import os
import json
import time
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


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
# Public API
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

    # --------------- Failure State ---------------
    # We no longer fall back to hardcoded text, as requested.
    # Return empty structures so the frontend can handle the absence of AI data.
    return {
        "questions": [],
        "missing_elements": [],
        "extracted_entities": {
            "actors": [],
            "actions": [],
            "data_entities": [],
        },
    }


def _extract_testable_behaviors(client: OpenAI, story_text: str) -> list:
    """
    Pass 1 — Ask the model to enumerate every distinct testable behavior,
    acceptance criterion, rule, and edge condition present in the story.
    Returns a list of plain-text behavior strings.
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
        "  - Cross-browser/device considerations if relevant\n"
        "  - Regression impact on adjacent features\n\n"
        "Respond ONLY with a valid JSON array of short behavior description strings. "
        "No explanation, no markdown fences. Example:\n"
        '["User can submit the form with all valid fields", '
        '"System rejects submission when required field is empty", ...]'
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"User Story:\n{story_text}"},
    ]
    raw = ""
    try:
        raw = _stream_response(client, messages, temperature=0.3)
        result = _parse_json_from_response(raw)
        if isinstance(result, list) and all(isinstance(b, str) for b in result):
            return result
        raise ValueError(f"Expected list of strings, got: {type(result)}")
    except Exception as e:
        print(f"[llm_service] _extract_testable_behaviors error: {e}\nRaw: {raw!r}")
        return []


def _generate_cases_for_behaviors(
    client: OpenAI, story_text: str, behaviors: list
) -> list:
    """
    Pass 2 — For every extracted behavior, generate as many test cases as
    appropriate across all 5 categories: Functional, Negative, Boundary,
    Security, Accessibility.
    """
    behaviors_block = "\n".join(f"- {b}" for b in behaviors)
    system_prompt = (
        "You are a principal QA Lead with expertise in comprehensive test design. "
        "You are given a user story and a list of every testable behavior extracted from it.\n\n"
        "YOUR TASK: Generate the FULL set of manual test cases that a rigorous QA team would write.\n\n"
        "RULES:\n"
        "1. Cover EVERY behavior listed — do not skip any.\n"
        "2. For each behavior generate ALL applicable test cases across these categories:\n"
        "     Functional  — happy-path and all AC verification\n"
        "     Negative    — invalid input, unauthorized access, error handling\n"
        "     Boundary    — min/max/exactly-at-limit/one-beyond-limit values\n"
        "     Security    — injection, token replay, enumeration, privilege escalation, CSRF\n"
        "     Accessibility — keyboard-only, screen reader, WCAG contrast, focus order\n"
        "3. Do NOT omit a category simply because the story doesn't explicitly mention it.\n"
        "4. Each Expected Result must be SPECIFIC and VERIFIABLE — never vague.\n"
        "5. Steps must be atomic, numbered actions a tester can execute without ambiguity.\n"
        "6. Generate a comprehensive set of test cases, but to avoid output limits, "
        "limit your response to a MAXIMUM of 25 highly distinct test cases total.\n"
        "   Focus on the most critical paths and edge cases first.\n\n"
        "Respond ONLY with a valid JSON array — no explanation, no markdown fences.\n"
        "Schema for each element:\n"
        '{"title": "string", '
        '"category": "Functional|Negative|Boundary|Security|Accessibility", '
        '"priority": "High|Medium|Low", '
        '"preconditions": "string", '
        '"steps": ["Step 1", "Step 2", "..."], '
        '"expected_result": "string"}'
    )
    user_content = (
        f"User Story:\n{story_text}\n\n"
        f"Testable Behaviors to cover:\n{behaviors_block}"
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


def _deduplicate(test_cases: list) -> list:
    """Remove near-identical test cases (same title after lowercasing and stripping)."""
    seen: set = set()
    unique = []
    for tc in test_cases:
        key = tc.get("title", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(tc)
    return unique


def generate_test_cases(story_text: str) -> list:
    """
    Two-pass exhaustive test case generator using the NVIDIA NIM LLM.

    Pass 1 — Extract every testable behavior from the story.
    Pass 2 — Generate ALL appropriate test cases for those behaviors,
              covering Functional, Negative, Boundary, Security, Accessibility.

    Falls back gracefully if the API is unavailable or parsing fails.
    """
    client = _get_client()

    if client:
        # ── Pass 1: extract testable behaviors ──────────────────────────────
        print("[llm_service] Pass 1: extracting testable behaviors…")
        behaviors = _extract_testable_behaviors(client, story_text)
        if not behaviors:
            print("[llm_service] No behaviors extracted; falling back to direct generation.")
            behaviors = []  # Pass 2 will still run using just the story text

        print(f"[llm_service] Extracted {len(behaviors)} behaviors. Running Pass 2…")

        # ── Pass 2: generate exhaustive test cases ───────────────────────────
        try:
            cases = _generate_cases_for_behaviors(client, story_text, behaviors)
            if cases:
                deduped = _deduplicate(cases)
                print(f"[llm_service] Generated {len(cases)} cases → {len(deduped)} after dedup.")
                return deduped
            raise RuntimeError("Pass 2 returned empty list.")
        except Exception as e:
            print(f"[llm_service] generate_test_cases error: {e}")
            raise RuntimeError(f"Failed to generate test cases via AI: {e}")

    raise RuntimeError("LLM client not available for generate_test_cases.")
