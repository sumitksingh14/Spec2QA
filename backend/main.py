from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import json

import models, schemas, database, llm_service

# Create DB tables
database.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="StoryToTest API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In prod, replace with frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/analyze")
def analyze_story(story: schemas.StoryCreate, db: Session = Depends(database.get_db)):
    # Basic persistence for the story
    db_story = models.Story(title=story.title, description=story.description, story_type=story.story_type)
    db.add(db_story)
    db.commit()
    db.refresh(db_story)

    # Send to LLM for analysis
    analysis_result = llm_service.analyze_story(story.description)

    # Include the story_id so the frontend doesn't need a second request
    return {"story_id": db_story.id, **analysis_result}


@app.post("/api/generate/manual-tests")
def generate_tests(request: schemas.GenerateTestCasesRequest, db: Session = Depends(database.get_db)):
    db_story = db.query(models.Story).filter(models.Story.id == request.story_id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="Story not found")

    story_text = request.clarified_description or db_story.description

    if request.clarified_description and request.clarified_description != db_story.description:
        db_story.clarified_description = request.clarified_description

    # Generate test cases using enhanced two-pass LLM pipeline (v2)
    generation_result = llm_service.generate_test_cases(story_text)

    test_cases_data = generation_result["test_cases"]
    uncovered_behaviors = generation_result.get("uncovered_behaviors", [])
    category_allocation = generation_result.get("category_allocation", {})
    skipped_categories = generation_result.get("skipped_categories", [])
    generation_meta = generation_result.get("generation_meta", {})

    # Persist coverage/gap metadata to the Story so StoryDetails can show it on reload
    db_story.generation_meta_json = json.dumps({
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
    })

    generated_tests = []
    for i, tc_data in enumerate(test_cases_data, start=1):
        db_tc = models.TestCase(
            story_id=db_story.id,
            sequence_id=f"TC-{db_story.id}-{i:02d}",
            title=tc_data.get("title", ""),
            category=tc_data.get("category", "Functional"),
            priority=tc_data.get("priority", "Medium"),
            preconditions=tc_data.get("preconditions", ""),
            steps=tc_data.get("steps", []),
            expected_result=tc_data.get("expected_result", ""),
        )
        db.add(db_tc)
        generated_tests.append(db_tc)

    db.commit()

    for tc in generated_tests:
        db.refresh(tc)

    # Build response: test_cases in existing shape + new additive fields
    return {
        "message": "Test cases generated successfully",
        "count": len(generated_tests),
        "test_cases": generated_tests,
        # §5 — uncovered behaviors ranked by risk_weight
        "uncovered_behaviors": uncovered_behaviors,
        # §2 / §1 — per-category applicability and slot allocation
        "category_allocation": {
            cat: {
                "applicable": s.get("applicable", True),
                "reason": s.get("reason", ""),
                "allocated_slots": s.get("allocated_slots", 0),
            }
            for cat, s in category_allocation.items()
        },
        # §2 — categories skipped
        "skipped_categories": skipped_categories,
        # Diagnostic metadata
        "generation_meta": generation_meta,
    }


@app.get("/api/stories/{story_id}/test-cases")
def get_story_test_cases(story_id: int, db: Session = Depends(database.get_db)):
    test_cases = db.query(models.TestCase).filter(models.TestCase.story_id == story_id).all()
    return test_cases


@app.get("/api/stories/{story_id}", response_model=schemas.Story)
def get_story(story_id: int, db: Session = Depends(database.get_db)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@app.delete("/api/stories/{story_id}", status_code=204)
def delete_story(story_id: int, db: Session = Depends(database.get_db)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    db.delete(story)
    db.commit()
    return None


@app.get("/api/stories", response_model=List[schemas.Story])
def get_stories(db: Session = Depends(database.get_db)):
    return db.query(models.Story).order_by(models.Story.created_at.desc()).all()
