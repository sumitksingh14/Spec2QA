"""
§7 — Regression test suite for the Spec2QA v2 generation pipeline.

All tests are fixture-based and mock _stream_response so no live LLM calls are made.
Assertions cover:
  - 25-case hard cap never exceeded
  - CATEGORY_MAX never exceeded per category
  - Skipped categories when no relevant surface
  - High-risk stories include ≥ 1 Security/Negative case with auth keywords
  - covers_behavior_id validity
  - uncovered_behaviors list structure
  - Dedup v2 removes near-duplicates and keeps more specific case
  - Specificity validator flags generic expected_result phrases
  - Risk weight classification
  - Slot allocation constraints (CATEGORY_MIN respected, total ≤ 25)

Run: cd backend && python -m pytest tests/test_pipeline.py -v
"""

import json
import re
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Fixtures — sample stories
# ---------------------------------------------------------------------------

STORIES = {
    "simple_crud": (
        "As a user, I want to create, read, update, and delete product records "
        "so that I can manage inventory.\n\n"
        "Acceptance Criteria:\n"
        "- User can add a new product with name, SKU, and price.\n"
        "- User can view a list of all products.\n"
        "- User can update any product field.\n"
        "- User can delete a product; deleted products no longer appear in the list."
    ),
    "security_sensitive": (
        "As a user, I want to log in to my account using email and password "
        "so that I can access my profile.\n\n"
        "Acceptance Criteria:\n"
        "- User must provide a valid email and password to authenticate.\n"
        "- After 5 failed login attempts, the account must be locked for 15 minutes.\n"
        "- Passwords must be at least 8 characters and include a special character.\n"
        "- Session tokens must expire after 30 minutes of inactivity.\n"
        "- Login form must be protected against SQL injection and CSRF attacks."
    ),
    "ui_heavy": (
        "As a user, I want to fill out a multi-step registration form "
        "so that I can create an account.\n\n"
        "Acceptance Criteria:\n"
        "- Step 1: First name (max 50 chars), last name (max 50 chars), email (valid format).\n"
        "- Step 2: Password (min 8 chars, must contain uppercase, digit, special char).\n"
        "- Step 3: Profile photo upload (max 5 MB, JPEG or PNG only).\n"
        "- All form inputs must be keyboard-navigable.\n"
        "- Error messages must be visible to screen readers via ARIA live regions.\n"
        "- Submit button is disabled until all required fields are valid."
    ),
    "backend_batch_job": (
        "As a system operator, I want a nightly batch job to archive orders older than "
        "90 days to cold storage so that the primary database stays performant.\n\n"
        "Acceptance Criteria:\n"
        "- The job runs at 02:00 UTC every day.\n"
        "- Orders with status 'completed' or 'cancelled' and created_at > 90 days ago are moved.\n"
        "- A summary log is written after each run: count moved, errors, duration.\n"
        "- If the job fails, an alert is sent to the ops team and no partial moves are committed.\n"
        "- The job must complete within 30 minutes."
    ),
    "ambiguous_underspecified": (
        "As a user, I want to search for things so that I can find what I need.\n\n"
        "Notes:\n"
        "- Should be fast.\n"
        "- Results should be relevant."
    ),
}

# ---------------------------------------------------------------------------
# Helpers — build mock LLM responses
# ---------------------------------------------------------------------------

def _make_behaviors(descriptions):
    """Build a minimal Pass 1 JSON response."""
    return json.dumps([
        {"description": d, "source": "explicit_ac" if i < 3 else "inferred"}
        for i, d in enumerate(descriptions)
    ])


def _make_test_cases(n, category="Functional", covers_id=0, expected_result="The record is saved successfully and appears in the list."):
    """Build n test cases for Pass 2 JSON response."""
    cases = []
    for i in range(n):
        cases.append({
            "title": f"Test case {i+1}: {category} scenario",
            "category": category,
            "priority": "Medium",
            "preconditions": "User is logged in",
            "steps": [f"Step {j+1}: perform action {j+1}" for j in range(3)],
            "expected_result": expected_result,
            "covers_behavior_id": covers_id + i,
        })
    return json.dumps(cases)


def _make_25_mixed_cases():
    """25 cases spread across all 5 categories."""
    cats = ["Functional", "Functional", "Functional", "Functional", "Functional",
            "Functional", "Functional", "Functional",
            "Negative", "Negative", "Negative", "Negative", "Negative",
            "Boundary", "Boundary", "Boundary",
            "Security", "Security", "Security",
            "Accessibility", "Accessibility", "Accessibility",
            "Functional", "Negative", "Boundary"]
    cases = []
    for i, cat in enumerate(cats):
        cases.append({
            "title": f"TC-{i+1}: {cat} scenario for feature X",
            "category": cat,
            "priority": "High" if cat == "Security" else "Medium",
            "preconditions": "System is initialized",
            "steps": [f"Navigate to the page", f"Perform action {i}", f"Verify result {i}"],
            "expected_result": f"The system returns HTTP 200 with response body containing '{cat}' confirmation and the record ID.",
            "covers_behavior_id": i % 10,
        })
    return json.dumps(cases)


# ---------------------------------------------------------------------------
# Pure-function unit tests (no mock needed)
# ---------------------------------------------------------------------------

class TestRiskWeightClassification(unittest.TestCase):
    """§3 — _infer_risk_weight keyword logic."""

    def setUp(self):
        from llm_service import _infer_risk_weight
        self.fn = _infer_risk_weight

    def test_auth_keyword_is_high(self):
        self.assertEqual(self.fn("User must authenticate with password"), "high")

    def test_payment_keyword_is_high(self):
        self.assertEqual(self.fn("Process payment via credit card"), "high")

    def test_validate_keyword_is_medium(self):
        self.assertEqual(self.fn("Validate email format before submission"), "medium")

    def test_generic_description_is_low(self):
        self.assertEqual(self.fn("Display the product name on the page"), "low")

    def test_must_keyword_is_high(self):
        self.assertEqual(self.fn("System must complete the action"), "high")


class TestCategoryApplicability(unittest.TestCase):
    """§2 — _classify_category_applicability heuristics."""

    def setUp(self):
        from llm_service import _classify_category_applicability, BehaviorTag
        self.fn = _classify_category_applicability
        self.BehaviorTag = BehaviorTag

    def _b(self, desc, src="inferred", risk="low"):
        return self.BehaviorTag(id=0, description=desc, source=src, risk_weight=risk)

    def test_backend_batch_job_skips_accessibility(self):
        behaviors = [self._b("Run nightly archival job"), self._b("Write summary log")]
        result = self.fn(behaviors, STORIES["backend_batch_job"])
        self.assertFalse(result["Accessibility"]["applicable"],
                         "Batch job story should have Accessibility skipped")

    def test_ui_heavy_story_enables_accessibility(self):
        behaviors = [self._b("User fills out multi-step form"), self._b("Submit button is keyboard-navigable")]
        result = self.fn(behaviors, STORIES["ui_heavy"])
        self.assertTrue(result["Accessibility"]["applicable"])

    def test_security_story_enables_security(self):
        behaviors = [self._b("User must authenticate with password")]
        result = self.fn(behaviors, STORIES["security_sensitive"])
        self.assertTrue(result["Security"]["applicable"])

    def test_crud_story_may_skip_security(self):
        behaviors = [self._b("Create a product"), self._b("Delete a product")]
        result = self.fn(behaviors, STORIES["simple_crud"])
        # Simple CRUD with no auth keywords — Security should be skipped
        self.assertFalse(result["Security"]["applicable"],
                         "Plain CRUD story with no auth keywords should skip Security")

    def test_functional_always_applicable(self):
        behaviors = [self._b("Do something")]
        result = self.fn(behaviors, "As a user I want to do something.")
        self.assertTrue(result["Functional"]["applicable"])
        self.assertTrue(result["Negative"]["applicable"])


class TestSlotAllocation(unittest.TestCase):
    """§1 — _compute_slot_allocation constraints."""

    def setUp(self):
        from llm_service import (
            _compute_slot_allocation, _classify_category_applicability,
            TOTAL_CASE_CAP, CATEGORY_MIN, CATEGORY_MAX, BehaviorTag,
        )
        self.alloc = _compute_slot_allocation
        self.classify = _classify_category_applicability
        self.cap = TOTAL_CASE_CAP
        self.min = CATEGORY_MIN
        self.max = CATEGORY_MAX
        self.BehaviorTag = BehaviorTag

    def _b(self, desc, risk="low"):
        from llm_service import _infer_risk_weight
        return self.BehaviorTag(id=0, description=desc, source="inferred",
                                risk_weight=_infer_risk_weight(desc))

    def test_total_never_exceeds_25(self):
        for story_key, story_text in STORIES.items():
            with self.subTest(story=story_key):
                behaviors = [self._b(f"behavior {i} in {story_key}") for i in range(15)]
                applicability = self.classify(behaviors, story_text)
                allocation = self.alloc(behaviors, applicability)
                self.assertLessEqual(sum(allocation.values()), self.cap,
                                     f"{story_key}: total {sum(allocation.values())} > 25")

    def test_each_applicable_category_gets_minimum(self):
        behaviors = [self._b("must authenticate"), self._b("validate form input")]
        applicability = self.classify(behaviors, STORIES["security_sensitive"])
        allocation = self.alloc(behaviors, applicability)
        for cat, status in applicability.items():
            if status["applicable"]:
                self.assertGreaterEqual(allocation.get(cat, 0), self.min,
                                        f"{cat} applicable but has {allocation.get(cat, 0)} < CATEGORY_MIN")

    def test_no_category_exceeds_maximum(self):
        behaviors = [self._b(f"functional step {i}") for i in range(30)]
        applicability = self.classify(behaviors, "As a user I want to list items.")
        allocation = self.alloc(behaviors, applicability)
        for cat, slots in allocation.items():
            self.assertLessEqual(slots, self.max, f"{cat} has {slots} > CATEGORY_MAX")

    def test_skipped_category_gets_zero_slots(self):
        behaviors = [self._b("run batch archival job"), self._b("write log file")]
        applicability = self.classify(behaviors, STORIES["backend_batch_job"])
        allocation = self.alloc(behaviors, applicability)
        if not applicability["Accessibility"]["applicable"]:
            self.assertEqual(allocation.get("Accessibility", 0), 0,
                             "Skipped Accessibility should have 0 slots")


class TestSpecificityValidator(unittest.TestCase):
    """§4 — _validate_specificity flags generic expected results."""

    def setUp(self):
        from llm_service import _validate_specificity
        self.fn = _validate_specificity

    def _tc(self, category, expected_result, steps=None):
        return {
            "title": "A test case",
            "category": category,
            "priority": "Medium",
            "steps": steps or ["Step 1", "Step 2"],
            "expected_result": expected_result,
            "covers_behavior_id": 0,
        }

    def test_generic_phrase_is_flagged(self):
        cases = [self._tc("Functional", "The system should work correctly.")]
        valid, flagged = self.fn(cases)
        self.assertEqual(len(flagged), 1)
        self.assertIn("Generic", flagged[0]["_flag_reason"])

    def test_specific_result_passes(self):
        cases = [self._tc("Functional", "The API returns HTTP 201 with a JSON body containing the new record ID.")]
        valid, flagged = self.fn(cases)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(flagged), 0)

    def test_boundary_without_numbers_is_flagged(self):
        cases = [self._tc("Boundary", "The system rejects the input.", steps=["Enter a very long name"])]
        valid, flagged = self.fn(cases)
        self.assertEqual(len(flagged), 1)
        self.assertIn("Boundary", flagged[0]["_flag_reason"])

    def test_boundary_with_numbers_passes(self):
        cases = [self._tc("Boundary", "The system rejects the name when it exceeds 255 characters.",
                           steps=["Enter a name with exactly 256 characters"])]
        valid, flagged = self.fn(cases)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(flagged), 0)

    def test_multiple_flags_captured(self):
        cases = [
            self._tc("Functional", "Works as expected."),
            self._tc("Boundary", "System behaves as expected.", steps=["Do something"]),
            self._tc("Negative", "HTTP 400 is returned with message 'Email already exists'."),
        ]
        valid, flagged = self.fn(cases)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(flagged), 2)


class TestDedupV2(unittest.TestCase):
    """§6 — _deduplicate_v2 Jaccard + title dedup."""

    def setUp(self):
        from llm_service import _deduplicate_v2
        self.fn = _deduplicate_v2

    def _tc(self, title, steps, expected_result, covers_id=0):
        return {
            "title": title,
            "category": "Functional",
            "priority": "Medium",
            "preconditions": "",
            "steps": steps,
            "expected_result": expected_result,
            "covers_behavior_id": covers_id,
        }

    def test_exact_title_dedup_keeps_more_specific(self):
        short = self._tc("Login test", ["Go to login", "Click submit"], "System logs in.")
        long  = self._tc("Login test", ["Navigate to /login", "Enter email", "Enter password", "Click Submit"], "User is redirected to /dashboard and session cookie is set.")
        result = self.fn([short, long])
        self.assertEqual(len(result), 1)
        self.assertIn("dashboard", result[0]["expected_result"].lower())

    def test_high_jaccard_near_duplicate_removed(self):
        tc1 = self._tc("Submit form with valid data",
                       ["Open the form", "Enter valid name", "Enter valid email", "Click submit"],
                       "The form submission returns HTTP 200 and a success message is displayed.")
        tc2 = self._tc("Submit form with correct data",  # different title, same intent
                       ["Open the form", "Enter valid name", "Enter valid email", "Click submit"],
                       "The form submission returns HTTP 200 and a confirmation message is displayed.")
        result = self.fn([tc1, tc2])
        self.assertEqual(len(result), 1)

    def test_distinct_cases_preserved(self):
        tc1 = self._tc("Login with valid credentials",
                       ["Enter email", "Enter password", "Click login"],
                       "User is redirected to dashboard; session token is issued.")
        tc2 = self._tc("Login with invalid password",
                       ["Enter valid email", "Enter wrong password", "Click login"],
                       "System returns HTTP 401 and displays 'Invalid credentials'.")
        result = self.fn([tc1, tc2])
        self.assertEqual(len(result), 2)


class TestCoverageGaps(unittest.TestCase):
    """§5 — _compute_coverage_gaps identifies uncovered behaviors."""

    def setUp(self):
        from llm_service import _compute_coverage_gaps, BehaviorTag
        self.fn = _compute_coverage_gaps
        self.BehaviorTag = BehaviorTag

    def test_uncovered_behaviors_identified(self):
        behaviors = [
            self.BehaviorTag(id=0, description="Login happy path", source="explicit_ac", risk_weight="high"),
            self.BehaviorTag(id=1, description="Logout clears session", source="explicit_ac", risk_weight="medium"),
            self.BehaviorTag(id=2, description="Rate limiting on login", source="inferred", risk_weight="high"),
        ]
        test_cases = [
            {"covers_behavior_id": 0, "title": "TC1", "category": "Functional"},
            {"covers_behavior_id": 1, "title": "TC2", "category": "Negative"},
            # behavior 2 has no test case
        ]
        uncovered = self.fn(behaviors, test_cases)
        self.assertEqual(len(uncovered), 1)
        self.assertEqual(uncovered[0]["id"], 2)

    def test_uncovered_sorted_by_risk(self):
        behaviors = [
            self.BehaviorTag(id=0, description="Low risk feature", source="inferred", risk_weight="low"),
            self.BehaviorTag(id=1, description="High risk auth", source="explicit_ac", risk_weight="high"),
            self.BehaviorTag(id=2, description="Medium risk validation", source="explicit_description", risk_weight="medium"),
        ]
        uncovered = self.fn(behaviors, [])
        self.assertEqual(uncovered[0]["risk_weight"], "high")
        self.assertEqual(uncovered[1]["risk_weight"], "medium")
        self.assertEqual(uncovered[2]["risk_weight"], "low")

    def test_no_uncovered_when_all_covered(self):
        behaviors = [
            self.BehaviorTag(id=0, description="Feature A", source="explicit_ac", risk_weight="high"),
        ]
        test_cases = [{"covers_behavior_id": 0, "title": "TC1", "category": "Functional"}]
        uncovered = self.fn(behaviors, test_cases)
        self.assertEqual(uncovered, [])


# ---------------------------------------------------------------------------
# Integration-level tests (mock LLM, full pipeline)
# ---------------------------------------------------------------------------

class TestGeneratePipelineIntegration(unittest.TestCase):
    """
    §7 — End-to-end pipeline tests with mocked _stream_response.
    Validates: hard cap, security coverage, accessibility skip, uncovered behaviors.
    """

    def _run_pipeline(self, story_text, mock_responses):
        """
        Run generate_test_cases with a queue of mock _stream_response return values.
        mock_responses: list of strings returned sequentially per call.
        """
        from llm_service import generate_test_cases
        call_count = [0]

        def fake_stream(client, messages, temperature=0.6, max_retries=3):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(mock_responses):
                return mock_responses[idx]
            return "[]"

        with patch("llm_service._stream_response", side_effect=fake_stream), \
             patch("llm_service._get_client", return_value=MagicMock()):
            return generate_test_cases(story_text)

    def test_hard_cap_never_exceeded(self):
        """25 cases from Pass 2 should never result in >25 in output."""
        behaviors_json = _make_behaviors([f"behavior {i}" for i in range(10)])
        gaps_json = "[]"
        cases_json = _make_25_mixed_cases()

        result = self._run_pipeline(
            STORIES["simple_crud"],
            [behaviors_json, gaps_json, cases_json],
        )
        self.assertLessEqual(len(result["test_cases"]), 25,
                             f"Output has {len(result['test_cases'])} test cases, expected ≤ 25")

    def test_security_story_includes_security_or_negative_case(self):
        """A security-sensitive story must include ≥ 1 Security or Negative case."""
        behaviors_json = _make_behaviors([
            "User must authenticate with valid password",
            "Account locked after 5 failed login attempts",
            "Session token expires after inactivity",
        ])
        gaps_json = "[]"
        # Build distinct cases per category so dedup doesn't collapse them
        cases = [
            {
                "title": "Login with valid email and password",
                "category": "Functional",
                "priority": "High",
                "preconditions": "User has a registered account",
                "steps": ["Navigate to /login", "Enter valid email", "Enter correct password", "Click Login"],
                "expected_result": "User is redirected to /dashboard; a session cookie with HttpOnly flag is set.",
                "covers_behavior_id": 0,
            },
            {
                "title": "Login fails after 5 consecutive wrong passwords",
                "category": "Negative",
                "priority": "High",
                "preconditions": "User account exists and is not locked",
                "steps": [
                    "Attempt login with wrong password 5 times in a row",
                    "Attempt a 6th login with the correct password",
                ],
                "expected_result": "After the 5th failed attempt the account is locked; the 6th attempt returns HTTP 403 with message 'Account locked for 15 minutes'.",
                "covers_behavior_id": 1,
            },
            {
                "title": "SQL injection in login form is rejected",
                "category": "Security",
                "priority": "High",
                "preconditions": "Login page is accessible",
                "steps": [
                    "Enter \" OR 1=1 --  in the email field",
                    "Enter any value in the password field",
                    "Click Login",
                ],
                "expected_result": "Server returns HTTP 400 with body 'Invalid email format'; no DB query is executed with the injected payload.",
                "covers_behavior_id": 2,
            },
        ]
        result_json = json.dumps(cases)

        result = self._run_pipeline(
            STORIES["security_sensitive"],
            [behaviors_json, gaps_json, result_json],
        )
        cats = [tc["category"] for tc in result["test_cases"]]
        self.assertTrue(
            "Security" in cats or "Negative" in cats,
            "Security story must have at least one Security or Negative test case"
        )

    def test_backend_batch_job_accessibility_skipped(self):
        """Batch job story: Accessibility should appear in skipped_categories."""
        behaviors_json = _make_behaviors([
            "Run nightly archival at 02:00 UTC",
            "Move completed/cancelled orders older than 90 days",
            "Write summary log after each run",
        ])
        gaps_json = "[]"
        cases_json = json.dumps([
            {
                "title": "Archive job runs at scheduled time",
                "category": "Functional",
                "priority": "High",
                "preconditions": "System time is 02:00 UTC",
                "steps": ["Trigger the cron job", "Wait for completion"],
                "expected_result": "Job completes within 30 minutes and summary log contains moved count.",
                "covers_behavior_id": 0,
            },
            {
                "title": "Alert sent on job failure",
                "category": "Negative",
                "priority": "High",
                "preconditions": "Job is configured to run",
                "steps": ["Simulate DB timeout during archive run"],
                "expected_result": "Ops team receives email alert within 2 minutes; no partial moves are committed.",
                "covers_behavior_id": 2,
            },
        ])

        result = self._run_pipeline(
            STORIES["backend_batch_job"],
            [behaviors_json, gaps_json, cases_json],
        )
        self.assertIn("Accessibility", result["skipped_categories"],
                      "Backend batch job should skip Accessibility")

    def test_uncovered_behaviors_returned(self):
        """Ambiguous story generates uncovered_behaviors for behaviors with no test case."""
        behaviors_json = _make_behaviors([
            "User can search for items",
            "Results are relevant to the query",
            "Search is fast (< 500ms)",
            "Pagination is supported for large result sets",
        ])
        gaps_json = '["Error state when no results found"]'
        # Only cover behaviors 0 and 1 — leave 2, 3, 4 uncovered
        cases_json = json.dumps([
            {
                "title": "Search returns results for valid query",
                "category": "Functional",
                "priority": "High",
                "preconditions": "Search index is populated",
                "steps": ["Enter 'widget' in search box", "Click Search"],
                "expected_result": "Results page displays at least 1 item matching 'widget'.",
                "covers_behavior_id": 0,
            },
            {
                "title": "Search results ordered by relevance score",
                "category": "Functional",
                "priority": "Medium",
                "preconditions": "Search index is populated",
                "steps": ["Enter a query", "Inspect result ordering"],
                "expected_result": "First result has the highest relevance score; items are sorted descending by score.",
                "covers_behavior_id": 1,
            },
        ])

        result = self._run_pipeline(
            STORIES["ambiguous_underspecified"],
            [behaviors_json, gaps_json, cases_json],
        )
        self.assertGreater(len(result["uncovered_behaviors"]), 0,
                           "Ambiguous story should have uncovered behaviors")

    def test_covers_behavior_id_is_valid_index(self):
        """Every test case's covers_behavior_id must be present and be an integer."""
        behaviors_json = _make_behaviors([f"AC{i}" for i in range(5)])
        gaps_json = "[]"
        cases_json = _make_test_cases(5, category="Functional", covers_id=0)

        result = self._run_pipeline(
            STORIES["simple_crud"],
            [behaviors_json, gaps_json, cases_json],
        )
        for tc in result["test_cases"]:
            self.assertIn("covers_behavior_id", tc,
                          f"Missing covers_behavior_id on: {tc.get('title')}")
            self.assertIsInstance(tc["covers_behavior_id"], int)

    def test_generation_meta_fields_present(self):
        """generation_meta must include key diagnostic fields."""
        behaviors_json = _make_behaviors(["Create product", "Delete product"])
        gaps_json = "[]"
        cases_json = _make_test_cases(3, category="Functional", covers_id=0)

        result = self._run_pipeline(
            STORIES["simple_crud"],
            [behaviors_json, gaps_json, cases_json],
        )
        meta = result.get("generation_meta", {})
        self.assertIn("behaviors_extracted", meta)
        self.assertIn("slot_allocation", meta)
        self.assertIn("skipped_categories", meta)


if __name__ == "__main__":
    unittest.main()
