
"""
Tests for Classification Engine (Member 2).
Implements BR-11:
- DPD 1–30 → SMA-0
- DPD 31–60 → SMA-1
- DPD 61–90 → SMA-2
- DPD >90 → NPA
- full catch-up payment restores STANDARD
"""
from datetime import date
from decimal import Decimal
import pytest
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.repayment import Repayment
from src.models.enums import EmploymentType, CityTier, Classification, RepaymentType
from src.services.approval_engine import ApprovalEngine
from src.services.repayment_engine import RepaymentEngine
from src.services.classification_engine import ClassificationEngine


def create_test_loan():
    applicant = Applicant(
        "APP_CLS", date(1990, 1, 1), Decimal('100000'), Decimal('0'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=750
    )
    application = LoanApplication("APL_CLS", "APP_CLS", Decimal('120000'), 12, "Test", date(2025, 1, 1))
    decision = ApprovalEngine.evaluate_application(applicant, application)
    loan = ApprovalEngine.create_loan("LN_CLS", applicant, application, decision, date(2025, 1, 1))
    return loan


def test_br11_classification_progression_and_catch_up():
    loan = create_test_loan()
    test_date = date(2025, 5, 12)

    # Installment 1 is due 2025-02-01

    # On due date -> STANDARD (DPD 0)
    dpd, cls = ClassificationEngine.update_loan_status(loan, date(2025, 2, 1))
    assert dpd == 0
    assert cls == Classification.STANDARD

    # 10 days overdue -> SMA-0 (DPD 10)
    dpd, cls = ClassificationEngine.update_loan_status(loan, date(2025, 2, 11))
    assert dpd == 10
    assert cls == Classification.SMA_0

    # 45 days overdue -> SMA-1 (DPD 45)
    dpd, cls = ClassificationEngine.update_loan_status(loan, date(2025, 3, 18))
    assert dpd == 45
    assert cls == Classification.SMA_1

    # 75 days overdue -> SMA-2 (DPD 75)
    dpd, cls = ClassificationEngine.update_loan_status(loan, date(2025, 4, 17))
    assert dpd == 75
    assert cls == Classification.SMA_2

    # 100 days overdue -> NPA (DPD 100)
    dpd, cls = ClassificationEngine.update_loan_status(loan, test_date)
    assert dpd == 100
    assert cls == Classification.NPA

    # Full catch-up payment restores STANDARD!
    # Amount needed = unpaid EMIs + accumulated penal interest
    total_due = loan.total_overdue_emi + loan.total_penal_interest_due
    rep = Repayment("REP_CATCHUP", loan.loan_id, test_date, total_due, RepaymentType.EMI)
    RepaymentEngine.process_repayment(loan, rep)

    assert loan.dpd == 0
    assert loan.classification == Classification.STANDARD
