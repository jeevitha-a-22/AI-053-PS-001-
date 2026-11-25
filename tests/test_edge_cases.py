"""
Tests explicitly covering all 8 edge cases required by the specification:
1. applicant exactly age 60
2. tenure crossing 65th birthday mid-month
3. zero income
4. missing credit score
5. prepayment on EMI due date
6. two repayments on the same day
7. foreclosure with pending penal interest
8. leap-year February
"""
from datetime import date
from decimal import Decimal
import pytest
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.repayment import Repayment
from src.models.enums import EmploymentType, CityTier, DecisionStatus, RepaymentType, PrepaymentType
from src.services.approval_engine import ApprovalEngine
from src.services.eligibility_engine import EligibilityEngine
from src.services.repayment_engine import RepaymentEngine
from src.services.foreclosure_engine import ForeclosureEngine
from src.services.emi_engine import EMIEngine
from src.utils.date_utils import add_months, is_leap_year


def test_edge_case_1_applicant_exactly_age_60():
    """Edge Case 1: Applicant exactly age 60 on date of application."""
    dob = date(1965, 3, 15)
    app_date = date(2025, 3, 15)  # 60th birthday
    applicant = Applicant("A_60", dob, Decimal('100000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    assert applicant.get_age_on(app_date) == 60

    # Tenure 36m matures 2028-03-15, which is well before 65th birthday (2030-03-15)
    application = LoanApplication("L_60", "A_60", Decimal('300000'), 36, "Test", app_date)
    decision = ApprovalEngine.evaluate_application(applicant, application)
    assert decision.status == DecisionStatus.APPROVE


def test_edge_case_2_tenure_crossing_65th_birthday_mid_month():
    """Edge Case 2: Tenure crossing 65th birthday mid-month."""
    # DOB: 1965-05-15. 65th birthday: 2030-05-15.
    dob = date(1965, 5, 15)
    # Application date: 2025-05-20 (Applicant is 60).
    app_date = date(2025, 5, 20)
    applicant = Applicant("A_mid", dob, Decimal('100000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)

    # 60 months tenure from 2025-05-20 ends on 2030-05-20.
    # 2030-05-20 is 5 days AFTER applicant turned 65 on 2030-05-15.
    application = LoanApplication("L_cross", "A_mid", Decimal('300000'), 60, "Test", app_date)
    passed, rules, reasons = EligibilityEngine.check_age_and_tenure(applicant, application)
    assert not passed
    assert "BR-01" in rules
    assert "must end before 65th birthday" in reasons[0]


def test_edge_case_3_zero_income():
    """Edge Case 3: Zero income."""
    applicant = Applicant("A_zero", date(1990, 1, 1), Decimal('0'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    application = LoanApplication("L_zero", "A_zero", Decimal('100000'), 12, "Test", date(2025, 1, 1))

    decision = ApprovalEngine.evaluate_application(applicant, application)
    assert decision.status == DecisionStatus.REJECT
    assert ("BR-02" in decision.rule_ids or "BR-04" in decision.rule_ids)


def test_edge_case_4_missing_credit_score():
    """Edge Case 4: Missing credit score."""
    applicant = Applicant("A_nosc", date(1990, 1, 1), Decimal('80000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, None)
    application = LoanApplication("L_nosc", "A_nosc", Decimal('200000'), 12, "Test", date(2025, 1, 1))

    decision = ApprovalEngine.evaluate_application(applicant, application)
    assert decision.status == DecisionStatus.REJECT
    assert "BR-03" in decision.rule_ids


def test_edge_case_5_prepayment_on_emi_due_date():
    """Edge Case 5: Prepayment on exact EMI due date."""
    applicant = Applicant("A_prep_due", date(1990, 1, 1), Decimal('150000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    application = LoanApplication("L_prep_due", "A_prep_due", Decimal('300000'), 24, "Test", date(2025, 1, 1))
    decision = ApprovalEngine.evaluate_application(applicant, application)
    loan = ApprovalEngine.create_loan("LN_P_DUE", applicant, application, decision, date(2025, 1, 1))

    # Pay first 6 EMIs
    for i in range(6):
        inst = loan.schedule[i]
        RepaymentEngine.process_repayment(loan, Repayment(f"R{i}", loan.loan_id, inst.due_date, inst.emi_amount, RepaymentType.EMI))

    # On 7th installment due date (2025-08-01), pay regular EMI first, then prepayment
    due_date = loan.schedule[6].due_date
    emi_rep = Repayment("R_emi_7", loan.loan_id, due_date, loan.schedule[6].emi_amount, RepaymentType.EMI)
    RepaymentEngine.process_repayment(loan, emi_rep)

    prepay_rep = Repayment("R_prep_7", loan.loan_id, due_date, Decimal('30000'), RepaymentType.PART_PREPAYMENT, PrepaymentType.TENURE_REDUCTION)
    processed = RepaymentEngine.process_repayment(loan, prepay_rep)
    assert processed.principal_cleared > Decimal('0.00')


def test_edge_case_6_two_repayments_on_same_day():
    """Edge Case 6: Two repayments on the same day."""
    applicant = Applicant("A_same", date(1990, 1, 1), Decimal('100000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    application = LoanApplication("L_same", "A_same", Decimal('100000'), 12, "Test", date(2025, 1, 1))
    decision = ApprovalEngine.evaluate_application(applicant, application)
    loan = ApprovalEngine.create_loan("LN_SAME", applicant, application, decision, date(2025, 1, 1))

    inst_1 = loan.schedule[0]
    half_emi = inst_1.emi_amount / Decimal('2')
    same_date = inst_1.due_date

    # Repayment 1 on same_date
    rep1 = Repayment("R_same_1", loan.loan_id, same_date, half_emi, RepaymentType.EMI)
    RepaymentEngine.process_repayment(loan, rep1)
    assert not inst_1.is_fully_paid

    # Repayment 2 on same_date
    rep2 = Repayment("R_same_2", loan.loan_id, same_date, half_emi, RepaymentType.EMI)
    RepaymentEngine.process_repayment(loan, rep2)
    assert inst_1.is_fully_paid
    assert len(loan.repayments) == 2


def test_edge_case_7_foreclosure_with_pending_penal_interest():
    """Edge Case 7: Foreclosure with pending penal interest."""
    applicant = Applicant("A_fc_penal", date(1990, 1, 1), Decimal('200000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    application = LoanApplication("L_fc_penal", "A_fc_penal", Decimal('300000'), 36, "Test", date(2024, 1, 1))
    decision = ApprovalEngine.evaluate_application(applicant, application)
    loan = ApprovalEngine.create_loan("LN_FC_P", applicant, application, decision, date(2024, 1, 1))

    # Pay 12 EMIs on time
    for i in range(12):
        inst = loan.schedule[i]
        RepaymentEngine.process_repayment(loan, Repayment(f"R{i}", loan.loan_id, inst.due_date, inst.emi_amount, RepaymentType.EMI))

    # 13th installment (due 2025-02-01) is overdue and accrues penal interest on 2025-02-20 (19 days late)
    quote_date = date(2025, 2, 20)
    quote = ForeclosureEngine.calculate_foreclosure_quote(loan, quote_date)
    assert quote.is_eligible
    assert quote.pending_penal_interest > Decimal('0.00')

    # Execute foreclosure paying total settlement
    rep_fc = Repayment("R_FC", loan.loan_id, quote_date, quote.total_settlement_amount, RepaymentType.FORECLOSURE)
    RepaymentEngine.process_repayment(loan, rep_fc)
    assert loan.is_closed
    assert loan.total_penal_interest_due == Decimal('0.00')


def test_edge_case_8_leap_year_february():
    """Edge Case 8: Leap-year February."""
    # 2024 is a leap year; 2025 is not
    assert is_leap_year(2024)
    assert not is_leap_year(2025)

    # Disbursal on Jan 31 in a leap year (2024) -> 1 month later should clamp to Feb 29
    leap_jan_31 = date(2024, 1, 31)
    feb_due = add_months(leap_jan_31, 1)
    assert feb_due == date(2024, 2, 29)

    # Disbursal on Jan 31 in a non-leap year (2025) -> 1 month later should clamp to Feb 28
    non_leap_jan_31 = date(2025, 1, 31)
    feb_due_non_leap = add_months(non_leap_jan_31, 1)
    assert feb_due_non_leap == date(2025, 2, 28)

    # Full schedule generation starting on Jan 31, 2024
    schedule = EMIEngine.generate_amortisation_schedule(Decimal('100000'), Decimal('0.12'), 12, leap_jan_31)
    assert schedule[0].due_date == date(2024, 2, 29)
    assert schedule[1].due_date == date(2024, 3, 31)
