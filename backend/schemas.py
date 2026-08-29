from pydantic import BaseModel
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime

# ---------------------------------------------------------------------------
# Story schemas (unchanged from v1)
# ---------------------------------------------------------------------------

class StoryBase(BaseModel):
    title: str
    description: str
    story_type: Optional[str] = None

class StoryCreate(StoryBase):
    pass

class Story(StoryBase):
    id: int
    created_at: datetime
    clarified_description: Optional[str] = None
    # New additive fields — present when story has been generated with v2 pipeline
    generation_meta_json: Optional[str] = None

    class Config:
        from_attributes = True

class ClarificationRequest(BaseModel):
    questions: List[str]
    missing_elements: List[str]
    extracted_entities: dict

# ---------------------------------------------------------------------------
# Test Case schemas (unchanged from v1)
# ---------------------------------------------------------------------------

class TestCaseBase(BaseModel):
    title: str
    category: str
    priority: str
    preconditions: Optional[str] = None
    steps: List[str]
    expected_result: str
    linked_ac_ids: List[int] = []

class TestCase(TestCaseBase):
    id: int
    story_id: int
    sequence_id: str
    status: str

    class Config:
        from_attributes = True

class GenerateTestCasesRequest(BaseModel):
    story_id: int
    clarified_description: Optional[str] = None
    llm_provider: Optional[str] = None

# ---------------------------------------------------------------------------
# §3 / §1 / §5 — New additive response schemas
# ---------------------------------------------------------------------------

class BehaviorTag(BaseModel):
    """A single testable behavior extracted from Pass 1 (§3)."""
    id: int
    description: str
    source: Literal["explicit_ac", "explicit_description", "inferred"]
    risk_weight: Literal["high", "medium", "low"]

class CategoryStatus(BaseModel):
    """Applicability and slot allocation for one test category (§2, §1)."""
    applicable: bool
    reason: str
    allocated_slots: int

class GenerateTestCasesResponse(BaseModel):
    """
    Response from POST /api/generate/manual-tests.
    All fields beyond message/count/test_cases are additive — existing
    frontend code consuming only test_cases continues to work.
    """
    message: str
    count: int
    test_cases: List[TestCase]

    # §5 — behaviors from Pass 1 with zero associated test cases, ranked by risk_weight
    uncovered_behaviors: List[BehaviorTag] = []

    # §2 / §1 — per-category applicability and slot allocation
    category_allocation: Dict[str, CategoryStatus] = {}

    # §2 — categories skipped because no relevant surface was detected
    skipped_categories: List[str] = []

    # Diagnostic metadata (behavior counts, passes run, allocation used)
    generation_meta: Dict[str, Any] = {}
