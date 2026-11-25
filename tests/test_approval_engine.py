"""
Tests for Approval Engine (Member 1).
Implements full approval, conditional approval (BR-12), and rejections.
"""
from datetime import date
from decimal import Decimal
import pytest
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.enums import EmploymentType, CityTier, DecisionStatus
from src.services.approval_engine import ApprovalEngine


def test_approval_clean_pass():
    applicant = Applicant(
        "A1", date(1992, 5, 15), Decimal('100000'), Decimal('10000'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=780
    )
    application = LoanApplication("L1", "A1", Decimal('500000'), 36, "Renovation", date(2025, 1, 1))

    decision = ApprovalEngine.evaluate_application(applicant, application)
    assert decision.status == DecisionStatus.APPROVE
    assert "BR-01" in decision.rule_ids
    assert decision.sanctioned_amount == Decimal('500000')
    assert decision.sanctioned_tenure_months == 36


def test_rejection_low_credit_score():
    applicant = Applicant(
        "A2", date(1992, 5, 15), Decimal('100000'), Decimal('10000'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=600
    )
    application = LoanApplication("L2", "A2", Decimal('500000'), 36, "Renovation", date(2025, 1, 1))

    decision = ApprovalEngine.evaluate_application(applicant, application)
    assert decision.status == DecisionStatus.REJECT
    assert "BR-03" in decision.rule_ids


def test_br12_conditional_approval_amount_reduction():
    # Applicant with 50,000 income, existing EMI 15,000
    # Salaried 50% max FOIR = 25,000 max EMI -> Available proposed EMI = 10,000
    # Requested 10,00,000 for 36m (which would require EMI ~32,000, failing FOIR and amount cap 20x=10,00,000)
    applicant = Applicant(
        "A3", date(1990, 1, 1), Decimal('50000'), Decimal('15000'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=750
    )
    application = LoanApplication("L3", "A3", Decimal('1000000'), 36, "Car", date(2025, 1, 1))

    decision = ApprovalEngine.evaluate_application(applicant, application)
    assert decision.status == DecisionStatus.APPROVE_WITH_CONDITIONS
    assert "BR-12" in decision.rule_ids
    assert decision.sanctioned_amount < Decimal('1000000')
    assert decision.foir <= Decimal('0.50')
