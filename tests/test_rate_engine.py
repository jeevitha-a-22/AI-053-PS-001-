"""
Tests for Rate Engine (Member 1).
Implements BR-05 cumulative adjustments.
"""
from datetime import date
from decimal import Decimal
import pytest
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.enums import EmploymentType, CityTier
from src.services.rate_engine import RateEngine


def test_br05_salaried_base_rate():
    applicant = Applicant(
        "A1", date(1990, 1, 1), Decimal('50000'), Decimal('0'),
        EmploymentType.SALARIED, CityTier.TIER_2, credit_score=780
    )
    application = LoanApplication("L1", "A1", Decimal('300000'), 36, "Test", date(2025, 1, 1))
    rate, logs = RateEngine.calculate_rate(applicant, application)
    assert rate == Decimal('0.11')  # 11%


def test_br05_self_employed_base_rate():
    applicant = Applicant(
        "A2", date(1990, 1, 1), Decimal('50000'), Decimal('0'),
        EmploymentType.SELF_EMPLOYED, CityTier.TIER_2, credit_score=780
    )
    application = LoanApplication("L2", "A2", Decimal('300000'), 36, "Test", date(2025, 1, 1))
    rate, logs = RateEngine.calculate_rate(applicant, application)
    assert rate == Decimal('0.13')  # 13%


def test_br05_cumulative_adjustments():
    # Salaried: Base 11%
    # Tier-1: -0.5% (10.5%)
    # Tenure > 48 (60 months): +0.5% (11.0%)
    # Credit score 650-749 (700): +2.0% (13.0%)
    applicant = Applicant(
        "A3", date(1990, 1, 1), Decimal('80000'), Decimal('0'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=700
    )
    application = LoanApplication("L3", "A3", Decimal('500000'), 60, "Test", date(2025, 1, 1))
    rate, logs = RateEngine.calculate_rate(applicant, application)
    assert rate == Decimal('0.130')  # 11 - 0.5 + 0.5 + 2.0 = 13.0%
