from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

# TAGS
class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = "#6c757d"

class TagResponse(BaseModel):
    id: int
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)

# CATEGORIES
class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[int] = None

class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    parent_id: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CategoryTreeResponse(CategoryResponse):
    children: List['CategoryTreeResponse'] = Field(default_factory=list)

# SEARCH
class QuestionSearchFilters(BaseModel):
    query: Optional[str] = None
    category_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    limit: int = 20
    offset: int = 0
