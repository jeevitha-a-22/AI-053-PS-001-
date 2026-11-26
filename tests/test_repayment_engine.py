
"""
Tests for Repayment Engine (Member 2).
Covers on-time, grace period, late payment with penal interest, and multiple repayments.
"""
from datetime import date
from decimal import Decimal
import pytest
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.repayment import Repayment
from src.models.enums import EmploymentType, CityTier, RepaymentType
from src.services.approval_engine import ApprovalEngine
from src.services.repayment_engine import RepaymentEngine


def create_test_loan():
    applicant = Applicant(
        "APP_REP", date(1990, 1, 1), Decimal('100000'), Decimal('0'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=750
    )
    application = LoanApplication("APL_REP", "APP_REP", Decimal('120000'), 12, "Test", date(2025, 1, 1))
    decision = ApprovalEngine.evaluate_application(applicant, application)
    loan = ApprovalEngine.create_loan("LN_REP", applicant, application, decision, date(2025, 1, 1))
    return loan


def test_on_time_repayment():
    loan = create_test_loan()
    inst_1 = loan.schedule[0]
    due_date = inst_1.due_date  # 2025-02-01
    emi_amount = inst_1.emi_amount

    # Pay exactly on due date
    rep = Repayment("R1", loan.loan_id, due_date, emi_amount, RepaymentType.EMI)
    processed = RepaymentEngine.process_repayment(loan, rep)

    assert inst_1.is_fully_paid
    assert processed.penal_interest_cleared == Decimal('0.00')
    assert processed.principal_cleared == inst_1.principal_component
    assert processed.interest_cleared == inst_1.interest_component


def test_grace_period_repayment_no_penalty():
    loan = create_test_loan()
    inst_1 = loan.schedule[0]
    # Paid 4 days after due date (within 5-day grace period: BR-08)
    pay_date = date(2025, 2, 5)
    rep = Repayment("R_grace", loan.loan_id, pay_date, inst_1.emi_amount, RepaymentType.EMI)
    processed = RepaymentEngine.process_repayment(loan, rep)

    assert inst_1.is_fully_paid
    assert processed.penal_interest_cleared == Decimal('0.00')
    assert inst_1.penal_interest_accrued == Decimal('0.00')


def test_late_repayment_with_penal_interest():
    loan = create_test_loan()
    inst_1 = loan.schedule[0]
    # Paid 15 days after due date (past 5-day grace period: BR-08)
    pay_date = date(2025, 2, 16)
    # Expected daily penal interest = emi * (0.02 / 30) * 15
    # Let's pay full EMI + expected penalty
    rep = Repayment("R_late", loan.loan_id, pay_date, inst_1.emi_amount + Decimal('200'), RepaymentType.EMI)
    processed = RepaymentEngine.process_repayment(loan, rep)

    assert processed.penal_interest_cleared > Decimal('0.00')
    assert inst_1.is_fully_paid


def test_partial_repayment():
    loan = create_test_loan()
    inst_1 = loan.schedule[0]
    # Pay half the EMI amount
    half_amount = inst_1.emi_amount / Decimal('2')
    rep = Repayment("R_part", loan.loan_id, inst_1.due_date, half_amount, RepaymentType.EMI)
    processed = RepaymentEngine.process_repayment(loan, rep)

    assert not inst_1.is_fully_paid
    assert inst_1.paid_interest == inst_1.interest_component  # Interest paid first
    assert inst_1.unpaid_principal > Decimal('0.00')
