"""
Question and QuestionOption models.
Supports 5 question types: multiple_choice, multiple_choice_complex, true_false, essay, short_answer
multiple_choice_complex supports 3 subtypes: checkbox, true_false_table, combination
"""
from datetime import datetime, timezone
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class Question(Base):
    """Question model for exam questions."""

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    # Optional context/reading for PGK or HOTS questions.
    stimulus = Column(Text, nullable=True)
    # Expanded to support 6 types
    question_type = Column(String(50), nullable=False, default="multiple_choice")
    question_subtype = Column(String(50), nullable=True)  # For future variants
    # NEW: PGK sub-type ('checkbox' for Tipe A, 'table_validation' for Tipe B)
    pgk_type = Column(String(50), nullable=True, default="checkbox")
    difficulty_level = Column(String(20), default="medium")

    # Classification
    category_id = Column(Integer, ForeignKey("question_categories.id", ondelete="SET NULL"), nullable=True)

    question_settings = Column(JSONB, default={})
    points = Column(Numeric(5, 2), nullable=False, default=1.00)
    order_index = Column(Integer, nullable=False)
    image_url = Column(String(255), nullable=True)
    video_url = Column(String(255), nullable=True)  # YouTube or video URL
    audio_url = Column(String(255), nullable=True)  # Audio file URL
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    exam = relationship("Exam", back_populates="questions", lazy="selectin")
    category = relationship("QuestionCategory", back_populates="questions", lazy="selectin")
    tags = relationship("QuestionTag", secondary="question_tags_map", back_populates="questions", lazy="selectin")
    options = relationship("QuestionOption", back_populates="question", lazy="selectin", cascade="all, delete-orphan")
    answers = relationship("Answer", back_populates="question", lazy="selectin")

    def __repr__(self):
        return f"<Question {self.id}: {self.question_text[:50]}...>"

    @property
    def correct_option(self) -> Optional["QuestionOption"]:
        """Get the first correct option (for single-answer types)."""
        for option in self.options:
            if option.is_correct:
                return option
        return None

    @property
    def correct_options(self) -> List["QuestionOption"]:
        """Get all correct options (for multiple-answer types)."""
        return [opt for opt in self.options if opt.is_correct]

    @property
    def is_hots_mode(self) -> bool:
        """Check if question is in HOTS mode."""
        settings = self.question_settings or {}
        return settings.get("is_hots_mode", False)

    @property
    def supports_multiple_answers(self) -> bool:
        """Check if question allows multiple correct answers."""
        return self.question_type == "multiple_choice_complex"

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Safely get a setting value."""
        settings = self.question_settings or {}
        return settings.get(key, default)

    def validate_answer(self, answer_data: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Validate answer based on question type.

        Args:
            answer_data: dict containing selected_option_id, selected_option_ids,
                        answer_text depending on type)

        Returns:
            Tuple of (is_correct: bool, points_earned: float)
        """
        if self.question_type == "multiple_choice":
            return self._validate_multiple_choice(answer_data)
        elif self.question_type == "multiple_choice_complex":
            # Check pgk_type to determine validation method
            pgk_type = self.pgk_type or self.get_setting("pgk_type", "checkbox")
            if pgk_type == "table_validation":
                return self._validate_true_false_table(answer_data)
            else:
                return self._validate_complex_choice(answer_data)
        elif self.question_type == "true_false":
            return self._validate_multiple_choice(answer_data)  # Same logic as MC
        elif self.question_type == "essay":
            return self._validate_essay(answer_data)
        elif self.question_type == "short_answer":
            return self._validate_short_answer(answer_data)
        else:
            return False, 0.0

    def _validate_multiple_choice(self, answer_data: Dict[str, Any]) -> Tuple[bool, float]:
        """Validate single-answer multiple choice or true/false."""
        selected_id = answer_data.get("selected_option_id")
        if not selected_id:
            return False, 0.0

        # Robust type conversion
        try:
            selected_id = int(selected_id)
        except (ValueError, TypeError):
            # If conversion fails, it won't match any int ID, which is correct behavior for invalid input
            pass

        selected_option = next(
            (opt for opt in self.options if opt.id == selected_id),
            None
        )
        if selected_option and selected_option.is_correct:
            return True, float(self.points)
        return False, 0.0

    def _validate_complex_choice(self, answer_data: Dict[str, Any]) -> Tuple[bool, float]:
        """Validate multiple choice complex with optional partial scoring."""
        selected_ids = answer_data.get("selected_option_ids", [])
        if not selected_ids:
            return False, 0.0

        # Robust type conversion for list
        try:
            selected_ids = [int(x) for x in selected_ids if x is not None]
        except (ValueError, TypeError):
            # If any conversion fails, we proceed with potentially partial or empty list
            # Ideally this shouldn't happen if validation layer works, but defensive coding helps
            pass

        correct_option_ids = {opt.id for opt in self.options if opt.is_correct}
        selected_set = set(selected_ids)

        # Count correct and incorrect selections
        correct_count = len(selected_set & correct_option_ids)
        incorrect_count = len(selected_set - correct_option_ids)
        total_correct = len(correct_option_ids)

        if total_correct == 0:
            return False, 0.0

        # Check if partial scoring is enabled
        partial_scoring = self.get_setting("partial_scoring", False)

        if partial_scoring:
            # Partial scoring: (correct - incorrect) / total, minimum 0
            score_ratio = max(0, (correct_count - incorrect_count) / total_correct)
            points_earned = float(self.points) * score_ratio
            # Is correct if at least 50% score achieved
            is_correct = score_ratio >= 0.5
            return is_correct, points_earned
        else:
            # All or nothing: must select exactly all correct options
            is_correct = selected_set == correct_option_ids
            return is_correct, float(self.points) if is_correct else 0.0

    def _validate_short_answer(self, answer_data: Dict[str, Any]) -> Tuple[Optional[bool], Optional[float]]:
        """Validate short answer with flexible matching.

        If require_manual_grading is enabled, always require manual grading.
        If acceptable_answers is configured and manual grading not required, auto-grade.
        Otherwise, require manual grading (return None, None).
        """
        student_answer = (answer_data.get("answer_text") or "").strip()
        if not student_answer:
            return None, None  # Empty answer requires manual review

        # Check if manual grading is explicitly required
        require_manual = self.get_setting("require_manual_grading", False)
        if require_manual:
            return None, None  # ✅ Force manual grading even if answer key exists

        acceptable_answers = self.get_setting("acceptable_answers", [])

        # If no acceptable answers configured, require manual grading
        if not acceptable_answers:
            return None, None  # ✅ NULL in DB = requires manual grading

        # Auto-grade if acceptable answers are configured
        case_sensitive = self.get_setting("case_sensitive", False)

        if not case_sensitive:
            student_answer = student_answer.lower()
            acceptable_answers = [ans.lower() for ans in acceptable_answers]

        # Check exact match in acceptable answers
        is_correct = student_answer in acceptable_answers
        return is_correct, float(self.points) if is_correct else 0.0

    def _validate_true_false_table(self, answer_data: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Validate true/false table answers with partial scoring.

        Answer format: {"statement_answers": {index: true/false, ...}}
        Correct answers stored in question_settings:
            - "statement_answers": [bool, ...] (list format from frontend)
            - OR "correct_statements": {id: bool, ...} (dict format, legacy)
        """
        student_answers = answer_data.get("statement_answers", {})

        import logging
        logger = logging.getLogger(__name__)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "TABLE VALIDATION | student_answers=%s answer_data_keys=%s",
                student_answers,
                sorted(answer_data.keys()),
            )

        if not student_answers:
            logger.debug("TABLE VALIDATION | no student_answers provided")
            return False, 0.0

        # Get correct answers from settings - try list format first, then dict format
        correct_answers_list = self.get_setting("statement_answers", [])
        correct_answers_dict = self.get_setting("correct_statements", {})

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "TABLE VALIDATION | statement_answers_count=%s correct_statements_count=%s",
                len(correct_answers_list) if isinstance(correct_answers_list, list) else 0,
                len(correct_answers_dict) if isinstance(correct_answers_dict, dict) else 0,
            )

        # Convert list to dict format for comparison
        if correct_answers_list:
            correct_answers = {str(i): v for i, v in enumerate(correct_answers_list)}
        elif correct_answers_dict:
            correct_answers = {str(k): v for k, v in correct_answers_dict.items()}
        else:
            logger.debug("TABLE VALIDATION | no correct answers in settings")
            return False, 0.0

        def _coerce_bool(value: Any) -> Optional[bool]:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "y", "benar"}:
                    return True
                if lowered in {"false", "0", "no", "n", "salah"}:
                    return False
            return None

        # Convert keys to strings and normalize values to real booleans.
        student_answers = {
            str(k): _coerce_bool(v)
            for k, v in student_answers.items()
        }

        correct_count = 0
        total_statements = len(correct_answers)

        for stmt_id, correct_val in correct_answers.items():
            student_val = student_answers.get(stmt_id)
            correct_bool = _coerce_bool(correct_val)
            if student_val is not None and correct_bool is not None and student_val == correct_bool:
                correct_count += 1

        if total_statements == 0:
            return False, 0.0

        # Partial scoring: score based on correct ratio
        score_ratio = correct_count / total_statements
        points_earned = float(self.points) * score_ratio
        is_correct = score_ratio == 1.0  # Fully correct only if all match

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "TABLE VALIDATION | correct=%s total=%s ratio=%.4f points=%.4f",
                correct_count,
                total_statements,
                score_ratio,
                points_earned,
            )

        return is_correct, points_earned

    def _validate_essay(self, answer_data: Dict[str, Any]) -> Tuple[Optional[bool], Optional[float]]:
        """Essay questions require manual grading.

        Returns (None, None) to indicate answer requires manual grading.
        This prevents auto-setting is_correct=False in database.
        """
        answer_text = answer_data.get("answer_text", "")
        # Essay is NEVER auto-graded - return None to keep as pending
        if answer_text and len(answer_text.strip()) > 0:
            return None, None  # ✅ NULL in DB = pending manual grading
        return None, None  # Empty answer also requires manual review


class QuestionOption(Base):
    """Option model for multiple choice questions."""

    __tablename__ = "question_options"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    option_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=True, default=False)
    order_index = Column(Integer, nullable=False)

    # Legacy fields kept for backward compatibility
    option_group = Column(String(20), default="standard")
    pair_id = Column(String(50), nullable=True)
    option_metadata = Column(JSONB, default={})

    # Relationships
    question = relationship("Question", back_populates="options", lazy="selectin")

    def __repr__(self):
        return f"<Option {self.id}: {self.option_text[:30]}...>"
