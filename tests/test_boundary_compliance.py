"""
Comprehensive Boundary Compliance Tests for BR-01 through BR-12.
Covers all boundary conditions requested in Step 2.
"""
from datetime import date
from decimal import Decimal
import pytest

from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication, LoanDecision
from src.models.enums import EmploymentType, CityTier, DecisionStatus, Classification, RepaymentType, PrepaymentType
from src.services.eligibility_engine import EligibilityEngine
from src.services.rate_engine import RateEngine
from src.services.emi_engine import EMIEngine
from src.services.approval_engine import ApprovalEngine
from src.services.classification_engine import ClassificationEngine
from src.services.prepayment_engine import PrepaymentEngine
from src.services.foreclosure_engine import ForeclosureEngine
from src.services.repayment_engine import RepaymentEngine


# ==============================================================================
# BR-01: Delayed Disbursal vs Application Date
# ==============================================================================
def test_br01_delayed_disbursal_crossing_65th_birthday():
    """
    BR-01 Regression:
    - Applicant passes application-date maturity check (application_date + tenure < 65th birthday).
    - But delayed disbursal causes actual loan maturity (disbursal_date + tenure) to reach/cross 65th birthday.
    - System must prevent loan creation and reject with BR-01.
    """
    dob = date(1965, 5, 15)  # 65th birthday: 2030-05-15
    app_date = date(2025, 5, 1)  # Applicant age 59 (turns 60 in 14 days)
    delayed_disbursal = date(2025, 5, 20)  # 5 days after 60th birthday

    applicant = Applicant(
        "A_BR01_DELAY", dob, Decimal('100000'), Decimal('0'),
        EmploymentType.SALARIED, CityTier.TIER_1, 750
    )
    # 60-month loan
    app = LoanApplication("L_BR01", "A_BR01_DELAY", Decimal('300000'), 60, "Test", app_date)

    # 1. Without delayed disbursal specified, application passes on application date (maturity: 2030-05-01 < 2030-05-15)
    decision = ApprovalEngine.evaluate_application(applicant, app)
    assert decision.status == DecisionStatus.APPROVE

    # 2. When evaluated with delayed disbursal date (maturity: 2030-05-20 >= 2030-05-15), fails BR-01
    decision_delayed = ApprovalEngine.evaluate_application(applicant, app, disbursal_date=delayed_disbursal)
    assert decision_delayed.status == DecisionStatus.REJECT
    assert "BR-01" in decision_delayed.rule_ids

    # 3. Attempting to create an actual loan with delayed disbursal date raises ValueError
    with pytest.raises(ValueError, match="BR-01 Violation"):
        ApprovalEngine.create_loan("LN_DELAY", applicant, app, decision, disbursal_date=delayed_disbursal)


# ==============================================================================
# BR-02: FOIR Exact Boundaries (50% salaried, 40% self-employed, plus just above)
# ==============================================================================
def test_br02_foir_exact_boundaries():
    # Salaried: exact 50.00% passes
    salaried = Applicant("S1", date(1990, 1, 1), Decimal('100000'), Decimal('20000'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    passed_50, foir_50, _, _, _ = EligibilityEngine.check_foir(salaried, Decimal('30000'))  # 50,000 / 100,000 = 0.50
    assert passed_50
    assert foir_50 == Decimal('0.50')

    # Salaried: just above (50.001%) fails
    passed_50_plus, foir_50_plus, _, rules_50, _ = EligibilityEngine.check_foir(salaried, Decimal('30001'))
    assert not passed_50_plus
    assert "BR-02" in rules_50

    # Self-employed: exact 40.00% passes
    self_emp = Applicant("SE1", date(1990, 1, 1), Decimal('100000'), Decimal('10000'), EmploymentType.SELF_EMPLOYED, CityTier.TIER_1, 750)
    passed_40, foir_40, _, _, _ = EligibilityEngine.check_foir(self_emp, Decimal('30000'))  # 40,000 / 100,000 = 0.40
    assert passed_40
    assert foir_40 == Decimal('0.40')

    # Self-employed: just above (40.001%) fails
    passed_40_plus, foir_40_plus, _, rules_40, _ = EligibilityEngine.check_foir(self_emp, Decimal('30001'))
    assert not passed_40_plus
    assert "BR-02" in rules_40


# ==============================================================================
# BR-03: Credit Score Boundaries (649, 650, 749, 750)
# ==============================================================================
def test_br03_credit_score_boundaries():
    app = LoanApplication("L_CS", "APP_CS", Decimal('200000'), 24, "Test", date(2025, 1, 1))

    # 649: Rejects
    a_649 = Applicant("A649", date(1990, 1, 1), Decimal('80000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_2, 649)
    passed_649, rules_649, _ = EligibilityEngine.check_credit_score(a_649)
    assert not passed_649
    assert "BR-03" in rules_649

    # 650: Passes, gets +2.0% rate surcharge (Salaried base 11% + 2% = 13.0%)
    a_650 = Applicant("A650", date(1990, 1, 1), Decimal('80000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_2, 650)
    passed_650, _, _ = EligibilityEngine.check_credit_score(a_650)
    rate_650, _ = RateEngine.calculate_rate(a_650, app)
    assert passed_650
    assert rate_650 == Decimal('0.130')

    # 749: Passes, gets +2.0% rate surcharge (13.0%)
    a_749 = Applicant("A749", date(1990, 1, 1), Decimal('80000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_2, 749)
    passed_749, _, _ = EligibilityEngine.check_credit_score(a_749)
    rate_749, _ = RateEngine.calculate_rate(a_749, app)
    assert passed_749
    assert rate_749 == Decimal('0.130')

    # 750: Passes, gets base rate (11.0%)
    a_750 = Applicant("A750", date(1990, 1, 1), Decimal('80000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_2, 750)
    passed_750, _, _ = EligibilityEngine.check_credit_score(a_750)
    rate_750, _ = RateEngine.calculate_rate(a_750, app)
    assert passed_750
    assert rate_750 == Decimal('0.110')


# ==============================================================================
# BR-04: Maximum Loan Amount Boundaries (₹25,00,000 and ₹25,00,001)
# ==============================================================================
def test_br04_amount_cap_exact_boundaries():
    # Applicant with high income (₹2,00,000), where 20x would be ₹40,00,000
    applicant = Applicant("A_CAP", date(1990, 1, 1), Decimal('200000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)

    # ₹25,00,000: Exactly at absolute maximum cap -> Passes
    app_25l = LoanApplication("L_25L", "A_CAP", Decimal('2500000'), 36, "Test", date(2025, 1, 1))
    passed_25l, cap_25l, _, _ = EligibilityEngine.check_amount_cap(applicant, app_25l)
    assert passed_25l
    assert cap_25l == Decimal('2500000')

    # ₹25,00,001: Just ₹1 above absolute maximum cap -> Fails BR-04
    app_25l_plus = LoanApplication("L_25L_PLUS", "A_CAP", Decimal('2500001'), 36, "Test", date(2025, 1, 1))
    passed_25l_plus, cap_plus, rules_plus, _ = EligibilityEngine.check_amount_cap(applicant, app_25l_plus)
    assert not passed_25l_plus
    assert "BR-04" in rules_plus
    assert cap_plus == Decimal('2500000')


# ==============================================================================
# BR-05: Tenure Surcharge Boundary (48 vs 49 months)
# ==============================================================================
def test_br05_tenure_surcharge_boundary_48_vs_49():
    applicant = Applicant("A_RATE", date(1990, 1, 1), Decimal('100000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_2, 750)

    # 48 months: tenure > 48 is False -> No surcharge (11.0%)
    app_48 = LoanApplication("L_48", "A_RATE", Decimal('200000'), 48, "Test", date(2025, 1, 1))
    rate_48, _ = RateEngine.calculate_rate(applicant, app_48)
    assert rate_48 == Decimal('0.110')

    # 49 months: tenure > 48 is True -> +0.5% surcharge (11.5%)
    app_49 = LoanApplication("L_49", "A_RATE", Decimal('200000'), 49, "Test", date(2025, 1, 1))
    rate_49, _ = RateEngine.calculate_rate(applicant, app_49)
    assert rate_49 == Decimal('0.115')


# ==============================================================================
# BR-06: Processing Fee Rounding & Clamping Boundaries
# ==============================================================================
def test_br06_processing_fee_boundaries():
    # Min cap ₹999 boundary:
    # 1.5% of 66,500 = 997.50 -> rounded to 998 -> clamped to 999
    fee_min, net_min = EMIEngine.calculate_processing_fee(Decimal('66500'))
    assert fee_min == Decimal('999')
    assert net_min == Decimal('66500') - Decimal('999')

    # 1.5% of 66,600 = 999.00 -> exact minimum cap
    fee_exact_min, _ = EMIEngine.calculate_processing_fee(Decimal('66600'))
    assert fee_exact_min == Decimal('999')

    # 1.5% of 66,700 = 1000.50 -> rounded to 1001 (above minimum cap)
    fee_above_min, _ = EMIEngine.calculate_processing_fee(Decimal('66700'))
    assert fee_above_min == Decimal('1001')

    # Max cap ₹9,999 boundary:
    # 1.5% of 666,500 = 9997.50 -> rounded to 9998 (below maximum cap)
    fee_below_max, _ = EMIEngine.calculate_processing_fee(Decimal('666500'))
    assert fee_below_max == Decimal('9998')

    # 1.5% of 666,600 = 9999.00 -> exact maximum cap
    fee_exact_max, _ = EMIEngine.calculate_processing_fee(Decimal('666600'))
    assert fee_exact_max == Decimal('9999')

    # 1.5% of 700,000 = 10,500 -> clamped to 9999
    fee_above_max, net_above = EMIEngine.calculate_processing_fee(Decimal('700000'))
    assert fee_above_max == Decimal('9999')
    assert net_above == Decimal('700000') - Decimal('9999')


# ==============================================================================
# BR-09: Part Prepayment Month Cutoff (Month 24 vs Month 25)
# ==============================================================================
def test_br09_month_cutoff_24_vs_25():
    # Disbursal 2023-01-01
    disbursal = date(2023, 1, 1)
    applicant = Applicant("A_PREP_BD", date(1990, 1, 1), Decimal('150000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    app = LoanApplication("L_PREP_BD", "A_PREP_BD", Decimal('500000'), 36, "Test", disbursal)
    decision = ApprovalEngine.evaluate_application(applicant, app)
    loan = ApprovalEngine.create_loan("LN_P_BD", applicant, app, decision, disbursal)

    # Simulate 6 EMIs paid
    for i in range(6):
        loan.schedule[i].is_fully_paid = True

    # Month 24 payment date: 2025-01-01 -> 2% fee applies (₹1,000 on ₹50,000)
    fee_24 = PrepaymentEngine.calculate_prepayment_fee(loan, date(2025, 1, 1), Decimal('50000'))
    assert fee_24 == Decimal('1000.00')

    # Month 25 payment date: 2025-02-01 -> 0% fee applies
    fee_25 = PrepaymentEngine.calculate_prepayment_fee(loan, date(2025, 2, 1), Decimal('50000'))
    assert fee_25 == Decimal('0.00')


# ==============================================================================
# BR-10: Foreclosure Month Cutoff (Month 36 vs Month 37)
# ==============================================================================
def test_br10_month_cutoff_36_vs_37():
    # Disbursal 2022-01-01
    disbursal = date(2022, 1, 1)
    applicant = Applicant("A_FC_BD", date(1990, 1, 1), Decimal('200000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    app = LoanApplication("L_FC_BD", "A_FC_BD", Decimal('600000'), 48, "Test", disbursal)
    decision = ApprovalEngine.evaluate_application(applicant, app)
    loan = ApprovalEngine.create_loan("LN_FC_BD", applicant, app, decision, disbursal)

    # Simulate 12 EMIs paid
    for i in range(12):
        loan.schedule[i].is_fully_paid = True

    # Month 36 quote date: 2025-01-01 -> 4% fee applies
    quote_36 = ForeclosureEngine.calculate_foreclosure_quote(loan, date(2025, 1, 1))
    assert quote_36.is_eligible
    assert quote_36.foreclosure_fee_rate == Decimal('0.04')
    assert quote_36.foreclosure_fee > Decimal('0.00')

    # Month 37 quote date: 2025-02-01 -> 0% fee applies (loan older than 36 months)
    quote_37 = ForeclosureEngine.calculate_foreclosure_quote(loan, date(2025, 2, 1))
    assert quote_37.is_eligible
    assert quote_37.foreclosure_fee_rate == Decimal('0.00')
    assert quote_37.foreclosure_fee == Decimal('0.00')


# ==============================================================================
# BR-11: DPD Exact Boundaries (0, 1, 30, 31, 60, 61, 90, 91)
# ==============================================================================
@pytest.mark.parametrize(
    "dpd_days,expected_classification",
    [
        (0, Classification.STANDARD),
        (1, Classification.SMA_0),
        (30, Classification.SMA_0),
        (31, Classification.SMA_1),
        (60, Classification.SMA_1),
        (61, Classification.SMA_2),
        (90, Classification.SMA_2),
        (91, Classification.NPA),
    ],
)
def test_br11_dpd_exact_boundary_values(dpd_days, expected_classification):
    # Setup fresh loan with installment 1 due 2025-02-01
    disbursal = date(2025, 1, 1)
    applicant = Applicant("A_DPD", date(1990, 1, 1), Decimal('100000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    app = LoanApplication("L_DPD", "A_DPD", Decimal('120000'), 12, "Test", disbursal)
    decision = ApprovalEngine.evaluate_application(applicant, app)
    loan = ApprovalEngine.create_loan("LN_DPD_TEST", applicant, app, decision, disbursal)

    due_date = loan.schedule[0].due_date  # 2025-02-01
    from datetime import timedelta
    as_of = due_date + timedelta(days=dpd_days)

    actual_dpd, actual_class = ClassificationEngine.update_loan_status(loan, as_of)
    assert actual_dpd == dpd_days
    assert actual_class == expected_classification


# ==============================================================================
# BR-12: Credit Score < 650 with FOIR Failure Must Strictly REJECT
# ==============================================================================
def test_br12_credit_score_below_650_with_foir_failure_strictly_rejects():
    """
    BR-12 states:
    'If only FOIR or amount cap fails, provide conditional approval...'
    If credit score is below 650, the application must be strictly REJECTED,
    never given APPROVE_WITH_CONDITIONS.
    """
    applicant = Applicant(
        "A_LOW_CS_HIGH_FOIR", date(1990, 1, 1), Decimal('50000'), Decimal('20000'),
        EmploymentType.SALARIED, CityTier.TIER_1, credit_score=620  # Below 650
    )
    # Requested amount will fail FOIR
    app = LoanApplication("L_FAIL_CS_FOIR", "A_LOW_CS_HIGH_FOIR", Decimal('800000'), 36, "Test", date(2025, 1, 1))

    decision = ApprovalEngine.evaluate_application(applicant, app)
    assert decision.status == DecisionStatus.REJECT
    assert "BR-03" in decision.rule_ids
    assert decision.status != DecisionStatus.APPROVE_WITH_CONDITIONS
