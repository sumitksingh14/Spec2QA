from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, DateTime, Boolean
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import database
import json


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------

class Story(database.Base):
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    story_type = Column(String, nullable=True)  # UI, API, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    clarified_description = Column(Text, nullable=True)

    # v2 pipeline: stores JSON blob of uncovered_behaviors, category_allocation,
    # skipped_categories, generation_meta so StoryDetails can show them on reload.
    # Neon Postgres: run `ALTER TABLE stories ADD COLUMN generation_meta_json TEXT;`
    # if the column doesn't exist yet (SQLite will get it automatically via create_all).
    generation_meta_json = Column(Text, nullable=True)

    # Feature 3 — Pre-generation scope control
    # JSON list of AC IDs / line indices excluded from extraction
    excluded_ac_ids_json = Column(Text, nullable=True)

    # Feature 4 — Story versioning & diffing
    content_hash = Column(Text, nullable=True)   # SHA-256 of normalized description
    version = Column(Integer, default=1)          # incremented on changed resubmit

    acceptance_criteria = relationship("AcceptanceCriterion", back_populates="story", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="story", cascade="all, delete-orphan")
    generation_runs = relationship("GenerationRun", back_populates="story", cascade="all, delete-orphan")
    generation_jobs = relationship("GenerationJob", back_populates="story", cascade="all, delete-orphan")
    share_tokens = relationship("ShareToken", back_populates="story", cascade="all, delete-orphan")
    qa_exchanges = relationship("QAExchange", back_populates="story", cascade="all, delete-orphan")
    webhook_config = relationship("WebhookConfig", back_populates="story", uselist=False, cascade="all, delete-orphan")

    @property
    def excluded_ac_ids(self):
        return json.loads(self.excluded_ac_ids_json) if self.excluded_ac_ids_json else []

    @excluded_ac_ids.setter
    def excluded_ac_ids(self, value):
        self.excluded_ac_ids_json = json.dumps(value)


# ---------------------------------------------------------------------------
# AcceptanceCriterion
# ---------------------------------------------------------------------------

class AcceptanceCriterion(database.Base):
    __tablename__ = "acceptance_criteria"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    description = Column(Text)

    story = relationship("Story", back_populates="acceptance_criteria")


# ---------------------------------------------------------------------------
# Feature 4 — GenerationRun
# Each POST /api/generate/manual-tests creates one row.
# TestCase.run_id references the specific run.
# Feature 14 metrics are stored on the run.
# ---------------------------------------------------------------------------

class GenerationRun(database.Base):
    __tablename__ = "generation_runs"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    generation_meta_json = Column(Text, nullable=True)

    # Feature 14 — Cost / latency metrics
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    wall_time_ms = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    provider = Column(String, nullable=True)

    story = relationship("Story", back_populates="generation_runs")
    test_cases = relationship("TestCase", back_populates="run")
    qa_exchanges = relationship("QAExchange", back_populates="run")
    execution_results = relationship("ExecutionResult", back_populates="run")


# ---------------------------------------------------------------------------
# TestCase
# ---------------------------------------------------------------------------

class TestCase(database.Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    sequence_id = Column(String, index=True)  # e.g. TC-123-01
    title = Column(String)
    category = Column(String)  # Functional, Negative, Boundary, etc.
    priority = Column(String)  # Critical, High, Medium, Low
    preconditions = Column(Text, nullable=True)
    steps_json = Column(Text)  # JSON string of steps
    expected_result = Column(Text)
    status = Column(String, default="Not Run")

    # Store linked AC IDs as JSON for simplicity in MVP
    linked_ac_ids_json = Column(Text, nullable=True)

    # Feature 1 — Per-case regeneration: stores the BehaviorTag this case covers
    behavior_context_json = Column(Text, nullable=True)

    # Feature 4 — Which generation run produced this case
    run_id = Column(Integer, ForeignKey("generation_runs.id"), nullable=True)

    # Feature 9 — Approval state & assignment
    approval_status = Column(String, default="Draft")  # Draft | Reviewed | Approved
    assigned_to = Column(String, nullable=True)

    story = relationship("Story", back_populates="test_cases")
    run = relationship("GenerationRun", back_populates="test_cases")
    comments = relationship("Comment", back_populates="test_case", cascade="all, delete-orphan")
    execution_results = relationship("ExecutionResult", back_populates="test_case", cascade="all, delete-orphan")

    @property
    def steps(self):
        return json.loads(self.steps_json) if self.steps_json else []

    @steps.setter
    def steps(self, value):
        self.steps_json = json.dumps(value)

    @property
    def linked_ac_ids(self):
        return json.loads(self.linked_ac_ids_json) if self.linked_ac_ids_json else []

    @linked_ac_ids.setter
    def linked_ac_ids(self, value):
        self.linked_ac_ids_json = json.dumps(value)

    @property
    def behavior_context(self):
        return json.loads(self.behavior_context_json) if self.behavior_context_json else None

    @behavior_context.setter
    def behavior_context(self, value):
        self.behavior_context_json = json.dumps(value) if value is not None else None


# ---------------------------------------------------------------------------
# Feature 6 — ShareToken
# ---------------------------------------------------------------------------

class ShareToken(database.Base):
    __tablename__ = "share_tokens"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    is_revoked = Column(Boolean, default=False)

    story = relationship("Story", back_populates="share_tokens")


# ---------------------------------------------------------------------------
# Feature 2 — QAExchange (post-generation Q&A)
# ---------------------------------------------------------------------------

class QAExchange(database.Base):
    __tablename__ = "qa_exchanges"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    run_id = Column(Integer, ForeignKey("generation_runs.id"), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    story = relationship("Story", back_populates="qa_exchanges")
    run = relationship("GenerationRun", back_populates="qa_exchanges")


# ---------------------------------------------------------------------------
# Feature 8 — WebhookConfig (Slack notification)
# ---------------------------------------------------------------------------

class WebhookConfig(database.Base):
    __tablename__ = "webhook_configs"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"), unique=True)
    slack_webhook_url = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)

    story = relationship("Story", back_populates="webhook_config")


# ---------------------------------------------------------------------------
# Feature 10 — Comment
# ---------------------------------------------------------------------------

class Comment(database.Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id"))
    author = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    test_case = relationship("TestCase", back_populates="comments")


# ---------------------------------------------------------------------------
# Feature 11 — ExecutionResult
# ---------------------------------------------------------------------------

class ExecutionResult(database.Base):
    __tablename__ = "execution_results"

    id = Column(Integer, primary_key=True, index=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id"))
    run_id = Column(Integer, ForeignKey("generation_runs.id"), nullable=True)
    status = Column(String, default="Not Run")   # Not Run | Pass | Fail | Blocked
    actual_result = Column(Text, nullable=True)
    executed_by = Column(String, nullable=True)
    executed_at = Column(DateTime, nullable=True)

    # Feature 12 — Jira bug link
    jira_bug_key = Column(String, nullable=True)

    test_case = relationship("TestCase", back_populates="execution_results")
    run = relationship("GenerationRun", back_populates="execution_results")


# ---------------------------------------------------------------------------
# Async generation job tracker (fixes Vercel 504 / maxDuration timeout)
# ---------------------------------------------------------------------------

class GenerationJob(database.Base):
    """
    Tracks in-progress and completed LLM generation jobs.
    The POST /api/generate/manual-tests endpoint creates a job and returns
    its job_id immediately. A background thread runs the pipeline and updates
    this row. The frontend polls GET /api/generate/status/{job_id}.
    """
    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True)          # UUID job_id
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=True)
    status = Column(String, default="pending")     # pending | running | done | failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    # Serialised request payload so the background thread can reconstruct it
    request_json = Column(Text, nullable=True)

    story = relationship("Story", back_populates="generation_jobs")

