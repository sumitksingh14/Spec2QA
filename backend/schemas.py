from pydantic import BaseModel
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime

# ---------------------------------------------------------------------------
# Story schemas
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
    generation_meta_json: Optional[str] = None
    excluded_ac_ids_json: Optional[str] = None
    content_hash: Optional[str] = None
    version: Optional[int] = 1

    class Config:
        from_attributes = True

class ClarificationRequest(BaseModel):
    questions: List[str]
    missing_elements: List[str]
    extracted_entities: dict

# ---------------------------------------------------------------------------
# TestCase schemas
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
    behavior_context_json: Optional[str] = None
    run_id: Optional[int] = None
    approval_status: Optional[str] = "Draft"
    assigned_to: Optional[str] = None

    class Config:
        from_attributes = True

class TestCaseUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    preconditions: Optional[str] = None
    steps: Optional[List[str]] = None
    expected_result: Optional[str] = None
    assigned_to: Optional[str] = None

class GenerateTestCasesRequest(BaseModel):
    story_id: int
    clarified_description: Optional[str] = None
    llm_provider: Optional[str] = None
    # Feature 3 — scope control
    excluded_ac_ids: Optional[List[int]] = []

# Feature 1 — regeneration
class RegenerateRequest(BaseModel):
    instruction: Optional[str] = None

# Feature 9 — approval
class ApprovalUpdate(BaseModel):
    status: Literal["Draft", "Reviewed", "Approved"]

# ---------------------------------------------------------------------------
# Generation pipeline schemas
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
    message: str
    count: int
    test_cases: List[TestCase]
    uncovered_behaviors: List[BehaviorTag] = []
    category_allocation: Dict[str, CategoryStatus] = {}
    skipped_categories: List[str] = []
    generation_meta: Dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Feature 4 — Story versioning & diffing
# ---------------------------------------------------------------------------

class GenerationRun(BaseModel):
    id: int
    story_id: int
    version: int
    created_at: datetime
    generation_meta_json: Optional[str] = None
    prompt_tokens: Optional[int] = 0
    completion_tokens: Optional[int] = 0
    wall_time_ms: Optional[int] = 0
    retry_count: Optional[int] = 0
    provider: Optional[str] = None

    class Config:
        from_attributes = True

class DiffLine(BaseModel):
    line_type: Literal["added", "removed", "unchanged"]
    content: str

class TestCaseDiffStatus(BaseModel):
    test_case_id: int
    sequence_id: str
    title: str
    validity: Literal["still_valid", "possibly_stale", "obsolete"]
    reason: str

class DiffResult(BaseModel):
    old_version: int
    new_version: int
    diff_lines: List[DiffLine]
    test_case_statuses: List[TestCaseDiffStatus]
    has_changes: bool

# ---------------------------------------------------------------------------
# Feature 6 — Shareable read-only links
# ---------------------------------------------------------------------------

class ShareTokenCreate(BaseModel):
    expires_in_days: Optional[int] = None  # None = never expires

class ShareTokenOut(BaseModel):
    id: int
    story_id: int
    token: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_revoked: bool
    share_url: Optional[str] = None

    class Config:
        from_attributes = True

# ---------------------------------------------------------------------------
# Feature 2 — Post-generation Q&A
# ---------------------------------------------------------------------------

class QAQuestion(BaseModel):
    question: str

class QAExchange(BaseModel):
    id: int
    story_id: int
    run_id: Optional[int] = None
    question: str
    answer: str
    created_at: datetime

    class Config:
        from_attributes = True

# ---------------------------------------------------------------------------
# Feature 8 — Slack notification / webhook config
# ---------------------------------------------------------------------------

class WebhookConfigIn(BaseModel):
    slack_webhook_url: str
    enabled: Optional[bool] = True

class WebhookConfigOut(BaseModel):
    id: int
    story_id: int
    slack_webhook_url: str
    enabled: bool

    class Config:
        from_attributes = True

# ---------------------------------------------------------------------------
# Feature 10 — Comment threads
# ---------------------------------------------------------------------------

class CommentCreate(BaseModel):
    author: str
    text: str

class Comment(BaseModel):
    id: int
    test_case_id: int
    author: str
    text: str
    created_at: datetime

    class Config:
        from_attributes = True

# ---------------------------------------------------------------------------
# Feature 11 — Manual execution mode
# ---------------------------------------------------------------------------

class ExecutionResultIn(BaseModel):
    status: Literal["Not Run", "Pass", "Fail", "Blocked"]
    actual_result: Optional[str] = None
    executed_by: Optional[str] = None

class ExecutionResultOut(BaseModel):
    id: int
    test_case_id: int
    run_id: Optional[int] = None
    status: str
    actual_result: Optional[str] = None
    executed_by: Optional[str] = None
    executed_at: Optional[datetime] = None
    jira_bug_key: Optional[str] = None

    class Config:
        from_attributes = True

# ---------------------------------------------------------------------------
# Feature 12 — Jira bug creation
# ---------------------------------------------------------------------------

class JiraBugRequest(BaseModel):
    actual_result: str
    project_key: Optional[str] = None

class JiraBugResponse(BaseModel):
    key: Optional[str] = None
    url: Optional[str] = None
    prefilled_payload: Optional[Dict[str, Any]] = None

# ---------------------------------------------------------------------------
# Feature 5 — Pattern suggestions
# ---------------------------------------------------------------------------

class PatternSuggestion(BaseModel):
    tag: str
    count: int
    example_story_ids: List[int]

class PatternSuggestionsResponse(BaseModel):
    suggestions: List[PatternSuggestion]

# ---------------------------------------------------------------------------
# Feature 14 — Admin metrics
# ---------------------------------------------------------------------------

class RunMetrics(BaseModel):
    run_id: int
    story_id: int
    story_title: Optional[str] = None
    version: int
    created_at: datetime
    provider: Optional[str] = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    wall_time_ms: int
    retry_count: int

# ---------------------------------------------------------------------------
# Feature 15 — Coverage trend
# ---------------------------------------------------------------------------

class CoverageTrendPoint(BaseModel):
    week: str  # ISO week string e.g. "2026-W35"
    total_stories: int
    stories_with_uncovered: int
    pct_covered: float  # 0–100
