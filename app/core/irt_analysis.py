"""
Item Response Theory (IRT) Analysis Module

Implements a Two-Parameter Logistic (2PL) IRT model for
advanced exam item analysis and student ability estimation.

Part of Phase 4: IRT Analytics Enhancement

Mathematical Model:
P(θ) = 1 / (1 + e^(-a(θ-b)))

Where:
- θ (theta): Student ability parameter
- a: Item discrimination parameter (how well the item differentiates)
- b: Item difficulty parameter (threshold on ability scale)
"""
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from scipy.optimize import minimize


@dataclass
class ItemParameters:
    """IRT item parameters for a single question."""
    question_id: int
    discrimination: float  # 'a' parameter
    difficulty: float      # 'b' parameter
    correct_count: int = 0
    total_responses: int = 0

    @property
    def ctt_difficulty(self) -> float:
        """Classical Test Theory p-value (proportion correct)."""
        if self.total_responses == 0:
            return 0.0
        return self.correct_count / self.total_responses

    @property
    def interpretation(self) -> Dict[str, str]:
        """Human-readable interpretation of parameters."""
        # Discrimination interpretation
        if self.discrimination < 0.5:
            disc_label = "Poor - Item does not differentiate well"
        elif self.discrimination < 1.0:
            disc_label = "Moderate - Acceptable discrimination"
        elif self.discrimination < 1.5:
            disc_label = "Good - Clear differentiation"
        else:
            disc_label = "Excellent - Very high discrimination"

        # Difficulty interpretation (-3 to +3 scale)
        if self.difficulty < -2:
            diff_label = "Very Easy"
        elif self.difficulty < -1:
            diff_label = "Easy"
        elif self.difficulty < 1:
            diff_label = "Moderate"
        elif self.difficulty < 2:
            diff_label = "Difficult"
        else:
            diff_label = "Very Difficult"

        return {
            "discrimination": disc_label,
            "difficulty": diff_label,
            "recommendation": self._get_recommendation()
        }

    def _get_recommendation(self) -> str:
        """Generate recommendation for item improvement."""
        if self.discrimination < 0.5:
            return "REVISE: Item has poor discrimination. Consider rewriting or removing."
        if self.discrimination < 0 or self.ctt_difficulty > 0.95:
            return "REVIEW: Item may be too easy or has issues."
        if self.ctt_difficulty < 0.2:
            return "REVIEW: Item may be too difficult."
        return "KEEP: Item performs well."


@dataclass
class StudentAbility:
    """Estimated student ability from IRT model."""
    student_id: int
    theta: float  # Ability estimate
    standard_error: float = 0.0

    @property
    def percentile(self) -> float:
        """Convert theta to approximate percentile."""
        # Using normal CDF approximation
        from scipy.stats import norm
        return norm.cdf(self.theta) * 100


class TwoParameterLogisticIRT:
    """
    Two-Parameter Logistic (2PL) IRT Model.

    Estimates item parameters (discrimination, difficulty) and
    student abilities using Maximum Likelihood Estimation.
    """

    def __init__(self):
        self.item_params: Dict[int, ItemParameters] = {}
        self.student_abilities: Dict[int, StudentAbility] = {}

    @staticmethod
    def probability(theta: float, a: float, b: float) -> float:
        """
        Calculate probability of correct response.

        P(θ) = 1 / (1 + e^(-a(θ-b)))

        Args:
            theta: Student ability
            a: Item discrimination
            b: Item difficulty

        Returns:
            Probability of correct response (0-1)
        """
        exponent = -a * (theta - b)
        # Clip to prevent overflow
        exponent = np.clip(exponent, -700, 700)
        return 1.0 / (1.0 + np.exp(exponent))

    @staticmethod
    def item_information(theta: float, a: float, b: float) -> float:
        """
        Calculate Fisher Information for an item at given ability.

        I(θ) = a² * P(θ) * Q(θ)

        Higher information = item provides more precise measurement at θ.
        """
        p = TwoParameterLogisticIRT.probability(theta, a, b)
        q = 1.0 - p
        return (a ** 2) * p * q

    def estimate_item_parameters(
        self,
        response_matrix: np.ndarray,
        initial_theta: Optional[np.ndarray] = None
    ) -> Dict[int, ItemParameters]:
        """
        Estimate item parameters using Joint Maximum Likelihood.

        Args:
            response_matrix: N x M matrix (N students, M items)
                            1 = correct, 0 = incorrect, np.nan = missing
            initial_theta: Initial ability estimates (default: raw scores)

        Returns:
            Dictionary of ItemParameters keyed by item index
        """
        n_students, n_items = response_matrix.shape

        # Initialize theta from raw scores if not provided
        if initial_theta is None:
            raw_scores = np.nanmean(response_matrix, axis=1)
            # Transform to standardized scale
            initial_theta = (raw_scores - np.nanmean(raw_scores)) / (np.nanstd(raw_scores) + 0.01)

        theta = initial_theta.copy()

        # Iterate to estimate parameters
        for iteration in range(20):  # EM-like iterations
            # E-step: Estimate item parameters given theta
            for j in range(n_items):
                responses = response_matrix[:, j]
                valid_mask = ~np.isnan(responses)

                if np.sum(valid_mask) < 5:
                    # Not enough data
                    self.item_params[j] = ItemParameters(
                        question_id=j,
                        discrimination=1.0,
                        difficulty=0.0,
                        correct_count=int(np.nansum(responses)),
                        total_responses=int(np.sum(valid_mask))
                    )
                    continue

                y = responses[valid_mask]
                t = theta[valid_mask]

                # MLE for a and b
                result = minimize(
                    self._neg_log_likelihood,
                    x0=[1.0, 0.0],  # Initial [a, b]
                    args=(y, t),
                    method='L-BFGS-B',
                    bounds=[(0.1, 3.0), (-4.0, 4.0)]  # Reasonable bounds
                )

                a_hat, b_hat = result.x

                self.item_params[j] = ItemParameters(
                    question_id=j,
                    discrimination=round(a_hat, 3),
                    difficulty=round(b_hat, 3),
                    correct_count=int(np.sum(y)),
                    total_responses=len(y)
                )

            # M-step: Update theta given item parameters
            new_theta = np.zeros(n_students)
            for i in range(n_students):
                responses = response_matrix[i, :]
                new_theta[i] = self._estimate_single_ability(responses)

            # Check convergence
            if np.max(np.abs(new_theta - theta)) < 0.01:
                break

            theta = new_theta

        return self.item_params

    def _neg_log_likelihood(self, params: np.ndarray, y: np.ndarray, theta: np.ndarray) -> float:
        """Negative log-likelihood for a single item."""
        a, b = params
        p = self.probability(theta, a, b)
        p = np.clip(p, 1e-10, 1 - 1e-10)  # Avoid log(0)

        ll = np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))
        return -ll

    def _estimate_single_ability(self, responses: np.ndarray) -> float:
        """Estimate ability for a single student using MLE."""
        valid_mask = ~np.isnan(responses)
        if np.sum(valid_mask) == 0:
            return 0.0

        y = responses[valid_mask]
        item_indices = np.where(valid_mask)[0]

        def neg_ll_theta(theta_val):
            theta = theta_val[0]
            ll = 0.0
            for j, resp in zip(item_indices, y):
                if j in self.item_params:
                    ip = self.item_params[j]
                    p = self.probability(theta, ip.discrimination, ip.difficulty)
                    p = np.clip(p, 1e-10, 1 - 1e-10)
                    ll += resp * np.log(p) + (1 - resp) * np.log(1 - p)
            return -ll

        result = minimize(
            neg_ll_theta,
            x0=[0.0],
            method='L-BFGS-B',
            bounds=[(-4.0, 4.0)]
        )

        return round(result.x[0], 3)

    def estimate_abilities(
        self,
        response_matrix: np.ndarray,
        student_ids: List[int]
    ) -> Dict[int, StudentAbility]:
        """
        Estimate abilities for all students.

        Args:
            response_matrix: N x M response matrix
            student_ids: List of student IDs

        Returns:
            Dictionary of StudentAbility keyed by student_id
        """
        n_students = response_matrix.shape[0]

        for i in range(n_students):
            theta = self._estimate_single_ability(response_matrix[i, :])
            self.student_abilities[student_ids[i]] = StudentAbility(
                student_id=student_ids[i],
                theta=theta
            )

        return self.student_abilities

    def get_test_information_curve(
        self,
        theta_range: Tuple[float, float] = (-3.0, 3.0),
        n_points: int = 100
    ) -> List[Dict[str, float]]:
        """
        Calculate Test Information Function across ability range.

        Returns TIF which shows measurement precision at different ability levels.
        """
        thetas = np.linspace(theta_range[0], theta_range[1], n_points)
        results = []

        for theta in thetas:
            total_info = sum(
                self.item_information(theta, ip.discrimination, ip.difficulty)
                for ip in self.item_params.values()
            )
            results.append({
                "theta": round(float(theta), 2),
                "information": round(float(total_info), 3),
                "se": round(1.0 / np.sqrt(max(total_info, 0.01)), 3)
            })

        return results
