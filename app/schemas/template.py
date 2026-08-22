"""
Pydantic schemas for Exam Templates.
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List


class TemplateCreate(BaseModel):
    """Schema for creating exam template."""
    name: str = Field(..., min_length=3, max_length=200, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    template_data: Dict[str, Any] = Field(..., description="Exam configuration as JSON")
    is_public: bool = Field(False, description="Make template public for all teachers")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Template Ujian Pilihan Ganda 20 Soal",
                "description": "Template standar untuk ujian MC dengan 20 soal",
                "template_data": {
                    "duration_minutes": 60,
                    "passing_score": 70,
                    "shuffle_questions": True,
                    "shuffle_options": True,
                    "max_attempts": 1,
                    "show_results": True,
                    "question_count": 20,
                    "question_types": ["multiple_choice"]
                },
                "is_public": False
            }
        }
    }


class TemplateUpdate(BaseModel):
    """Schema for updating exam template."""
    name: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    template_data: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None


class TemplateResponse(BaseModel):
    """Schema for template response."""
    id: int
    name: str
    description: Optional[str] = None
    creator_id: Optional[int] = None
    template_data: Dict[str, Any]
    is_public: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    """Schema for list of templates response."""
    templates: List[TemplateResponse]
    total: int


class ExamFromTemplateCreate(BaseModel):
    """Schema for creating exam from template."""
    title: str = Field(..., min_length=3, description="Exam title")
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    allowed_classes: Optional[str] = Field(None, description="Comma-separated class names")
    
    # Override template defaults (optional)
    duration_minutes: Optional[int] = Field(None, ge=1, description="Override template duration")
    passing_score: Optional[float] = Field(None, ge=0, le=100, description="Override passing score")
    max_attempts: Optional[int] = Field(None, ge=1, description="Override max attempts")
