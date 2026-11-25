"""
Tests for Foreclosure Engine (Member 2).
Implements BR-10:
- allowed after 12 EMIs
- 4% of outstanding principal
- 0% if loan is older than 36 months
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
from src.services.foreclosure_engine import ForeclosureEngine


def setup_loan_for_foreclosure(emis_to_pay: int):
    applicant = Applicant(
        "APP_FC", date(1990, 1, 1), Decimal('200000'), Decimal('0'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=780
    )
    # 48 month loan
    application = LoanApplication("APL_FC", "APP_FC", Decimal('500000'), 48, "Test", date(2022, 1, 1))
    decision = ApprovalEngine.evaluate_application(applicant, application)
    loan = ApprovalEngine.create_loan("LN_FC", applicant, application, decision, date(2022, 1, 1))

    for i in range(emis_to_pay):
        inst = loan.schedule[i]
        rep = Repayment(f"REP_{i+1}", loan.loan_id, inst.due_date, inst.emi_amount, RepaymentType.EMI)
        RepaymentEngine.process_repayment(loan, rep)

    return loan


def test_br10_foreclosure_ineligible_under_12_emis():
    loan = setup_loan_for_foreclosure(11)
    quote = ForeclosureEngine.calculate_foreclosure_quote(loan, date(2022, 12, 15))
    assert not quote.is_eligible
    assert "BR-10: Foreclosure only allowed after 12 EMIs" in quote.ineligibility_reasons[0]


def test_br10_foreclosure_with_4_percent_fee():
    loan = setup_loan_for_foreclosure(12)
    # Month 13 (within 36 months) -> 4% fee
    quote_date = date(2023, 1, 15)
    quote = ForeclosureEngine.calculate_foreclosure_quote(loan, quote_date)
    assert quote.is_eligible
    assert quote.foreclosure_fee_rate == Decimal('0.04')
    expected_fee = (quote.outstanding_principal * Decimal('0.04')).quantize(Decimal('0.01'))
    assert quote.foreclosure_fee == expected_fee

    # Execute foreclosure
    rep = Repayment("REP_FC", loan.loan_id, quote_date, quote.total_settlement_amount, RepaymentType.FORECLOSURE)
    processed = RepaymentEngine.process_repayment(loan, rep)
    assert loan.is_closed
    assert loan.closure_type == "FORECLOSED"


def test_br10_foreclosure_zero_fee_after_36_months():
    # 37 EMIs paid -> older than 36 months
    loan = setup_loan_for_foreclosure(37)
    quote_date = date(2025, 2, 15)
    quote = ForeclosureEngine.calculate_foreclosure_quote(loan, quote_date)
    assert quote.is_eligible
    assert quote.foreclosure_fee_rate == Decimal('0.00')
    assert quote.foreclosure_fee == Decimal('0.00')
