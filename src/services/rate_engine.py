"""
Rate Engine (Owned by Member 1).
Implements BR-05:
Base rate:
- salaried: 11%
- self-employed: 13%
Adjustments:
- tier-1 city: -0.5%
- tenure > 48 months: +0.5%
- credit score 650–749: +2%
Adjustments are cumulative.
"""
from decimal import Decimal
from typing import Tuple, List
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.enums import EmploymentType, CityTier


class RateEngine:
    """Calculates interest rates based on applicant profile and loan parameters."""

    BASE_RATE_SALARIED = Decimal('0.11')  # 11%
    BASE_RATE_SELF_EMPLOYED = Decimal('0.13')  # 13%

    TIER_1_DISCOUNT = Decimal('-0.005')  # -0.5%
    LONG_TENURE_SURCHARGE = Decimal('0.005')  # +0.5% for tenure > 48
    MODERATE_CREDIT_SURCHARGE = Decimal('0.02')  # +2.0% for credit score 650-749

    @classmethod
    def calculate_rate(cls, applicant: Applicant, application: LoanApplication) -> Tuple[Decimal, List[str]]:
        """
        Calculate cumulative annual interest rate according to BR-05.
        Returns (rate, list_of_applied_adjustments).
        """
        adjustments_log: List[str] = []

        # 1. Base rate
        if applicant.employment_type == EmploymentType.SALARIED:
            rate = cls.BASE_RATE_SALARIED
            adjustments_log.append("Base rate salaried: 11.0%")
        else:
            rate = cls.BASE_RATE_SELF_EMPLOYED
            adjustments_log.append("Base rate self-employed: 13.0%")

        # 2. City tier adjustment
        if applicant.city_tier == CityTier.TIER_1:
            rate += cls.TIER_1_DISCOUNT
            adjustments_log.append("Tier-1 city discount: -0.5%")

        # 3. Tenure adjustment
        if application.tenure_months > 48:
            rate += cls.LONG_TENURE_SURCHARGE
            adjustments_log.append("Tenure > 48 months surcharge: +0.5%")

        # 4. Credit score adjustment (650-749)
        if applicant.credit_score is not None and 650 <= applicant.credit_score <= 749:
            rate += cls.MODERATE_CREDIT_SURCHARGE
            adjustments_log.append("Credit score 650–749 risk adjustment: +2.0%")

        return rate, adjustments_log
