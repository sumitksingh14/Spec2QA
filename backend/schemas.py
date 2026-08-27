from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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
    
    class Config:
        from_attributes = True

class ClarificationRequest(BaseModel):
    questions: List[str]
    missing_elements: List[str]
    extracted_entities: dict

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
