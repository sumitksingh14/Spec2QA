"""
llm_service.py — Spec2QA two-pass test-case generation pipeline.

Enhanced pipeline (v2):
  Pass 1   : _extract_testable_behaviors()       — structured BehaviorTag list with risk_weight + source
  Pass 1b  : _verify_extraction_completeness()   — self-verification re-prompt, gap append   [§3]
  §2       : _classify_category_applicability()  — keyword heuristic, no LLM call
  §1       : _compute_slot_allocation()           — risk-weighted proportional budget
  Pass 2   : _generate_cases_for_behaviors()     — budget-aware, every case carries covers_behavior_id
  §4       : _validate_specificity()             — rule-based; optional targeted regen for flagged cases
  §6       : _deduplicate_v2()                   — title + Jaccard(steps+expected_result)
  §5       : _compute_coverage_gaps()            — uncovered behavior list ranked by risk_weight

New features:
  Feature 1  : regenerate_single_case()          — focused single-case regen with optional instruction
  Feature 2  : answer_qa_question()              — lightweight Q&A against stored generation context
  Feature 3  : exclusion list in _extract_testable_behaviors() pass-through
  Feature 13 : ProviderConfig + fallback chain + draft mode

Hard constraints:
  - Total test cases ≤ 25  (TOTAL_CASE_CAP — never removed/configurable)
  - CATEGORY_MIN = 1 slot if category is applicable
  - CATEGORY_MAX = 12 slots per category
  - LLM calls: Pass 1, Pass 1b (self-verify), Pass 2, optional Pass 2 regen (flagged only)
"""

import os
import re
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict
from groq import Groq
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
FALLBACK_LLM_PROVIDER = os.getenv("FALLBACK_LLM_PROVIDER", "")  # Feature 13

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

TOTAL_CASE_CAP: int = 25         # Fixed product decision — never change
CATEGORY_MIN: int = 1            # Minimum slots per applicable category
CATEGORY_MAX: int = 12           # Maximum slots per category
CATEGORIES: List[str] = ["Functional", "Negative", "Boundary", "Security", "Accessibility"]

# Jaccard similarity threshold for near-duplicate detection (§6)
DEDUP_SIMILARITY_THRESHOLD: float = 0.65

# Generic expected-result patterns that trigger specificity flag (§4)
GENERIC_PATTERNS: List[str] = [
    r"\bshould work correctly\b",
    r"\bsystem behaves as expected\b",
    r"\bbehaves correctly\b",
    r"\bworks as expected\b",
    r"\bfunctions properly\b",
    r"\bas expected\b",
    r"\bshould function\b",
    r"\bsystem responds appropriately\b",
    r"\bno error occurs\b",
    r"\bno errors? occur\b",
]

# ---------------------------------------------------------------------------
# Feature 13 — ProviderConfig: clean abstraction over provider identity
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    name: str                           # "nvidia" | "groq"
    model_id: str
    max_tokens: int = 8192
    is_draft: bool = False              # True → fast/cheap preview model
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)


_PROVIDER_CONFIGS: Dict[str, ProviderConfig] = {
    "nvidia": ProviderConfig(
        name="nvidia",
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        max_tokens=16384,
        extra_kwargs={"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}},
    ),
    "groq": ProviderConfig(
        name="groq",
        model_id="openai/gpt-oss-20b",
        max_tokens=4096,
    ),
    # Draft mode — fast preview via groq smaller model
    "draft": ProviderConfig(
        name="groq",
        model_id="openai/gpt-oss-20b",
        max_tokens=4096,
        is_draft=True,
    ),
}


def _resolve_provider_chain(primary: str) -> List[ProviderConfig]:
    """Return [primary_config, fallback_config?] for use in _stream_response_with_fallback."""
    chain: List[ProviderConfig] = []

    # Normalise "draft" → use groq draft config but keep nvidia as fallback
    actual_primary = "draft" if primary == "draft" else primary
    cfg = _PROVIDER_CONFIGS.get(actual_primary) or _PROVIDER_CONFIGS.get("groq")
    chain.append(cfg)

    # Fallback (Feature 13): configured via env or opposite of primary
    fb_name = FALLBACK_LLM_PROVIDER or ("groq" if cfg.name == "nvidia" else "")
    if fb_name and fb_name != cfg.name:
        fb_cfg = _PROVIDER_CONFIGS.get(fb_name)
        if fb_cfg:
            chain.append(fb_cfg)

    return chain


# ---------------------------------------------------------------------------
# Internal type aliases
# ---------------------------------------------------------------------------

class BehaviorTag(TypedDict):
    id: int
    description: str
    source: str   # "explicit_ac" | "explicit_description" | "inferred"
    risk_weight: str  # "high" | "medium" | "low"


class CategoryStatus(TypedDict):
    applicable: bool
    reason: str
    allocated_slots: int


# ---------------------------------------------------------------------------
# LLM client helpers
# ---------------------------------------------------------------------------

def _get_client(provider: str) -> Any:
    """Return an LLM client based on the given provider name."""
    # Normalise: "draft" routes through groq
    actual = "groq" if provider == "draft" else provider
    if actual == "nvidia":
        if not NVIDIA_API_KEY:
            print("[llm_service] NVIDIA_API_KEY not set — AI generation unavailable.")
            return None
        return OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    else:
        if not GROQ_API_KEY:
            print("[llm_service] GROQ_API_KEY not set — AI generation unavailable.")
            return None
        return Groq(api_key=GROQ_API_KEY)


def _build_completion_kwargs(cfg: ProviderConfig, messages: list, temperature: float) -> dict:
    """Build kwargs dict for client.chat.completions.create from a ProviderConfig."""
    kwargs: Dict[str, Any] = {
        "model": cfg.model_id,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.95,
        "stream": True,
    }
    if cfg.name == "nvidia":
        kwargs["max_tokens"] = cfg.max_tokens
    else:
        kwargs["max_completion_tokens"] = cfg.max_tokens
    kwargs.update(cfg.extra_kwargs)
    return kwargs


def _stream_response(
    client: Any,
    provider: str,
    messages: list,
    temperature: float = 0.6,
    max_retries: int = 3,
    metrics: Optional[Dict] = None,
) -> str:
    """
    Stream a chat completion from the configured LLM API.
    Feature 13: on exhaustion of retries, tries fallback provider automatically.
    Feature 14: if metrics dict is provided, accumulates retry_count.
    Returns the final answer content.
    """
    provider_chain = _resolve_provider_chain(provider)
    last_error: Optional[Exception] = None

    for cfg in provider_chain:
        prov_client = _get_client(cfg.name) if cfg.name != provider else client
        if prov_client is None:
            continue

        for attempt in range(1, max_retries + 1):
            try:
                kwargs = _build_completion_kwargs(cfg, messages, temperature)
                completion = prov_client.chat.completions.create(**kwargs)
                content_parts = []
                for chunk in completion:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content_parts.append(delta.content)
                result = "".join(content_parts).strip()
                if metrics is not None:
                    metrics["provider_used"] = cfg.name
                return result
            except Exception as e:
                last_error = e
                is_transient = any(
                    phrase in str(e).lower()
                    for phrase in ["overloaded", "rate limit", "too many requests", "503", "429", "timeout", "connection"]
                )
                if metrics is not None:
                    metrics["retry_count"] = metrics.get("retry_count", 0) + 1
                if is_transient and attempt < max_retries:
                    wait = 2 ** attempt  # 2s, 4s, 8s …
                    print(f"[llm_service] Transient error on {cfg.name} (attempt {attempt}/{max_retries}): {e}. Retrying in {wait}s…")
                    time.sleep(wait)
                else:
                    print(f"[llm_service] {cfg.name} exhausted ({e}) — trying fallback if available.")
                    break  # try next in chain

    if last_error:
        raise last_error
    raise RuntimeError("All providers exhausted in _stream_response")


def _parse_json_from_response(raw: str):
    """
    Robustly extract JSON from a model response that may include
    thinking blocks (<think>...</think>), markdown fences (```json ... ```),
    or plain JSON text. Handles truncated JSON arrays gracefully.
    """
    text = raw.strip()
    # Strip <think>...</think> if present
    if "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text[text.index("\n") + 1:] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()

    # Isolate JSON object or array bounds
    first_bracket = min(
        [pos for pos in [text.find("{"), text.find("[")] if pos != -1],
        default=-1
    )
    last_bracket = max(
        [text.rfind("}"), text.rfind("]")],
        default=-1
    )
    candidate_text = text
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate_text = text[first_bracket:last_bracket + 1]

    try:
        return json.loads(candidate_text)
    except json.JSONDecodeError:
        # If truncated JSON array, recover all valid complete JSON objects inside it
        if "[" in text:
            objs = []
            for match in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, flags=re.DOTALL):
                try:
                    obj = json.loads(match.group(0))
                    if isinstance(obj, dict):
                        objs.append(obj)
                except Exception:
                    pass
            if objs:
                print(f"[llm_service] Recovered {len(objs)} items from truncated JSON response.")
                return objs

        return json.loads(candidate_text)


# ---------------------------------------------------------------------------
# Public API — analyze_story
# ---------------------------------------------------------------------------

def analyze_story(story_text: str) -> Dict[str, Any]:
    """
    Use the LLM to analyze a user story.
    Returns detected ambiguities, missing elements, and extracted entities.
    Falls back gracefully if the API is unavailable or parsing fails.
    """
    provider = LLM_PROVIDER
    client = _get_client(provider)

    if client:
        system_prompt = (
            "You are a senior QA Architect. Analyze the provided user story and:\n"
            "1. Identify unclear or ambiguous requirements that need clarification.\n"
            "2. List missing acceptance criteria or constraint definitions.\n"
            "3. Extract key actors, actions, and data entities.\n\n"
            "Respond ONLY with a single valid JSON object — no explanation, no markdown fences. "
            "Use exactly this schema:\n"
            '{"questions": ["<clarifying question>"], '
            '"missing_elements": ["<missing element>"], '
            '"extracted_entities": {"actors": [...], "actions": [...], "data_entities": [...]}}\n'
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze this user story:\n\n{story_text}"},
        ]
        try:
            raw = _stream_response(client, provider, messages, temperature=0.4)
            data = _parse_json_from_response(raw)
            return {
                "questions": data.get("questions", []),
                "missing_elements": data.get("missing_elements", []),
                "extracted_entities": data.get("extracted_entities", {}),
            }
        except Exception as e:
            print(f"[llm_service] analyze_story error: {e}")

    return {
        "questions": [],
        "missing_elements": [],
        "extracted_entities": {
            "actors": [],
            "actions": [],
            "data_entities": [],
        },
    }


# ---------------------------------------------------------------------------
# §3 — Pass 1: Structured behavior extraction with risk_weight + source tags
# ---------------------------------------------------------------------------

_HIGH_RISK_KEYWORDS = {
    "must", "shall", "required", "mandatory", "auth", "authentication",
    "authorization", "login", "logout", "password", "token", "payment",
    "pii", "personal", "permission", "role", "admin", "security", "critical",
    "csrf", "injection", "encrypt", "credential", "2fa", "mfa", "otp",
}
_MEDIUM_RISK_KEYWORDS = {
    "should", "validate", "validation", "error", "fail", "failure", "retry",
    "timeout", "limit", "exceed", "reject", "prevent", "handle", "exception",
    "race", "concurrent", "concurrency", "duplicate", "unique", "constraint",
}


def _infer_risk_weight(description: str) -> Literal["high", "medium", "low"]:
    """Keyword-based risk weight — no LLM call."""
    lower = description.lower()
    tokens = set(re.findall(r"\b\w+\b", lower))
    if tokens & _HIGH_RISK_KEYWORDS:
        return "high"
    if tokens & _MEDIUM_RISK_KEYWORDS:
        return "medium"
    return "low"


def _extract_testable_behaviors(
    client: Any,
    provider: str,
    story_text: str,
    excluded_ac_ids: Optional[List[int]] = None,
    metrics: Optional[Dict] = None,
) -> List[BehaviorTag]:
    """
    Pass 1 — Ask the model to enumerate every distinct testable behavior,
    acceptance criterion, rule, and edge condition present in the story.

    Feature 3: excluded_ac_ids — IDs of ACs to skip during extraction.
    Returns a list of BehaviorTag dicts with: id, description, source, risk_weight.
    """
    exclusion_block = ""
    if excluded_ac_ids:
        exclusion_block = (
            f"\n\nDo NOT extract behaviors for acceptance criteria with these indices "
            f"(0-based): {excluded_ac_ids}. Ignore them completely.\n"
        )

    system_prompt = (
        "You are a senior QA Architect. Read the user story carefully and enumerate "
        "distinct, high-value testable behaviors, acceptance criteria, business rules, "
        "constraints, error conditions, and edge cases. Aim for 20 to 35 concise, unique behaviors total. "
        "Do NOT generate repetitive or near-duplicate variations.\n\n"
        "Consider:\n"
        "  - Stated acceptance criteria\n"
        "  - Error and failure paths\n"
        "  - Data validation rules (format, length, required)\n"
        "  - Security and authentication constraints\n"
        "  - Key accessibility and UX requirements\n"
        + exclusion_block +
        "\nFor each behavior, classify its SOURCE as one of:\n"
        '  "explicit_ac"          — directly stated as an Acceptance Criterion\n'
        '  "explicit_description" — clearly mentioned in the story description body\n'
        '  "inferred"             — implied but not explicitly written\n\n'
        "Respond ONLY with a valid JSON array — no explanation, no markdown fences.\n"
        "Schema for each element:\n"
        '{"description": "string", "source": "explicit_ac|explicit_description|inferred"}'
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"User Story:\n{story_text}"},
    ]
    raw = ""
    try:
        raw = _stream_response(client, provider, messages, temperature=0.3, metrics=metrics)
        result = _parse_json_from_response(raw)
        if not isinstance(result, list):
            raise ValueError(f"Expected list, got: {type(result)}")

        behaviors: List[BehaviorTag] = []
        for i, item in enumerate(result):
            if isinstance(item, str):
                desc = item
                src = "inferred"
            elif isinstance(item, dict):
                desc = item.get("description", "")
                src = item.get("source", "inferred")
                if src not in ("explicit_ac", "explicit_description", "inferred"):
                    src = "inferred"
            else:
                continue
            if desc:
                behaviors.append(BehaviorTag(
                    id=i,
                    description=desc,
                    source=src,
                    risk_weight=_infer_risk_weight(desc),
                ))
        return behaviors
    except Exception as e:
        print(f"[llm_service] _extract_testable_behaviors error: {e}\nRaw: {raw!r}")
        return []


# ---------------------------------------------------------------------------
# §3 — Pass 1b: Self-verification completeness re-prompt
# ---------------------------------------------------------------------------

def _verify_extraction_completeness(
    client: Any, provider: str, story_text: str, behaviors: List[BehaviorTag],
    metrics: Optional[Dict] = None,
) -> List[BehaviorTag]:
    """
    Pass 1b — Feed the story + extracted behavior list back to the model.
    Ask it to identify any ACs or explicit requirement sentences NOT covered.
    Appends gap behaviors with source="inferred" and re-indexes IDs.
    """
    if not behaviors:
        return behaviors

    # Compact behavior list and story text to keep token count under 2k
    selected_behaviors = behaviors[:25]
    behavior_list_text = "\n".join(
        f"  {b['id']}. [{b['source']}] {b['description'][:100]}" for b in selected_behaviors
    )
    compact_story = story_text[:1500] if len(story_text) > 1500 else story_text

    system_prompt = (
        "You are a senior QA Architect performing a coverage audit.\n\n"
        "You will be given:\n"
        "  1. An original user story\n"
        "  2. A list of testable behaviors already extracted from it\n\n"
        "Your task: Identify any acceptance criteria, explicit requirement sentences, "
        "or non-functional requirements in the story that are NOT already represented "
        "in the extracted behavior list.\n\n"
        "Look specifically for missed:\n"
        "  - Input validation rules (field lengths, formats, required vs optional)\n"
        "  - Concurrency/race conditions (shared state, simultaneous operations)\n"
        "  - Localization/i18n requirements (translated text, locale-dependent formats)\n"
        "  - Error message correctness (specific expected error text)\n"
        "  - Performance/timeout constraints\n\n"
        "If nothing is missing, respond with an empty JSON array: []\n"
        "Otherwise respond ONLY with a valid JSON array of gap descriptions — "
        "no explanation, no markdown fences.\n"
        'Schema: ["<gap description 1>", "<gap description 2>", ...]'
    )
    user_content = (
        f"User Story:\n{compact_story}\n\n"
        f"Already-extracted behaviors:\n{behavior_list_text}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    try:
        raw = _stream_response(client, provider, messages, temperature=0.3, metrics=metrics)
        gaps = _parse_json_from_response(raw)
        if not isinstance(gaps, list):
            return behaviors

        next_id = max(b["id"] for b in behaviors) + 1 if behaviors else 0
        appended = []
        for gap in gaps:
            if isinstance(gap, str) and gap.strip():
                appended.append(BehaviorTag(
                    id=next_id,
                    description=gap.strip(),
                    source="inferred",
                    risk_weight=_infer_risk_weight(gap),
                ))
                next_id += 1
        if appended:
            print(f"[llm_service] Pass 1b gap-fill: appended {len(appended)} missing behaviors.")
    except Exception as e:
        print(f"[llm_service] _verify_extraction_completeness error: {e}")
        return behaviors


_SECURITY_KEYWORDS = {
    "auth", "authentication", "authorization", "login", "logout", "password",
    "token", "permission", "role", "admin", "payment", "pii", "personal data",
    "csrf", "injection", "encrypt", "credential", "2fa", "mfa", "otp", "session",
    "privilege", "access control", "api key", "secret",
}
_ACCESSIBILITY_KEYWORDS = {
    "button", "form", "input", "label", "image", "img", "modal", "dialog",
    "screen reader", "keyboard", "focus", "aria", "wcag", "contrast", "ui",
    "interface", "web", "page", "click", "tap", "menu", "link", "checkbox",
    "radio", "select", "dropdown", "tooltip",
}
_BOUNDARY_KEYWORDS = {
    "limit", "max", "min", "maximum", "minimum", "length", "range", "size",
    "count", "threshold", "quota", "characters", "digits", "exceed", "truncat",
    "overflow", "underflow", "boundary", "edge", "cap",
}


def _classify_category_applicability(
    behaviors: List[BehaviorTag], story_text: str
) -> Dict[str, CategoryStatus]:
    """§2 — Rule-based applicability check for all 5 categories."""
    combined_text = story_text.lower() + " " + " ".join(b["description"].lower() for b in behaviors)
    tokens = set(re.findall(r"\b\w+\b", combined_text))

    def _check(keyword_set: set) -> bool:
        if tokens & keyword_set:
            return True
        for kw in keyword_set:
            if " " in kw and kw in combined_text:
                return True
        return False

    security_ok = _check(_SECURITY_KEYWORDS)
    accessibility_ok = _check(_ACCESSIBILITY_KEYWORDS)
    boundary_ok = _check(_BOUNDARY_KEYWORDS)

    return {
        "Functional": CategoryStatus(applicable=True, reason="Always applicable", allocated_slots=0),
        "Negative": CategoryStatus(applicable=True, reason="Always applicable — every story has error/failure paths", allocated_slots=0),
        "Boundary": CategoryStatus(
            applicable=boundary_ok,
            reason="Boundary-relevant keywords detected in story/behaviors" if boundary_ok else "No input limits, ranges, or boundary keywords identified in story",
            allocated_slots=0,
        ),
        "Security": CategoryStatus(
            applicable=security_ok,
            reason="Security-sensitive keywords detected (auth/payment/PII/permissions)" if security_ok else "No security surface identified in story",
            allocated_slots=0,
        ),
        "Accessibility": CategoryStatus(
            applicable=accessibility_ok,
            reason="UI surface keywords detected (forms, inputs, interactive elements)" if accessibility_ok else "No UI surface identified in story",
            allocated_slots=0,
        ),
    }


# ---------------------------------------------------------------------------
# §1 — Risk-weighted slot allocation
# ---------------------------------------------------------------------------

_RISK_WEIGHTS: Dict[str, int] = {"high": 3, "medium": 2, "low": 1}


def _compute_slot_allocation(
    behaviors: List[BehaviorTag],
    applicability: Dict[str, CategoryStatus],
    total: int = TOTAL_CASE_CAP,
) -> Dict[str, int]:
    """§1 — Distribute `total` slots across applicable categories proportionally."""
    applicable_cats = [c for c, s in applicability.items() if s["applicable"]]
    if not applicable_cats:
        applicable_cats = ["Functional"]

    category_scores: Dict[str, float] = {c: 0.0 for c in applicable_cats}

    _CAT_KEYWORD_MAP: Dict[str, set] = {
        "Security":      _SECURITY_KEYWORDS | {"attack", "exploit", "vulnerability", "bypass"},
        "Accessibility": _ACCESSIBILITY_KEYWORDS | {"wcag", "aria", "focus", "contrast"},
        "Boundary":      _BOUNDARY_KEYWORDS | {"off-by-one", "overflow", "underflow"},
        "Negative":      {"error", "fail", "invalid", "reject", "unauthor", "forbidden",
                          "missing", "empty", "null", "exception", "timeout", "deny"},
    }

    for behavior in behaviors:
        weight = _RISK_WEIGHTS.get(behavior["risk_weight"], 1)
        lower = behavior["description"].lower()
        btokens = set(re.findall(r"\b\w+\b", lower))
        matched_cats = set()
        for cat, kw_set in _CAT_KEYWORD_MAP.items():
            if cat in applicable_cats and (btokens & kw_set):
                category_scores[cat] += weight
                matched_cats.add(cat)
        if "Functional" in applicable_cats:
            category_scores["Functional"] += weight * (0.5 if matched_cats else 1.0)

    allocation: Dict[str, int] = {c: CATEGORY_MIN for c in applicable_cats}
    reserved = CATEGORY_MIN * len(applicable_cats)
    remaining = total - reserved

    total_score = sum(category_scores.values()) or 1.0
    extra: Dict[str, float] = {
        c: (category_scores[c] / total_score) * remaining for c in applicable_cats
    }

    extra_floor = {c: int(v) for c, v in extra.items()}
    leftover = remaining - sum(extra_floor.values())

    fracs = sorted(applicable_cats, key=lambda c: extra[c] - extra_floor[c], reverse=True)
    for c in fracs:
        if leftover <= 0:
            break
        cap_room = CATEGORY_MAX - CATEGORY_MIN - extra_floor[c]
        if cap_room > 0:
            extra_floor[c] += 1
            leftover -= 1

    for c in applicable_cats:
        allocation[c] = CATEGORY_MIN + extra_floor[c]
        allocation[c] = min(allocation[c], CATEGORY_MAX)

    while sum(allocation.values()) > total:
        trim_cat = min(applicable_cats, key=lambda c: category_scores.get(c, 0))
        if allocation[trim_cat] > CATEGORY_MIN:
            allocation[trim_cat] -= 1
        else:
            break

    return allocation


# ---------------------------------------------------------------------------
# Pass 2 — Budget-aware test case generation
# ---------------------------------------------------------------------------

def _generate_cases_for_behaviors(
    client: Any,
    provider: str,
    story_text: str,
    behaviors: List[BehaviorTag],
    allocation: Dict[str, int],
    applicability: Dict[str, CategoryStatus],
    metrics: Optional[Dict] = None,
) -> list:
    """Pass 2 — Generate test cases proportionally across applicable categories."""
    # Cap behaviors in Pass 2 prompt to top 30 to stay well under TPM token limits
    selected_behaviors = behaviors[:30]
    behaviors_block = "\n".join(
        f"  [{b['id']}] [{b['risk_weight'].upper()}] {b['description'][:150]}"
        for b in selected_behaviors
    )
    compact_story = story_text[:2500] if len(story_text) > 2500 else story_text

    applicable_categories = [c for c, s in applicability.items() if s["applicable"]]
    category_budget_block = "\n".join(
        f"  - {cat}: {allocation.get(cat, 0)} cases"
        for cat in CATEGORIES
        if applicability.get(cat, {}).get("applicable", False)
    )
    skipped_block = "\n".join(
        f"  - {cat} (reason: {applicability[cat]['reason']})"
        for cat in CATEGORIES
        if not applicability.get(cat, {}).get("applicable", True)
    )

    system_prompt = (
        "You are a principal QA Lead with expertise in comprehensive test design. "
        "You are given a user story and a list of key testable behaviors.\n\n"
        "YOUR TASK: Generate the FULL set of manual test cases within the EXACT slot budget below.\n\n"
        f"SLOT BUDGET (must not exceed):\n{category_budget_block}\n\n"
        + (f"SKIPPED CATEGORIES (do NOT generate for these):\n{skipped_block}\n\n" if skipped_block else "")
        + "RULES:\n"
        "1. Cover as many behaviors as possible — prioritise HIGH risk_weight behaviors first.\n"
        "2. Each test case must be in one of these categories: "
        + ", ".join(applicable_categories) + ".\n"
        "3. Do NOT exceed the slot count for any category.\n"
        "4. Each Expected Result must be SPECIFIC and VERIFIABLE — never vague.\n"
        "   FORBIDDEN phrases: 'should work correctly', 'system behaves as expected', "
        "   'behaves correctly', 'works as expected', 'functions properly'.\n"
        "5. Steps must be atomic, numbered actions a tester can execute without ambiguity.\n"
        "6. For Boundary category: the steps AND expected_result MUST include the actual "
        "   numeric/character boundary values being tested.\n"
        "7. Each test case MUST include 'covers_behavior_id' — the integer ID of the "
        "   behavior from the list below that this test primarily covers.\n\n"
        "Respond ONLY with a valid JSON array — no explanation, no markdown fences.\n"
        "Schema for each element:\n"
        '{"title": "string", '
        '"category": "Functional|Negative|Boundary|Security|Accessibility", '
        '"priority": "High|Medium|Low", '
        '"preconditions": "string", '
        '"steps": ["Step 1", "Step 2", "..."], '
        '"expected_result": "string", '
        '"covers_behavior_id": <integer>}'
    )
    user_content = (
        f"User Story:\n{compact_story}\n\n"
        f"Testable Behaviors to cover (ID, risk, description):\n{behaviors_block}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    try:
        raw = _stream_response(client, provider, messages, temperature=0.5, metrics=metrics)
        result = _parse_json_from_response(raw)
        if isinstance(result, list) and len(result) > 0:
            return result
        raise ValueError(f"Expected non-empty list, got: {type(result)}")
    except Exception as e:
        print(f"[llm_service] _generate_cases_for_behaviors error: {e}\nRaw: {raw!r}")
        return []


# ---------------------------------------------------------------------------
# §4 — Specificity validation + targeted regen
# ---------------------------------------------------------------------------

_GENERIC_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in GENERIC_PATTERNS]
_BOUNDARY_NUM_RE = re.compile(r"\d+")


def _is_generic_expected_result(expected_result: str) -> bool:
    return any(p.search(expected_result) for p in _GENERIC_PATTERNS_COMPILED)


def _is_boundary_missing_values(tc: dict) -> bool:
    if tc.get("category") != "Boundary":
        return False
    combined = " ".join(tc.get("steps", [])) + " " + tc.get("expected_result", "")
    return not _BOUNDARY_NUM_RE.search(combined)


def _validate_specificity(test_cases: list) -> Tuple[list, list]:
    """§4 — Rule-based post-generation validator. Returns (valid_cases, flagged_cases)."""
    valid, flagged = [], []
    for tc in test_cases:
        reasons = []
        if _is_generic_expected_result(tc.get("expected_result", "")):
            reasons.append("Generic expected_result phrase detected")
        if _is_boundary_missing_values(tc):
            reasons.append("Boundary case missing numeric boundary values in steps/expected_result")
        if reasons:
            tc = dict(tc)
            tc["_flag_reason"] = "; ".join(reasons)
            flagged.append(tc)
        else:
            valid.append(tc)
    return valid, flagged


def _regenerate_flagged_cases(
    client: Any,
    provider: str,
    story_text: str,
    flagged_cases: list,
    behaviors: List[BehaviorTag],
    metrics: Optional[Dict] = None,
) -> list:
    """§4 — One targeted regen call for flagged low-specificity cases."""
    if len(flagged_cases) > 8:
        print(f"[llm_service] §4: {len(flagged_cases)} flagged cases — too many for regen, returning as-is.")
        return [dict(tc, _flag_kept=True) for tc in flagged_cases]

    cases_block = json.dumps([
        {k: v for k, v in tc.items() if not k.startswith("_")}
        for tc in flagged_cases
    ], indent=2)

    system_prompt = (
        "You are a senior QA Engineer fixing vague test cases.\n\n"
        "Each test case below has been flagged for one of these reasons:\n"
        "  1. Expected result uses generic phrases ('should work correctly', etc.) — make it specific.\n"
        "  2. Boundary test case is missing the actual numeric/string boundary values.\n\n"
        "RULES:\n"
        "  - Keep the same title, category, priority, and covers_behavior_id.\n"
        "  - Replace only the generic/vague expected_result with a precise, verifiable outcome.\n"
        "  - For Boundary cases: include actual boundary values in both steps and expected_result.\n"
        "  - FORBIDDEN phrases: 'should work correctly', 'system behaves as expected', etc.\n\n"
        "Respond ONLY with a valid JSON array of the fixed test cases — "
        "same length as input, same order, no markdown fences."
    )
    user_content = (
        f"User Story (for context):\n{story_text}\n\n"
        f"Flagged test cases to fix:\n{cases_block}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    try:
        raw = _stream_response(client, provider, messages, temperature=0.3, metrics=metrics)
        fixed = _parse_json_from_response(raw)
        if isinstance(fixed, list) and len(fixed) == len(flagged_cases):
            print(f"[llm_service] §4: Successfully regenerated {len(fixed)} flagged cases.")
            return fixed
        raise ValueError(f"Regen returned wrong count: {len(fixed) if isinstance(fixed, list) else type(fixed)}")
    except Exception as e:
        print(f"[llm_service] §4 regen error: {e}\nRaw: {raw!r}")
        return [{k: v for k, v in tc.items() if not k.startswith("_")} for tc in flagged_cases]


# ---------------------------------------------------------------------------
# §6 — Dedup v2: title + Jaccard similarity on (steps + expected_result)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set:
    return set(re.findall(r"\b\w+\b", text.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _case_specificity_score(tc: dict) -> int:
    score = 0
    score += len(tc.get("expected_result", ""))
    score += sum(len(s) for s in tc.get("steps", []))
    score += len(tc.get("preconditions", ""))
    return score


def _deduplicate_v2(test_cases: list) -> list:
    """§6 — Two-pass deduplication (title exact + Jaccard within category)."""
    title_seen: Dict[str, int] = {}
    result: list = []
    for tc in test_cases:
        key = tc.get("title", "").lower().strip()
        if not key:
            result.append(tc)
            continue
        if key in title_seen:
            existing_idx = title_seen[key]
            existing = result[existing_idx]
            if _case_specificity_score(tc) > _case_specificity_score(existing):
                result[existing_idx] = tc
        else:
            title_seen[key] = len(result)
            result.append(tc)

    by_category: Dict[str, list] = {}
    for tc in result:
        cat = tc.get("category", "Functional")
        by_category.setdefault(cat, []).append(tc)

    final: list = []
    for cat, cat_cases in by_category.items():
        content_tokens: List[set] = []
        cat_final: list = []
        for tc in cat_cases:
            content = " ".join(tc.get("steps", [])) + " " + tc.get("expected_result", "")
            tokens = _tokenize(content)
            is_dup = False
            for i, existing_tokens in enumerate(content_tokens):
                if _jaccard(tokens, existing_tokens) >= DEDUP_SIMILARITY_THRESHOLD:
                    if _case_specificity_score(tc) > _case_specificity_score(cat_final[i]):
                        cat_final[i] = tc
                        content_tokens[i] = tokens
                    is_dup = True
                    break
            if not is_dup:
                cat_final.append(tc)
                content_tokens.append(tokens)
        final.extend(cat_final)

    freed = len(test_cases) - len(final)
    if freed:
        print(f"[llm_service] §6 dedup: removed {freed} near-duplicate cases.")
    return final


# ---------------------------------------------------------------------------
# §5 — Coverage gap surfacing
# ---------------------------------------------------------------------------

def _compute_coverage_gaps(
    behaviors: List[BehaviorTag], test_cases: list
) -> List[BehaviorTag]:
    """§5 — Identify behaviors from Pass 1 with zero test cases covering them."""
    covered_ids: set = set()
    for tc in test_cases:
        bid = tc.get("covers_behavior_id")
        if bid is not None:
            try:
                covered_ids.add(int(bid))
            except (TypeError, ValueError):
                pass

    uncovered = [b for b in behaviors if b["id"] not in covered_ids]
    weight_order = {"high": 0, "medium": 1, "low": 2}
    uncovered.sort(key=lambda b: weight_order.get(b["risk_weight"], 3))

    if uncovered:
        print(f"[llm_service] §5: {len(uncovered)} behaviors uncovered within 25-case budget.")
    return uncovered


# ---------------------------------------------------------------------------
# Feature 1 — Per-case regeneration
# ---------------------------------------------------------------------------

def regenerate_single_case(
    story_text: str,
    behavior_tag: Optional[Dict],
    existing_case: Dict,
    instruction: Optional[str] = None,
    provider_override: Optional[str] = None,
) -> Optional[Dict]:
    """
    Feature 1 — Regenerate a single test case with an optional user instruction.
    Preserves category and covers_behavior_id.
    Returns the updated case dict, or None on failure.
    """
    provider = provider_override or LLM_PROVIDER
    client = _get_client(provider)
    if not client:
        return None

    behavior_block = ""
    if behavior_tag:
        behavior_block = (
            f"\nOriginal behavior context this case covers:\n"
            f"  [{behavior_tag.get('risk_weight', 'medium').upper()}] "
            f"[{behavior_tag.get('source', 'inferred')}] "
            f"{behavior_tag.get('description', '')}\n"
        )

    instruction_block = ""
    if instruction:
        instruction_block = f"\nUser instruction: {instruction}\n"

    existing_json = json.dumps({k: v for k, v in existing_case.items()}, indent=2)

    system_prompt = (
        "You are a senior QA Engineer improving a single test case.\n\n"
        "RULES:\n"
        "  - Keep the same category (MUST NOT change).\n"
        "  - Keep covers_behavior_id unchanged unless the user instruction explicitly asks to change it.\n"
        "  - Follow any user instruction provided.\n"
        "  - Expected result must be SPECIFIC and VERIFIABLE.\n"
        "  - FORBIDDEN phrases: 'should work correctly', 'system behaves as expected', etc.\n\n"
        "Respond ONLY with a single valid JSON object for the updated test case — "
        "same schema as input, no explanation, no markdown fences.\n"
        '{"title": "string", "category": "string", "priority": "High|Medium|Low", '
        '"preconditions": "string", "steps": ["..."], "expected_result": "string", '
        '"covers_behavior_id": <int>}'
    )
    user_content = (
        f"User Story (context):\n{story_text}\n"
        + behavior_block
        + instruction_block
        + f"\nExisting test case to improve:\n{existing_json}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    try:
        raw = _stream_response(client, provider, messages, temperature=0.5)
        result = _parse_json_from_response(raw)
        if isinstance(result, dict) and "title" in result:
            # Preserve category from original if model changed it
            result["category"] = existing_case.get("category", result.get("category", "Functional"))
            return result
        raise ValueError(f"Unexpected response shape: {result!r}")
    except Exception as e:
        print(f"[llm_service] regenerate_single_case error: {e}\nRaw: {raw!r}")
        return None


# ---------------------------------------------------------------------------
# Feature 2 — Post-generation Q&A
# ---------------------------------------------------------------------------

def answer_qa_question(
    story_text: str,
    generation_meta: Dict,
    test_cases_summary: List[Dict],
    question: str,
    provider_override: Optional[str] = None,
) -> str:
    """
    Feature 2 — Answer a free-text question about an already-generated result set.
    No new extraction or generation — single lightweight completion.
    """
    provider = provider_override or LLM_PROVIDER
    client = _get_client(provider)
    if not client:
        return "AI is currently unavailable. Please check your API key configuration."

    # Build compact context from generation meta
    uncovered = generation_meta.get("uncovered_behaviors", [])
    category_alloc = generation_meta.get("category_allocation", {})
    tc_titles = [f"- [{tc.get('category', '?')}] {tc.get('title', '?')}" for tc in test_cases_summary[:25]]

    context_block = (
        f"Generated test cases ({len(tc_titles)} total):\n" + "\n".join(tc_titles) + "\n\n"
    )
    if uncovered:
        unc_lines = [f"  - [{b.get('risk_weight','?').upper()}] {b.get('description','')}" for b in uncovered[:10]]
        context_block += "Uncovered behaviors (not covered within 25-case budget):\n" + "\n".join(unc_lines) + "\n\n"
    if category_alloc:
        alloc_lines = [f"  {cat}: {s.get('allocated_slots', 0)} slots, applicable={s.get('applicable', True)}" for cat, s in category_alloc.items()]
        context_block += "Category allocation:\n" + "\n".join(alloc_lines) + "\n"

    system_prompt = (
        "You are a senior QA Architect who has just completed a test case generation run.\n"
        "Answer the user's question about the generated test suite using the context below.\n"
        "Be concise, factual, and reference specific test cases or behaviors when relevant.\n"
        "Do not generate new test cases — only answer the question.\n"
    )
    user_content = (
        f"Original Story:\n{story_text[:1500]}\n\n"
        + context_block
        + f"\nQuestion: {question}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    try:
        raw = _stream_response(client, provider, messages, temperature=0.4)
        return raw
    except Exception as e:
        print(f"[llm_service] answer_qa_question error: {e}\nRaw: {raw!r}")
        return f"Sorry, I encountered an error answering your question: {e}"


# ---------------------------------------------------------------------------
# Orchestration — generate_test_cases  (public API)
# ---------------------------------------------------------------------------

def generate_test_cases(
    story_text: str,
    provider_override: Optional[str] = None,
    excluded_ac_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Main orchestration function for the enhanced v2 generation pipeline.
    Feature 3: accepts excluded_ac_ids to skip specific ACs.
    Feature 14: returns metrics dict with token counts, wall time, retry count, provider.
    """
    import time as _time
    t_start = _time.monotonic()

    provider = provider_override if provider_override else LLM_PROVIDER
    client = _get_client(provider)
    if not client:
        return {"message": "AI Generation Disabled", "count": 0, "test_cases": []}

    # Shared metrics accumulator (Feature 14)
    metrics: Dict[str, Any] = {"retry_count": 0, "provider_used": provider}

    # ── Pass 1: Extract behaviors ──────────────────────────────────────────
    print("[llm_service] Pass 1: extracting testable behaviors…")
    behaviors = _extract_testable_behaviors(
        client, provider, story_text,
        excluded_ac_ids=excluded_ac_ids or [],
        metrics=metrics,
    )
    if not behaviors:
        print("[llm_service] Pass 1 returned no behaviors — aborting.")
        raise RuntimeError("Failed to extract any testable behaviors from the story.")

    print(f"[llm_service] Pass 1: {len(behaviors)} behaviors extracted.")

    # ── Pass 1b: Self-verification gap-fill (only run if Pass 1 found < 6 behaviors) ─
    if len(behaviors) < 6:
        print("[llm_service] Pass 1b: self-verification completeness check…")
        behaviors = _verify_extraction_completeness(client, provider, story_text, behaviors, metrics=metrics)
        print(f"[llm_service] Pass 1b complete: {len(behaviors)} behaviors total.")

    # ── §2: Category applicability ─────────────────────────────────────────
    applicability = _classify_category_applicability(behaviors, story_text)
    skipped_categories = [c for c, s in applicability.items() if not s["applicable"]]
    if skipped_categories:
        print(f"[llm_service] §2: Skipping categories: {skipped_categories}")

    # ── §1: Risk-weighted slot allocation ─────────────────────────────────
    allocation = _compute_slot_allocation(behaviors, applicability, total=TOTAL_CASE_CAP)
    for cat, slots in allocation.items():
        applicability[cat]["allocated_slots"] = slots
    print(f"[llm_service] §1: Slot allocation: {allocation}")

    # ── Pass 2: Generate test cases ────────────────────────────────────────
    print("[llm_service] Pass 2: generating test cases…")
    raw_cases = _generate_cases_for_behaviors(
        client, provider, story_text, behaviors, allocation, applicability, metrics=metrics
    )
    if not raw_cases:
        raise RuntimeError("Pass 2 returned empty list — failed to generate test cases.")

    raw_cases = raw_cases[:TOTAL_CASE_CAP]

    # ── §4: Specificity validation ─────────────────────────────────────────
    valid_cases, flagged_cases = _validate_specificity(raw_cases)
    if flagged_cases:
        print(f"[llm_service] §4: regenerating {len(flagged_cases)} non-specific cases…")
        fixed = _regenerate_flagged_cases(client, provider, story_text, flagged_cases, behaviors, metrics=metrics)
        valid_cases = valid_cases + fixed
        valid_cases, still_flagged = _validate_specificity(valid_cases)
        if still_flagged:
            print(f"[llm_service] §4: {len(still_flagged)} cases still flagged after regen — keeping.")
            valid_cases = valid_cases + [{k: v for k, v in tc.items() if not k.startswith("_")} for tc in still_flagged]

    # ── §6: Dedup v2 ──────────────────────────────────────────────────────
    deduped = _deduplicate_v2(valid_cases)
    deduped = deduped[:TOTAL_CASE_CAP]

    # ── §5: Coverage gap surfacing ─────────────────────────────────────────
    uncovered = _compute_coverage_gaps(behaviors, deduped)

    wall_time_ms = int((_time.monotonic() - t_start) * 1000)
    metrics["wall_time_ms"] = wall_time_ms

    print(
        f"[llm_service] Done: {len(deduped)} test cases, "
        f"{len(uncovered)} uncovered behaviors, "
        f"{len(skipped_categories)} skipped categories. "
        f"Wall time: {wall_time_ms}ms, retries: {metrics['retry_count']}."
    )

    return {
        "test_cases": deduped,
        "uncovered_behaviors": uncovered,
        "category_allocation": applicability,
        "skipped_categories": skipped_categories,
        "generation_meta": {
            "behaviors_extracted": len(behaviors),
            "behaviors_after_gap_fill": len(behaviors),
            "cases_before_dedup": len(valid_cases),
            "cases_after_dedup": len(deduped),
            "skipped_categories": skipped_categories,
            "slot_allocation": allocation,
        },
        # Feature 14 metrics
        "metrics": metrics,
    }
