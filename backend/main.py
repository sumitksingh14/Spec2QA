"""
main.py — Spec2QA FastAPI application.

Routes:
  Existing:
    POST   /api/analyze
    POST   /api/generate/manual-tests
    GET    /api/stories
    GET    /api/stories/{story_id}
    DELETE /api/stories/{story_id}
    GET    /api/stories/{story_id}/test-cases

  Feature 1 — Per-case regeneration:
    POST   /api/test-cases/{case_id}/regenerate
    PATCH  /api/test-cases/{case_id}
    DELETE /api/test-cases/{case_id}

  Feature 2 — Post-generation Q&A:
    POST   /api/stories/{story_id}/qa
    GET    /api/stories/{story_id}/qa

  Feature 4 — Story versioning:
    GET    /api/stories/{story_id}/runs
    GET    /api/stories/{story_id}/diff   (compare current vs last)

  Feature 5 — Pattern suggestions:
    GET    /api/stories/{story_id}/pattern-suggestions

  Feature 6 — Shareable links:
    POST   /api/stories/{story_id}/share
    GET    /api/share/{token}
    DELETE /api/share/{token}

  Feature 7 — Markdown export (client-side; no new route)

  Feature 8 — Slack webhook:
    PUT    /api/stories/{story_id}/webhook
    GET    /api/stories/{story_id}/webhook

  Feature 9 — Approval:
    PATCH  /api/test-cases/{case_id}/approval

  Feature 10 — Comments:
    POST   /api/test-cases/{case_id}/comments
    GET    /api/test-cases/{case_id}/comments

  Feature 11 — Execution:
    GET    /api/stories/{story_id}/execution
    PUT    /api/test-cases/{case_id}/execution

  Feature 12 — Jira bug:
    POST   /api/test-cases/{case_id}/create-jira-bug

  Feature 14 — Admin metrics:
    GET    /api/admin/metrics

  Feature 15 — Coverage trend:
    GET    /api/analytics/coverage-trend
"""

import hashlib
import difflib
import json
import os
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
import database
import llm_service

# Create DB tables & auto-migrate missing columns
database.init_db()

app = FastAPI(title="Spec2QA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In prod, replace with frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")


def _story_or_404(story_id: int, db: Session) -> models.Story:
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _testcase_or_404(case_id: int, db: Session) -> models.TestCase:
    tc = db.query(models.TestCase).filter(models.TestCase.id == case_id).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    return tc


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()


def _fire_slack_webhook(webhook_url: str, payload: dict) -> None:
    """Feature 8 — Fire-and-forget Slack webhook. Errors are logged, not raised."""
    try:
        httpx.post(webhook_url, json=payload, timeout=5.0)
    except Exception as e:
        print(f"[main] Slack webhook error: {e}")


# ---------------------------------------------------------------------------
# Existing routes (enhanced)
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
def analyze_story(story: schemas.StoryCreate, db: Session = Depends(database.get_db)):
    """Analyze story and persist it. Returns clarification questions + extracted entities."""
    content_hash = _hash_text(story.description)

    # Check if we've seen this story (same title) before — support versioning (#4)
    existing = db.query(models.Story).filter(models.Story.title == story.title).first()
    version = 1
    if existing:
        version = (existing.version or 1) + 1 if existing.content_hash != content_hash else (existing.version or 1)

    db_story = models.Story(
        title=story.title,
        description=story.description,
        story_type=story.story_type,
        content_hash=content_hash,
        version=version,
    )
    db.add(db_story)
    db.commit()
    db.refresh(db_story)

    analysis_result = llm_service.analyze_story(story.description)
    return {"story_id": db_story.id, "version": version, **analysis_result}


@app.post("/api/generate/manual-tests")
def generate_tests(
    request: schemas.GenerateTestCasesRequest,
    db: Session = Depends(database.get_db),
):
    """Generate test cases using the two-pass pipeline."""
    db_story = _story_or_404(request.story_id, db)
    story_text = request.clarified_description or db_story.description

    if request.clarified_description and request.clarified_description != db_story.description:
        db_story.clarified_description = request.clarified_description

    # Feature 3 — persist exclusion choices
    if request.excluded_ac_ids:
        db_story.excluded_ac_ids_json = json.dumps(request.excluded_ac_ids)

    # Call LLM pipeline
    generation_result = llm_service.generate_test_cases(
        story_text,
        provider_override=request.llm_provider,
        excluded_ac_ids=request.excluded_ac_ids or [],
    )

    test_cases_data = generation_result["test_cases"]
    uncovered_behaviors = generation_result.get("uncovered_behaviors", [])
    category_allocation = generation_result.get("category_allocation", {})
    skipped_categories = generation_result.get("skipped_categories", [])
    generation_meta = generation_result.get("generation_meta", {})
    run_metrics = generation_result.get("metrics", {})

    # Feature 4 — Create a GenerationRun record
    db_run = models.GenerationRun(
        story_id=db_story.id,
        version=db_story.version or 1,
        generation_meta_json=json.dumps({
            "uncovered_behaviors": uncovered_behaviors,
            "category_allocation": {
                cat: {
                    "applicable": s.get("applicable", True),
                    "reason": s.get("reason", ""),
                    "allocated_slots": s.get("allocated_slots", 0),
                }
                for cat, s in category_allocation.items()
            },
            "skipped_categories": skipped_categories,
            "generation_meta": generation_meta,
        }),
        # Feature 14 metrics
        wall_time_ms=run_metrics.get("wall_time_ms", 0),
        retry_count=run_metrics.get("retry_count", 0),
        provider=run_metrics.get("provider_used", request.llm_provider or ""),
    )
    db.add(db_run)
    db.flush()  # get db_run.id

    # Persist coverage/gap metadata to Story for reload
    db_story.generation_meta_json = db_run.generation_meta_json

    generated_tests = []
    for i, tc_data in enumerate(test_cases_data, start=1):
        # Feature 1 — find and store the BehaviorTag context for this case
        covers_id = tc_data.get("covers_behavior_id")
        behavior_ctx = None
        if covers_id is not None:
            # generation_meta carries behaviors as part of the result; look up from uncovered + covered
            # We store the behavior from generation_meta if available
            behavior_ctx = {"covers_behavior_id": covers_id}

        db_tc = models.TestCase(
            story_id=db_story.id,
            run_id=db_run.id,
            sequence_id=f"TC-{db_story.id}-{i:02d}",
            title=tc_data.get("title", ""),
            category=tc_data.get("category", "Functional"),
            priority=tc_data.get("priority", "Medium"),
            preconditions=tc_data.get("preconditions", ""),
            steps=tc_data.get("steps", []),
            expected_result=tc_data.get("expected_result", ""),
            behavior_context_json=json.dumps(behavior_ctx) if behavior_ctx else None,
        )
        db.add(db_tc)
        generated_tests.append(db_tc)

    db.commit()

    for tc in generated_tests:
        db.refresh(tc)

    # Feature 8 — Fire Slack webhook if configured for this story
    wh = db.query(models.WebhookConfig).filter(
        models.WebhookConfig.story_id == db_story.id,
        models.WebhookConfig.enabled == True,
    ).first()
    if wh:
        cat_breakdown = {
            cat: s.get("allocated_slots", 0)
            for cat, s in category_allocation.items()
            if s.get("applicable", True)
        }
        slack_payload = {
            "text": (
                f"✅ *Spec2QA* — Generation complete for *{db_story.title}*\n"
                f"• {len(generated_tests)} test cases generated\n"
                f"• Categories: {', '.join(f'{k}: {v}' for k, v in cat_breakdown.items())}\n"
                f"• Uncovered behaviors: {len(uncovered_behaviors)}"
            )
        }
        _fire_slack_webhook(wh.slack_webhook_url, slack_payload)

    return {
        "message": "Test cases generated successfully",
        "count": len(generated_tests),
        "test_cases": generated_tests,
        "run_id": db_run.id,
        "uncovered_behaviors": uncovered_behaviors,
        "category_allocation": {
            cat: {
                "applicable": s.get("applicable", True),
                "reason": s.get("reason", ""),
                "allocated_slots": s.get("allocated_slots", 0),
            }
            for cat, s in category_allocation.items()
        },
        "skipped_categories": skipped_categories,
        "generation_meta": generation_meta,
    }


@app.get("/api/stories/{story_id}/test-cases")
def get_story_test_cases(story_id: int, db: Session = Depends(database.get_db)):
    test_cases = db.query(models.TestCase).filter(models.TestCase.story_id == story_id).all()
    return test_cases


@app.get("/api/stories/{story_id}", response_model=schemas.Story)
def get_story(story_id: int, db: Session = Depends(database.get_db)):
    return _story_or_404(story_id, db)


@app.delete("/api/stories/{story_id}", status_code=204)
def delete_story(story_id: int, db: Session = Depends(database.get_db)):
    story = _story_or_404(story_id, db)
    db.delete(story)
    db.commit()
    return None


@app.get("/api/stories", response_model=List[schemas.Story])
def get_stories(db: Session = Depends(database.get_db)):
    return db.query(models.Story).order_by(models.Story.created_at.desc()).all()


# ---------------------------------------------------------------------------
# Feature 1 — Per-case regeneration
# ---------------------------------------------------------------------------

@app.post("/api/test-cases/{case_id}/regenerate")
def regenerate_test_case(
    case_id: int,
    body: schemas.RegenerateRequest,
    db: Session = Depends(database.get_db),
):
    """Regenerate a single test case with an optional user instruction."""
    db_tc = _testcase_or_404(case_id, db)
    story = _story_or_404(db_tc.story_id, db)

    story_text = story.clarified_description or story.description
    behavior_ctx = db_tc.behavior_context  # may be None for pre-feature cases

    updated = llm_service.regenerate_single_case(
        story_text=story_text,
        behavior_tag=behavior_ctx,
        existing_case={
            "title": db_tc.title,
            "category": db_tc.category,
            "priority": db_tc.priority,
            "preconditions": db_tc.preconditions,
            "steps": db_tc.steps,
            "expected_result": db_tc.expected_result,
            "covers_behavior_id": (behavior_ctx or {}).get("covers_behavior_id"),
        },
        instruction=body.instruction,
    )
    if updated is None:
        raise HTTPException(status_code=503, detail="LLM regeneration failed. Try again.")

    # Update fields (preserve category, sequence_id, story_id, run_id)
    db_tc.title = updated.get("title", db_tc.title)
    db_tc.priority = updated.get("priority", db_tc.priority)
    db_tc.preconditions = updated.get("preconditions", db_tc.preconditions)
    db_tc.steps = updated.get("steps", db_tc.steps)
    db_tc.expected_result = updated.get("expected_result", db_tc.expected_result)

    db.commit()
    db.refresh(db_tc)
    return db_tc


@app.patch("/api/test-cases/{case_id}")
def update_test_case(
    case_id: int,
    body: schemas.TestCaseUpdate,
    db: Session = Depends(database.get_db),
):
    """Inline edit a test case."""
    db_tc = _testcase_or_404(case_id, db)
    if body.title is not None:
        db_tc.title = body.title
    if body.category is not None:
        db_tc.category = body.category
    if body.priority is not None:
        db_tc.priority = body.priority
    if body.preconditions is not None:
        db_tc.preconditions = body.preconditions
    if body.steps is not None:
        db_tc.steps = body.steps
    if body.expected_result is not None:
        db_tc.expected_result = body.expected_result
    if body.assigned_to is not None:
        db_tc.assigned_to = body.assigned_to
    db.commit()
    db.refresh(db_tc)
    return db_tc


@app.delete("/api/test-cases/{case_id}", status_code=204)
def delete_test_case(case_id: int, db: Session = Depends(database.get_db)):
    db_tc = _testcase_or_404(case_id, db)
    db.delete(db_tc)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Feature 2 — Post-generation Q&A
# ---------------------------------------------------------------------------

@app.post("/api/stories/{story_id}/qa")
def ask_qa_question(
    story_id: int,
    body: schemas.QAQuestion,
    db: Session = Depends(database.get_db),
):
    """Ask a free-text question about a story's generated result set."""
    story = _story_or_404(story_id, db)
    test_cases = db.query(models.TestCase).filter(models.TestCase.story_id == story_id).all()

    generation_meta = {}
    if story.generation_meta_json:
        try:
            generation_meta = json.loads(story.generation_meta_json)
        except Exception:
            pass

    tc_summary = [
        {"title": tc.title, "category": tc.category, "expected_result": tc.expected_result}
        for tc in test_cases
    ]

    story_text = story.clarified_description or story.description
    answer = llm_service.answer_qa_question(
        story_text=story_text,
        generation_meta=generation_meta,
        test_cases_summary=tc_summary,
        question=body.question,
    )

    # Persist exchange
    latest_run = (
        db.query(models.GenerationRun)
        .filter(models.GenerationRun.story_id == story_id)
        .order_by(models.GenerationRun.created_at.desc())
        .first()
    )
    db_exchange = models.QAExchange(
        story_id=story_id,
        run_id=latest_run.id if latest_run else None,
        question=body.question,
        answer=answer,
    )
    db.add(db_exchange)
    db.commit()
    db.refresh(db_exchange)
    return db_exchange


@app.get("/api/stories/{story_id}/qa")
def get_qa_exchanges(story_id: int, db: Session = Depends(database.get_db)):
    """Return all Q&A exchanges for a story, oldest first."""
    _story_or_404(story_id, db)
    return (
        db.query(models.QAExchange)
        .filter(models.QAExchange.story_id == story_id)
        .order_by(models.QAExchange.created_at.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Feature 4 — Story versioning & diffing
# ---------------------------------------------------------------------------

@app.get("/api/stories/{story_id}/runs")
def get_generation_runs(story_id: int, db: Session = Depends(database.get_db)):
    """Return all generation runs for a story, newest first."""
    _story_or_404(story_id, db)
    runs = (
        db.query(models.GenerationRun)
        .filter(models.GenerationRun.story_id == story_id)
        .order_by(models.GenerationRun.created_at.desc())
        .all()
    )
    return runs


@app.get("/api/stories/{story_id}/diff")
def get_story_diff(story_id: int, compare_story_id: int = Query(...), db: Session = Depends(database.get_db)):
    """
    Compare two story versions and return a unified diff + test case staleness classification.
    compare_story_id: the older story_id to diff against (same title, earlier version).
    """
    new_story = _story_or_404(story_id, db)
    old_story = _story_or_404(compare_story_id, db)

    old_lines = (old_story.description or "").splitlines(keepends=True)
    new_lines = (new_story.description or "").splitlines(keepends=True)
    raw_diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))

    diff_lines = []
    changed_hunks: List[str] = []
    for line in raw_diff:
        if line.startswith("+") and not line.startswith("+++"):
            diff_lines.append({"line_type": "added", "content": line[1:]})
            changed_hunks.append(line[1:].lower())
        elif line.startswith("-") and not line.startswith("---"):
            diff_lines.append({"line_type": "removed", "content": line[1:]})
            changed_hunks.append(line[1:].lower())
        elif not line.startswith("@@") and not line.startswith("---") and not line.startswith("+++"):
            diff_lines.append({"line_type": "unchanged", "content": line.lstrip(" ")})

    # Classify old story's test cases against the diff
    old_tcs = db.query(models.TestCase).filter(models.TestCase.story_id == compare_story_id).all()
    tc_statuses = []
    for tc in old_tcs:
        tc_text = (tc.title + " " + tc.expected_result + " " + " ".join(tc.steps)).lower()
        tc_tokens = set(re.findall(r"\b\w+\b", tc_text))

        # Check overlap with changed hunk tokens
        hunk_tokens = set(re.findall(r"\b\w+\b", " ".join(changed_hunks)))
        overlap = tc_tokens & hunk_tokens

        if not diff_lines:
            validity = "still_valid"
            reason = "No changes detected."
        elif len(overlap) >= 3:
            validity = "possibly_stale"
            reason = f"Overlaps with changed text ({len(overlap)} shared terms)."
        elif any(word in tc_text for word in ["removed", "deleted", "deprecated"]):
            validity = "obsolete"
            reason = "References removed functionality."
        else:
            validity = "still_valid"
            reason = "No significant overlap with changed lines."

        tc_statuses.append({
            "test_case_id": tc.id,
            "sequence_id": tc.sequence_id,
            "title": tc.title,
            "validity": validity,
            "reason": reason,
        })

    return {
        "old_version": old_story.version or 1,
        "new_version": new_story.version or 1,
        "diff_lines": diff_lines,
        "test_case_statuses": tc_statuses,
        "has_changes": len(diff_lines) > 0,
    }


# ---------------------------------------------------------------------------
# Feature 5 — Cross-story pattern suggestions
# ---------------------------------------------------------------------------

@app.get("/api/stories/{story_id}/pattern-suggestions")
def get_pattern_suggestions(story_id: int, db: Session = Depends(database.get_db)):
    """
    Look across past runs for recurring behavior tags and return suggestions.
    Efficient: loads only generation_meta_json blobs, no full table scans of test cases.
    """
    _story_or_404(story_id, db)

    # Load all stories except current one
    other_stories = (
        db.query(models.Story)
        .filter(models.Story.id != story_id, models.Story.generation_meta_json != None)
        .all()
    )

    tag_counts: Dict[str, List[int]] = {}  # tag → list of story_ids that had it

    for s in other_stories:
        try:
            meta = json.loads(s.generation_meta_json or "{}")
        except Exception:
            continue
        uncovered = meta.get("uncovered_behaviors", [])
        cat_alloc = meta.get("category_allocation", {})

        # Extract behavior keywords from uncovered behaviors
        for b in uncovered:
            desc = b.get("description", "")
            tokens = re.findall(r"\b[a-z]{4,}\b", desc.lower())
            for t in tokens:
                tag_counts.setdefault(t, [])
                if s.id not in tag_counts[t]:
                    tag_counts[t].append(s.id)

        # Also look at skipped categories as pattern hints
        for cat in meta.get("skipped_categories", []):
            tag_counts.setdefault(cat.lower(), [])
            if s.id not in tag_counts[cat.lower()]:
                tag_counts[cat.lower()].append(s.id)

    # Filter: recur in >= 2 other stories; sort by count
    STOP_WORDS = {"that", "this", "with", "have", "from", "when", "user", "should", "must", "will"}
    suggestions = [
        {"tag": tag, "count": len(story_ids), "example_story_ids": story_ids[:5]}
        for tag, story_ids in tag_counts.items()
        if len(story_ids) >= 2 and tag not in STOP_WORDS and len(tag) > 4
    ]
    suggestions.sort(key=lambda s: s["count"], reverse=True)

    return {"suggestions": suggestions[:10]}


# ---------------------------------------------------------------------------
# Feature 6 — Shareable read-only links
# ---------------------------------------------------------------------------

@app.post("/api/stories/{story_id}/share")
def create_share_token(
    story_id: int,
    body: schemas.ShareTokenCreate,
    db: Session = Depends(database.get_db),
):
    story = _story_or_404(story_id, db)
    token = secrets.token_urlsafe(32)
    expires_at = None
    if body.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    db_token = models.ShareToken(
        story_id=story_id,
        token=token,
        expires_at=expires_at,
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)

    return {
        "id": db_token.id,
        "story_id": db_token.story_id,
        "token": token,
        "created_at": db_token.created_at,
        "expires_at": db_token.expires_at,
        "is_revoked": db_token.is_revoked,
        "share_url": f"/share/{token}",
    }


@app.get("/api/share/{token}")
def get_shared_run(token: str, db: Session = Depends(database.get_db)):
    """Public read-only endpoint. Returns story + test cases. No auth needed."""
    db_token = (
        db.query(models.ShareToken)
        .filter(models.ShareToken.token == token, models.ShareToken.is_revoked == False)
        .first()
    )
    if not db_token:
        raise HTTPException(status_code=404, detail="Share link not found or revoked.")

    if db_token.expires_at:
        # Make both timezone-aware for comparison
        exp = db_token.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Share link has expired.")

    story = db.query(models.Story).filter(models.Story.id == db_token.story_id).first()
    test_cases = db.query(models.TestCase).filter(models.TestCase.story_id == db_token.story_id).all()

    generation_meta = {}
    if story and story.generation_meta_json:
        try:
            generation_meta = json.loads(story.generation_meta_json)
        except Exception:
            pass

    return {
        "story": story,
        "test_cases": test_cases,
        "generation_meta": generation_meta,
        "is_read_only": True,
    }


@app.delete("/api/share/{token}", status_code=204)
def revoke_share_token(token: str, db: Session = Depends(database.get_db)):
    db_token = db.query(models.ShareToken).filter(models.ShareToken.token == token).first()
    if not db_token:
        raise HTTPException(status_code=404, detail="Share token not found.")
    db_token.is_revoked = True
    db.commit()
    return None


@app.get("/api/stories/{story_id}/shares")
def list_share_tokens(story_id: int, db: Session = Depends(database.get_db)):
    """List all share tokens for a story."""
    _story_or_404(story_id, db)
    tokens = (
        db.query(models.ShareToken)
        .filter(models.ShareToken.story_id == story_id)
        .order_by(models.ShareToken.created_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "token": t.token,
            "created_at": t.created_at,
            "expires_at": t.expires_at,
            "is_revoked": t.is_revoked,
            "share_url": f"/share/{t.token}",
        }
        for t in tokens
    ]


# ---------------------------------------------------------------------------
# Feature 8 — Slack webhook configuration
# ---------------------------------------------------------------------------

@app.put("/api/stories/{story_id}/webhook")
def upsert_webhook(
    story_id: int,
    body: schemas.WebhookConfigIn,
    db: Session = Depends(database.get_db),
):
    _story_or_404(story_id, db)
    existing = db.query(models.WebhookConfig).filter(models.WebhookConfig.story_id == story_id).first()
    if existing:
        existing.slack_webhook_url = body.slack_webhook_url
        existing.enabled = body.enabled if body.enabled is not None else True
        db.commit()
        db.refresh(existing)
        return existing
    new_wh = models.WebhookConfig(
        story_id=story_id,
        slack_webhook_url=body.slack_webhook_url,
        enabled=body.enabled if body.enabled is not None else True,
    )
    db.add(new_wh)
    db.commit()
    db.refresh(new_wh)
    return new_wh


@app.get("/api/stories/{story_id}/webhook")
def get_webhook(story_id: int, db: Session = Depends(database.get_db)):
    _story_or_404(story_id, db)
    wh = db.query(models.WebhookConfig).filter(models.WebhookConfig.story_id == story_id).first()
    if not wh:
        return {"configured": False}
    return {
        "configured": True,
        "id": wh.id,
        "story_id": wh.story_id,
        "slack_webhook_url": wh.slack_webhook_url,
        "enabled": wh.enabled,
    }


# ---------------------------------------------------------------------------
# Feature 9 — Approval state transitions
# ---------------------------------------------------------------------------

@app.patch("/api/test-cases/{case_id}/approval")
def update_approval(
    case_id: int,
    body: schemas.ApprovalUpdate,
    x_user_role: Optional[str] = Header(default="author"),
    db: Session = Depends(database.get_db),
):
    """
    Update approval status. Only 'qa_lead' role can set status to 'Approved'.
    Role is read from X-User-Role header (localStorage-backed stub — not secure).
    """
    db_tc = _testcase_or_404(case_id, db)
    if body.status == "Approved" and (x_user_role or "").lower() != "qa_lead":
        raise HTTPException(
            status_code=403,
            detail="Only QA Leads can approve test cases. Set X-User-Role: qa_lead header.",
        )
    db_tc.approval_status = body.status
    db.commit()
    db.refresh(db_tc)
    return db_tc


# ---------------------------------------------------------------------------
# Feature 10 — Comment threads
# ---------------------------------------------------------------------------

@app.post("/api/test-cases/{case_id}/comments")
def add_comment(
    case_id: int,
    body: schemas.CommentCreate,
    db: Session = Depends(database.get_db),
):
    _testcase_or_404(case_id, db)
    db_comment = models.Comment(
        test_case_id=case_id,
        author=body.author,
        text=body.text,
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


@app.get("/api/test-cases/{case_id}/comments")
def get_comments(case_id: int, db: Session = Depends(database.get_db)):
    _testcase_or_404(case_id, db)
    return (
        db.query(models.Comment)
        .filter(models.Comment.test_case_id == case_id)
        .order_by(models.Comment.created_at.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Feature 11 — Manual execution mode
# ---------------------------------------------------------------------------

@app.get("/api/stories/{story_id}/execution")
def get_execution_results(story_id: int, db: Session = Depends(database.get_db)):
    """Return execution results for all test cases in a story."""
    _story_or_404(story_id, db)
    tcs = db.query(models.TestCase).filter(models.TestCase.story_id == story_id).all()
    tc_ids = [tc.id for tc in tcs]

    results = (
        db.query(models.ExecutionResult)
        .filter(models.ExecutionResult.test_case_id.in_(tc_ids))
        .all()
    ) if tc_ids else []

    result_map = {r.test_case_id: r for r in results}

    return [
        {
            "test_case_id": tc.id,
            "sequence_id": tc.sequence_id,
            "title": tc.title,
            "category": tc.category,
            "priority": tc.priority,
            "steps": tc.steps,
            "expected_result": tc.expected_result,
            "execution": {
                "status": result_map[tc.id].status if tc.id in result_map else "Not Run",
                "actual_result": result_map[tc.id].actual_result if tc.id in result_map else None,
                "executed_by": result_map[tc.id].executed_by if tc.id in result_map else None,
                "executed_at": result_map[tc.id].executed_at if tc.id in result_map else None,
                "jira_bug_key": result_map[tc.id].jira_bug_key if tc.id in result_map else None,
            },
        }
        for tc in tcs
    ]


@app.put("/api/test-cases/{case_id}/execution")
def upsert_execution_result(
    case_id: int,
    body: schemas.ExecutionResultIn,
    db: Session = Depends(database.get_db),
):
    """Upsert execution result for a test case."""
    _testcase_or_404(case_id, db)
    existing = (
        db.query(models.ExecutionResult)
        .filter(models.ExecutionResult.test_case_id == case_id)
        .first()
    )
    now = datetime.now(timezone.utc)
    if existing:
        existing.status = body.status
        existing.actual_result = body.actual_result
        existing.executed_by = body.executed_by
        existing.executed_at = now
        db.commit()
        db.refresh(existing)
        return existing

    new_result = models.ExecutionResult(
        test_case_id=case_id,
        status=body.status,
        actual_result=body.actual_result,
        executed_by=body.executed_by,
        executed_at=now,
    )
    db.add(new_result)
    db.commit()
    db.refresh(new_result)
    return new_result


# ---------------------------------------------------------------------------
# Feature 12 — Jira bug creation shortcut
# ---------------------------------------------------------------------------

@app.post("/api/test-cases/{case_id}/create-jira-bug")
def create_jira_bug(
    case_id: int,
    body: schemas.JiraBugRequest,
    db: Session = Depends(database.get_db),
):
    """
    If JIRA_BASE_URL + JIRA_API_TOKEN are configured in env → calls Jira REST API.
    Otherwise returns a pre-filled payload for manual submission.
    """
    db_tc = _testcase_or_404(case_id, db)
    steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(db_tc.steps))

    prefilled = {
        "summary": f"[Bug] {db_tc.title}",
        "description": (
            f"*Test Case*: {db_tc.sequence_id}\n\n"
            f"*Steps to Reproduce*:\n{steps_text}\n\n"
            f"*Expected Result*:\n{db_tc.expected_result}\n\n"
            f"*Actual Result*:\n{body.actual_result}"
        ),
        "issuetype": "Bug",
        "priority": db_tc.priority,
    }

    if JIRA_BASE_URL and JIRA_API_TOKEN and JIRA_EMAIL:
        project_key = body.project_key or JIRA_PROJECT_KEY
        jira_payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": prefilled["summary"],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": prefilled["description"]}]}],
                },
                "issuetype": {"name": "Bug"},
                "priority": {"name": db_tc.priority},
            }
        }
        try:
            response = httpx.post(
                f"{JIRA_BASE_URL}/rest/api/3/issue",
                json=jira_payload,
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            if response.status_code in (200, 201):
                data = response.json()
                bug_key = data.get("key", "")
                # Update execution result with bug key
                exec_result = (
                    db.query(models.ExecutionResult)
                    .filter(models.ExecutionResult.test_case_id == case_id)
                    .first()
                )
                if exec_result:
                    exec_result.jira_bug_key = bug_key
                    db.commit()
                return {
                    "key": bug_key,
                    "url": f"{JIRA_BASE_URL}/browse/{bug_key}",
                    "prefilled_payload": None,
                }
        except Exception as e:
            print(f"[main] Jira API error: {e}")
            # Fall through to prefilled response

    return {"key": None, "url": None, "prefilled_payload": prefilled}


# ---------------------------------------------------------------------------
# Feature 14 — Admin metrics dashboard
# ---------------------------------------------------------------------------

@app.get("/api/admin/metrics")
def get_admin_metrics(
    start: Optional[str] = Query(None, description="ISO date string e.g. 2026-01-01"),
    end: Optional[str] = Query(None, description="ISO date string"),
    story_id: Optional[int] = Query(None),
    db: Session = Depends(database.get_db),
):
    """Return per-run metrics, optionally filtered by date range or story."""
    query = db.query(models.GenerationRun, models.Story).join(
        models.Story, models.GenerationRun.story_id == models.Story.id
    )
    if story_id:
        query = query.filter(models.GenerationRun.story_id == story_id)
    if start:
        try:
            query = query.filter(models.GenerationRun.created_at >= datetime.fromisoformat(start))
        except ValueError:
            pass
    if end:
        try:
            query = query.filter(models.GenerationRun.created_at <= datetime.fromisoformat(end))
        except ValueError:
            pass

    rows = query.order_by(models.GenerationRun.created_at.desc()).limit(200).all()

    return [
        {
            "run_id": run.id,
            "story_id": run.story_id,
            "story_title": story.title,
            "version": run.version,
            "created_at": run.created_at,
            "provider": run.provider,
            "prompt_tokens": run.prompt_tokens or 0,
            "completion_tokens": run.completion_tokens or 0,
            "total_tokens": (run.prompt_tokens or 0) + (run.completion_tokens or 0),
            "wall_time_ms": run.wall_time_ms or 0,
            "retry_count": run.retry_count or 0,
        }
        for run, story in rows
    ]


# ---------------------------------------------------------------------------
# Feature 15 — Coverage trend analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics/coverage-trend")
def get_coverage_trend(
    weeks: int = Query(8, ge=1, le=52),
    db: Session = Depends(database.get_db),
):
    """
    Feature 15 — Coverage trend by ISO week.
    Reads uncovered_behaviors from persisted generation_meta_json.
    Returns "no data yet" gracefully if insufficient history.
    """
    stories = (
        db.query(models.Story)
        .filter(models.Story.generation_meta_json != None)
        .order_by(models.Story.created_at.asc())
        .all()
    )

    if not stories:
        return {"weeks": [], "note": "No data yet — generate some test cases first."}

    from collections import defaultdict
    week_data: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "with_uncovered": 0})

    for story in stories:
        try:
            meta = json.loads(story.generation_meta_json or "{}")
        except Exception:
            continue

        uncovered = meta.get("uncovered_behaviors", [])
        created = story.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        iso_week = created.strftime("%G-W%V")  # ISO week e.g. "2026-W35"
        week_data[iso_week]["total"] += 1
        if uncovered:
            week_data[iso_week]["with_uncovered"] += 1

    # Build ordered list for the last `weeks` weeks
    sorted_weeks = sorted(week_data.keys())[-weeks:]
    trend = []
    for w in sorted_weeks:
        d = week_data[w]
        total = d["total"]
        with_unc = d["with_uncovered"]
        pct_covered = round(((total - with_unc) / total) * 100, 1) if total > 0 else 100.0
        trend.append({
            "week": w,
            "total_stories": total,
            "stories_with_uncovered": with_unc,
            "pct_covered": pct_covered,
        })

    return {"weeks": trend}
