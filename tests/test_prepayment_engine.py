"""
Tests for Prepayment Engine (Member 2).
Implements BR-09:
- allowed after 6 EMIs
- minimum ₹25,000
- borrower chooses tenure reduction or EMI reduction
- 2% fee if within first 24 months
"""
from datetime import date
from decimal import Decimal
import pytest
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.repayment import Repayment
from src.models.enums import EmploymentType, CityTier, RepaymentType, PrepaymentType
from src.services.approval_engine import ApprovalEngine
from src.services.repayment_engine import RepaymentEngine
from src.services.prepayment_engine import PrepaymentEngine


def setup_loan_with_paid_emis(emis_to_pay: int):
    applicant = Applicant(
        "APP_PREP", date(1990, 1, 1), Decimal('150000'), Decimal('0'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=780
    )
    application = LoanApplication("APL_PREP", "APP_PREP", Decimal('500000'), 36, "Test", date(2025, 1, 1))
    decision = ApprovalEngine.evaluate_application(applicant, application)
    loan = ApprovalEngine.create_loan("LN_PREP", applicant, application, decision, date(2025, 1, 1))

    for i in range(emis_to_pay):
        inst = loan.schedule[i]
        rep = Repayment(f"REP_{i+1}", loan.loan_id, inst.due_date, inst.emi_amount, RepaymentType.EMI)
        RepaymentEngine.process_repayment(loan, rep)

    return loan


def test_br09_prepayment_ineligible_before_6_emis():
    # Only 5 EMIs paid
    loan = setup_loan_with_paid_emis(5)
    eligible, errors = PrepaymentEngine.check_prepayment_eligibility(
        loan, Decimal('30000'), date(2025, 6, 1)
    )
    assert not eligible
    assert "BR-09" in errors[0]


def test_br09_prepayment_minimum_amount_violation():
    # 6 EMIs paid, but amount < 25,000
    loan = setup_loan_with_paid_emis(6)
    eligible, errors = PrepaymentEngine.check_prepayment_eligibility(
        loan, Decimal('20000'), date(2025, 7, 1)
    )
    assert not eligible
    assert "Minimum part prepayment amount is ₹25,000" in errors[0]


def test_br09_prepayment_tenure_reduction_with_fee():
    loan = setup_loan_with_paid_emis(6)
    orig_tenure = loan.tenure_months
    orig_emi = loan.monthly_emi
    prepay_amount = Decimal('50000')

    # Within 24 months -> 2% fee (₹1,000)
    rep = Repayment(
        "REP_PREPAY", loan.loan_id, date(2025, 7, 5), prepay_amount,
        RepaymentType.PART_PREPAYMENT, PrepaymentType.TENURE_REDUCTION
    )
    processed = RepaymentEngine.process_repayment(loan, rep)

    assert processed.fee_charged == Decimal('1000.00')
    assert processed.principal_cleared == Decimal('49000.00')
    # Monthly EMI stays identical
    assert loan.monthly_emi == orig_emi
    # Tenure reduced!
    assert loan.tenure_months < orig_tenure


def test_br09_prepayment_emi_reduction():
    loan = setup_loan_with_paid_emis(6)
    orig_emi = loan.monthly_emi
    prepay_amount = Decimal('50000')

    rep = Repayment(
        "REP_PREPAY_EMI", loan.loan_id, date(2025, 7, 5), prepay_amount,
        RepaymentType.PART_PREPAYMENT, PrepaymentType.EMI_REDUCTION
    )
    processed = RepaymentEngine.process_repayment(loan, rep)

    assert processed.principal_cleared == Decimal('49000.00')
    # Monthly EMI is reduced!
    assert loan.monthly_emi < orig_emi
