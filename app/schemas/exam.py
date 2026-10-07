from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.models.enums import RandomizationMode, ExamStatus


class ProctoringSettings(BaseModel):
    webcam_enabled: bool = True
    gaze_tracking_enabled: bool = False
    gaze_sensitivity_threshold: float = Field(0.5, ge=0.0, le=1.0)
    max_tab_switch_warnings: int = Field(3, ge=0)


class SelectionRules(BaseModel):
    difficulty: Optional[Dict[str, int]] = None
    question_type: Optional[Dict[str, int]] = None


class ExamQuestionCreate(BaseModel):
    question_id: str
    marks_override: Optional[float] = None
    order_index: Optional[int] = 0


class ExamCreate(BaseModel):
    title: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    duration_minutes: int = Field(..., gt=0)
    start_time: datetime
    end_time: datetime
    randomization_mode: Optional[RandomizationMode] = RandomizationMode.NONE
    negative_marking_enabled: bool = False
    selection_rules: Optional[Dict[str, Any]] = None
    proctoring_settings: Optional[Dict[str, Any]] = None
    question_ids: Optional[List[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_exam_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly after start_time")

        window_duration_minutes = (self.end_time - self.start_time).total_seconds() / 60.0
        if self.duration_minutes > window_duration_minutes:
            raise ValueError("duration_minutes cannot exceed total time window length")

        if self.proctoring_settings:
            gaze_sens = self.proctoring_settings.get("gaze_sensitivity_threshold")
            if gaze_sens is not None and (gaze_sens < 0.0 or gaze_sens > 1.0):
                raise ValueError("gaze_sensitivity_threshold must be between 0.0 and 1.0")

        return self


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    randomization_mode: Optional[RandomizationMode] = None
    negative_marking_enabled: Optional[bool] = None
    selection_rules: Optional[Dict[str, Any]] = None
    proctoring_settings: Optional[Dict[str, Any]] = None
    question_ids: Optional[List[str]] = None


class ExamOut(BaseModel):
    id: str
    created_by: Optional[str]
    title: str
    subject: str
    duration_minutes: int
    start_time: datetime
    end_time: datetime
    randomization_mode: RandomizationMode
    negative_marking_enabled: bool
    selection_rules: Optional[Dict[str, Any]]
    proctoring_settings: Optional[Dict[str, Any]]
    status: ExamStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExamListResponse(BaseModel):
    items: List[ExamOut]
    total: int
    page: int
    size: int
