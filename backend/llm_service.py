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
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

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
# LLM client helpers  (unchanged from v1)
# ---------------------------------------------------------------------------

def _get_client() -> Optional[OpenAI]:
    """Return an OpenAI-compatible client pointed at the NVIDIA NIM endpoint."""
    if not NVIDIA_API_KEY:
        print("[llm_service] NVIDIA_API_KEY not set — AI generation unavailable.")
        return None
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)


def _stream_response(
    client: OpenAI,
    messages: list,
    temperature: float = 0.6,
    max_retries: int = 3,
) -> str:
    """
    Stream a chat completion from the NVIDIA NIM API.
    Retries with exponential backoff on transient errors (overloaded, rate limit).
    Returns only the final answer content; thinking/reasoning tokens are discarded.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            completion = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
                top_p=0.95,
                max_tokens=16384,
                extra_body={"chat_template_kwargs": {"enable_thinking": True}},
                stream=True,
            )
            content_parts = []
            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # Ignore reasoning/thinking tokens — only capture the final answer
                if delta.content:
                    content_parts.append(delta.content)
            return "".join(content_parts).strip()
        except Exception as e:
            last_error = e
            is_transient = any(
                phrase in str(e).lower()
                for phrase in ["overloaded", "rate limit", "too many requests", "503", "429", "timeout", "connection"]
            )
            if is_transient and attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s, 8s …
                print(f"[llm_service] Transient API error (attempt {attempt}/{max_retries}): {e}. Retrying in {wait}s…")
                time.sleep(wait)
            else:
                raise
    if last_error:
        raise last_error
    raise RuntimeError("Unknown error in _stream_response")


def _parse_json_from_response(raw: str):
    """
    Robustly extract JSON from a model response that may include
    markdown fences (```json ... ```) or plain JSON.
    """
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = text[text.index("\n") + 1:] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Public API — analyze_story  (unchanged from v1)
# ---------------------------------------------------------------------------

def analyze_story(story_text: str) -> Dict[str, Any]:
    """
    Use the NVIDIA NIM LLM to analyze a user story.
    Returns detected ambiguities, missing elements, and extracted entities.
    Falls back gracefully if the API is unavailable or parsing fails.
    """
    client = _get_client()

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
            '"extracted_entities": {"actors": [], "actions": [], "data_entities": []}}'
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User Story:\n{story_text}"},
        ]
        raw = ""
        try:
            raw = _stream_response(client, messages, temperature=0.4)
            return _parse_json_from_response(raw)
        except Exception as e:
            print(f"[llm_service] analyze_story error: {e}\nRaw response: {raw!r}")

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


def _extract_testable_behaviors(client: OpenAI, story_text: str) -> List[BehaviorTag]:
    """
    Pass 1 — Ask the model to enumerate every distinct testable behavior,
    acceptance criterion, rule, and edge condition present in the story.

    Returns a list of BehaviorTag dicts with: id, description, source, risk_weight.
    source is classified from the model's output; risk_weight is post-processed
    keyword-based (no extra LLM call).
    """
    system_prompt = (
        "You are a senior QA Architect. Read the user story carefully and enumerate "
        "EVERY distinct testable behavior, acceptance criterion, business rule, "
        "constraint, error condition, and edge case you can identify.\n\n"
        "Think exhaustively. Consider:\n"
        "  - Each acceptance criterion as its own behavior\n"
        "  - All stated and implied error/failure paths\n"
        "  - Data validation rules (type, length, format, range, required)\n"
        "  - Authentication and authorisation rules\n"
        "  - Race conditions and concurrency scenarios\n"
        "  - Network/timeout/latency edge cases\n"
        "  - Security attack surfaces (injection, CSRF, token replay, enumeration)\n"
        "  - Accessibility requirements (keyboard, screen reader, contrast, focus)\n"
        "  - Implicit non-functional requirements: input validation limits, "
        "localization/i18n if user-facing text is involved, error-message correctness\n"
        "  - Cross-browser/device considerations if relevant\n"
        "  - Regression impact on adjacent features\n\n"
        "For each behavior, classify its SOURCE as one of:\n"
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
        raw = _stream_response(client, messages, temperature=0.3)
        result = _parse_json_from_response(raw)
        if not isinstance(result, list):
            raise ValueError(f"Expected list, got: {type(result)}")

        behaviors: List[BehaviorTag] = []
        for i, item in enumerate(result):
            if isinstance(item, str):
                # Tolerate plain string output from model
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
    client: OpenAI, story_text: str, behaviors: List[BehaviorTag]
) -> List[BehaviorTag]:
    """
    Pass 1b — Feed the story + extracted behavior list back to the model.
    Ask it to identify any ACs or explicit requirement sentences NOT covered.
    Appends gap behaviors with source="inferred" and re-indexes IDs.
    Temperature: 0.3 (focused, not creative) as per user preference.
    """
    if not behaviors:
        return behaviors

    behavior_list_text = "\n".join(
        f"  {b['id']}. [{b['source']}] {b['description']}" for b in behaviors
    )
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
        f"User Story:\n{story_text}\n\n"
        f"Already-extracted behaviors:\n{behavior_list_text}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    try:
        raw = _stream_response(client, messages, temperature=0.3)
        gaps = _parse_json_from_response(raw)
        if not isinstance(gaps, list):
            return behaviors

        # Append gaps, re-assign sequential IDs
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
        return behaviors + appended
    except Exception as e:
        print(f"[llm_service] _verify_extraction_completeness error: {e}\nRaw: {raw!r}")
        return behaviors  # Return original on failure


# ---------------------------------------------------------------------------
# §2 — Category applicability classifier (pure Python, no LLM)
# ---------------------------------------------------------------------------

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
    # Note: 'alert', 'notification', 'banner' intentionally excluded —
    # they are too ambiguous and trigger false positives for backend alerting systems.
}
_BOUNDARY_KEYWORDS = {
    "limit", "max", "min", "maximum", "minimum", "length", "range", "size",
    "count", "threshold", "quota", "characters", "digits", "exceed", "truncat",
    "overflow", "underflow", "boundary", "edge", "cap",
}


def _classify_category_applicability(
    behaviors: List[BehaviorTag], story_text: str
) -> Dict[str, CategoryStatus]:
    """
    §2 — Rule-based applicability check for all 5 categories.
    Functional and Negative are always applicable.
    Security, Accessibility, Boundary are keyword-driven.
    """
    combined_text = story_text.lower() + " " + " ".join(b["description"].lower() for b in behaviors)
    tokens = set(re.findall(r"\b\w+\b", combined_text))

    def _check(keyword_set: set) -> bool:
        # Check token overlap AND multi-word phrase match
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
        "Functional": CategoryStatus(
            applicable=True,
            reason="Always applicable",
            allocated_slots=0,  # filled by _compute_slot_allocation
        ),
        "Negative": CategoryStatus(
            applicable=True,
            reason="Always applicable — every story has error/failure paths",
            allocated_slots=0,
        ),
        "Boundary": CategoryStatus(
            applicable=boundary_ok,
            reason=(
                "Boundary-relevant keywords detected in story/behaviors"
                if boundary_ok
                else "No input limits, ranges, or boundary keywords identified in story"
            ),
            allocated_slots=0,
        ),
        "Security": CategoryStatus(
            applicable=security_ok,
            reason=(
                "Security-sensitive keywords detected (auth/payment/PII/permissions)"
                if security_ok
                else "No security surface identified in story (no auth, payment, or permission keywords)"
            ),
            allocated_slots=0,
        ),
        "Accessibility": CategoryStatus(
            applicable=accessibility_ok,
            reason=(
                "UI surface keywords detected (forms, inputs, interactive elements)"
                if accessibility_ok
                else "No UI surface identified in story — backend/batch/API story with no interactive elements"
            ),
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
    """
    §1 — Distribute `total` slots across applicable categories proportionally
    to the sum of risk-weighted behaviors relevant to each category.

    Mapping from behavior keywords to categories is intentionally broad so that
    high-risk behaviors (auth, payment, etc.) pull weight toward Security/Negative,
    while UI-heavy behaviors pull toward Accessibility.

    Constraints: CATEGORY_MIN ≤ slots ≤ CATEGORY_MAX per applicable category.
    Inapplicable categories get 0 slots; their budget redistributes.
    """
    applicable_cats = [c for c, s in applicability.items() if s["applicable"]]
    if not applicable_cats:
        applicable_cats = ["Functional"]  # fallback safety

    # Compute per-category raw scores
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

        # Distribute weight to matching categories; Functional always gets base credit
        matched_cats = set()
        for cat, kw_set in _CAT_KEYWORD_MAP.items():
            if cat in applicable_cats and (btokens & kw_set):
                category_scores[cat] += weight
                matched_cats.add(cat)
        # Behaviors that don't match any specialized category go to Functional
        if "Functional" in applicable_cats:
            category_scores["Functional"] += weight * (0.5 if matched_cats else 1.0)

    # Apply CATEGORY_MIN floor first (reserve budget)
    allocation: Dict[str, int] = {c: CATEGORY_MIN for c in applicable_cats}
    reserved = CATEGORY_MIN * len(applicable_cats)
    remaining = total - reserved

    # Distribute remaining proportionally to scores, capped at CATEGORY_MAX - CATEGORY_MIN
    total_score = sum(category_scores.values()) or 1.0
    extra: Dict[str, float] = {
        c: (category_scores[c] / total_score) * remaining
        for c in applicable_cats
    }

    # Floor extra allocations, then distribute leftover slots
    extra_floor = {c: int(v) for c, v in extra.items()}
    leftover = remaining - sum(extra_floor.values())

    # Sort by fractional remainder descending to distribute leftover
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

    # Ensure total never exceeds cap (rare edge: rounding)
    while sum(allocation.values()) > total:
        # Trim from the lowest-priority category
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
    client: OpenAI,
    story_text: str,
    behaviors: List[BehaviorTag],
    allocation: Dict[str, int],
    applicability: Dict[str, CategoryStatus],
) -> list:
    """
    Pass 2 — For every extracted behavior, generate test cases proportionally
    across applicable categories using the slot allocation from §1.

    Each generated test case must include `covers_behavior_id` referencing
    the Pass 1 behavior ID it tests.
    """
    behaviors_block = "\n".join(
        f"  [{b['id']}] [{b['risk_weight'].upper()}] [{b['source']}] {b['description']}"
        for b in behaviors
    )
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
        "You are given a user story and a list of every testable behavior extracted from it.\n\n"
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
        "   numeric/character boundary values being tested (e.g. 'Enter 256 characters', "
        "   'submit with quantity = 0').\n"
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
        f"User Story:\n{story_text}\n\n"
        f"Testable Behaviors to cover (ID, risk, source, description):\n{behaviors_block}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    try:
        raw = _stream_response(client, messages, temperature=0.6)
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
    """For Boundary cases: steps + expected_result must contain at least one numeric value."""
    if tc.get("category") != "Boundary":
        return False
    combined = " ".join(tc.get("steps", [])) + " " + tc.get("expected_result", "")
    return not _BOUNDARY_NUM_RE.search(combined)


def _validate_specificity(test_cases: list) -> Tuple[list, list]:
    """
    §4 — Rule-based post-generation validator.
    Returns (valid_cases, flagged_cases).
    Flagged cases have a '_flag_reason' field added.
    """
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
    client: OpenAI,
    story_text: str,
    flagged_cases: list,
    behaviors: List[BehaviorTag],
) -> list:
    """
    §4 — One targeted regen call for flagged low-specificity cases.
    Only fires if len(flagged_cases) ≤ 8, to keep cost bounded.
    """
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
        "  - For Boundary cases: include actual boundary values (e.g. exact character counts, "
        "    numeric limits, or off-by-one values) in both steps and expected_result.\n"
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
        raw = _stream_response(client, messages, temperature=0.3)
        fixed = _parse_json_from_response(raw)
        if isinstance(fixed, list) and len(fixed) == len(flagged_cases):
            print(f"[llm_service] §4: Successfully regenerated {len(fixed)} flagged cases.")
            return fixed
        raise ValueError(f"Regen returned wrong count: {len(fixed) if isinstance(fixed, list) else type(fixed)}")
    except Exception as e:
        print(f"[llm_service] §4 regen error: {e}\nRaw: {raw!r}")
        # Return originals stripped of flag metadata
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
    """Higher score = more specific/complete case (prefer to keep)."""
    score = 0
    score += len(tc.get("expected_result", ""))
    score += sum(len(s) for s in tc.get("steps", []))
    score += len(tc.get("preconditions", ""))
    return score


def _deduplicate_v2(test_cases: list) -> list:
    """
    §6 — Two-pass deduplication.
    Pass A: exact title match (keep more specific case).
    Pass B: Jaccard similarity on (steps_text + expected_result) ≥ threshold,
            applied WITHIN each category only to prevent cross-category false positives
            (e.g. a Functional and a Security case with similar generic steps should
            not be merged — they serve distinct testing purposes).
    Returns deduplicated list.
    """
    # Pass A — title dedup across all categories
    title_seen: Dict[str, int] = {}  # title → index in result
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

    # Pass B — content Jaccard dedup within each category separately
    # (prevents merging cases from different categories that share boilerplate steps)
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
    """
    §5 — Identify behaviors from Pass 1 that have zero test cases covering them.
    Returns uncovered behaviors sorted by risk_weight (high → medium → low).
    """
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
# Orchestration — generate_test_cases  (public API)
# ---------------------------------------------------------------------------

def generate_test_cases(story_text: str) -> Dict[str, Any]:
    """
    Two-pass exhaustive test case generator with quality and coverage enhancements.

    Returns a dict with:
      test_cases           : list of test case dicts (≤ 25, same shape as v1)
      uncovered_behaviors  : list of BehaviorTag dicts not covered by any test case
      category_allocation  : dict[category → CategoryStatus] with applied slot counts
      skipped_categories   : list of category names classified as not applicable
      generation_meta      : diagnostic metadata (behavior count, passes run, etc.)
    """
    client = _get_client()
    if not client:
        raise RuntimeError("LLM client not available for generate_test_cases.")

    # ── Pass 1: Extract behaviors ──────────────────────────────────────────
    print("[llm_service] Pass 1: extracting testable behaviors…")
    behaviors = _extract_testable_behaviors(client, story_text)
    if not behaviors:
        print("[llm_service] Pass 1 returned no behaviors — aborting.")
        raise RuntimeError("Failed to extract any testable behaviors from the story.")

    print(f"[llm_service] Pass 1: {len(behaviors)} behaviors extracted.")

    # ── Pass 1b: Self-verification gap-fill ───────────────────────────────
    print("[llm_service] Pass 1b: self-verification completeness check…")
    behaviors = _verify_extraction_completeness(client, story_text, behaviors)
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
    raw_cases = _generate_cases_for_behaviors(client, story_text, behaviors, allocation, applicability)
    if not raw_cases:
        raise RuntimeError("Pass 2 returned empty list — failed to generate test cases.")

    # Enforce hard cap
    raw_cases = raw_cases[:TOTAL_CASE_CAP]

    # ── §4: Specificity validation ─────────────────────────────────────────
    valid_cases, flagged_cases = _validate_specificity(raw_cases)
    if flagged_cases:
        print(f"[llm_service] §4: {len(flagged_cases)} cases flagged for low specificity.")
        fixed = _regenerate_flagged_cases(client, story_text, flagged_cases, behaviors)
        valid_cases = valid_cases + fixed
        # Re-validate after regen
        valid_cases, still_flagged = _validate_specificity(valid_cases)
        if still_flagged:
            print(f"[llm_service] §4: {len(still_flagged)} cases still flagged after regen — keeping.")
            valid_cases = valid_cases + [{k: v for k, v in tc.items() if not k.startswith("_")} for tc in still_flagged]

    # ── §6: Dedup v2 ──────────────────────────────────────────────────────
    deduped = _deduplicate_v2(valid_cases)

    # Final hard cap enforcement
    deduped = deduped[:TOTAL_CASE_CAP]

    # ── §5: Coverage gap surfacing ─────────────────────────────────────────
    uncovered = _compute_coverage_gaps(behaviors, deduped)

    print(
        f"[llm_service] Done: {len(deduped)} test cases, "
        f"{len(uncovered)} uncovered behaviors, "
        f"{len(skipped_categories)} skipped categories."
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
    }
