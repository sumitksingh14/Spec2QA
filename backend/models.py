from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import database
import json

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

    acceptance_criteria = relationship("AcceptanceCriterion", back_populates="story", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="story", cascade="all, delete-orphan")

class AcceptanceCriterion(database.Base):
    __tablename__ = "acceptance_criteria"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    description = Column(Text)

    story = relationship("Story", back_populates="acceptance_criteria")

class TestCase(database.Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    sequence_id = Column(String, index=True) # e.g. TC-123-01
    title = Column(String)
    category = Column(String) # Functional, Negative, Boundary, etc.
    priority = Column(String) # Critical, High, Medium, Low
    preconditions = Column(Text, nullable=True)
    steps_json = Column(Text) # JSON string of steps
    expected_result = Column(Text)
    status = Column(String, default="Not Run")
    
    # Store linked AC IDs as JSON for simplicity in MVP
    linked_ac_ids_json = Column(Text, nullable=True) 

    story = relationship("Story", back_populates="test_cases")
    
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
