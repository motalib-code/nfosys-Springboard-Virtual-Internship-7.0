from abc import ABC, abstractmethod
from typing import List, Set, Tuple

class ScoringStrategy(ABC):
    @abstractmethod
    def calculate_score(
        self,
        correct_option_ids: Set[str],
        selected_option_ids: Set[str],
        max_marks: float,
        negative_marks: float,
        negative_marking_enabled: bool
    ) -> Tuple[float, float]:
        """
        Calculates (marks_awarded, negative_deduction).
        """
        pass


class AllOrNothingStrategy(ScoringStrategy):
    """
    Default Strategy: Exact match of selected set with correct set gets full max_marks.
    Any wrong selection or incomplete set gets -negative_marks (if negative marking enabled),
    unless unattempted (selected set empty -> 0).
    """
    def calculate_score(
        self,
        correct_option_ids: Set[str],
        selected_option_ids: Set[str],
        max_marks: float,
        negative_marks: float,
        negative_marking_enabled: bool
    ) -> Tuple[float, float]:
        if not selected_option_ids:
            return 0.0, 0.0

        if selected_option_ids == correct_option_ids:
            return max_marks, 0.0

        deduction = negative_marks if negative_marking_enabled else 0.0
        return -deduction, deduction


class PartialCreditStrategy(ScoringStrategy):
    """
    Pluggable Partial Credit Strategy:
    Gives proportional credit for correct selections, penalizes wrong selections.
    """
    def calculate_score(
        self,
        correct_option_ids: Set[str],
        selected_option_ids: Set[str],
        max_marks: float,
        negative_marks: float,
        negative_marking_enabled: bool
    ) -> Tuple[float, float]:
        if not selected_option_ids:
            return 0.0, 0.0

        if not correct_option_ids:
            return 0.0, 0.0

        correct_selected = selected_option_ids.intersection(correct_option_ids)
        incorrect_selected = selected_option_ids - correct_option_ids

        per_item = max_marks / len(correct_option_ids)
        score = len(correct_selected) * per_item

        deduction = 0.0
        if incorrect_selected and negative_marking_enabled:
            deduction = len(incorrect_selected) * (negative_marks / len(correct_option_ids))
            score -= deduction

        return score, deduction
