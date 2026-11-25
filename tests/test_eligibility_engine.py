"""
Tests for Eligibility Engine (Member 1).
Covers BR-01, BR-02, BR-03, BR-04.
"""
from datetime import date
from decimal import Decimal
import pytest
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.enums import EmploymentType, CityTier
from src.services.eligibility_engine import EligibilityEngine


def create_sample_applicant(
    age: int = 30,
    income: Decimal = Decimal('100000'),
    existing_emis: Decimal = Decimal('10000'),
    emp_type: EmploymentType = EmploymentType.SALARIED,
    credit_score: int = 750,
    dob: date = None,
) -> Applicant:
    if dob is None:
        dob = date(2025 - age, 1, 1)
    return Applicant(
        applicant_id="TEST_APP",
        date_of_birth=dob,
        monthly_income=income,
        existing_emis=existing_emis,
        employment_type=emp_type,
        city_tier=CityTier.TIER_1,
        credit_score=credit_score,
    )


def test_br01_age_valid_range():
    # Age 21
    app_21 = create_sample_applicant(age=21)
    application = LoanApplication("L1", "TEST_APP", Decimal('100000'), 12, "Test", date(2025, 1, 1))
    passed, rules, reasons = EligibilityEngine.check_age_and_tenure(app_21, application)
    assert passed
    assert len(rules) == 0

    # Age 20 -> Fail
    app_20 = create_sample_applicant(age=20)
    passed, rules, reasons = EligibilityEngine.check_age_and_tenure(app_20, application)
    assert not passed
    assert "BR-01" in rules

    # Age 61 -> Fail
    app_61 = create_sample_applicant(age=61)
    passed, rules, reasons = EligibilityEngine.check_age_and_tenure(app_61, application)
    assert not passed
    assert "BR-01" in rules


def test_br01_applicant_exactly_age_60():
    # Applicant exactly 60 years old on application date
    dob = date(1965, 5, 10)
    app_date = date(2025, 5, 10)
    applicant = Applicant("TEST_60", dob, Decimal('100000'), Decimal('0'), EmploymentType.SALARIED, CityTier.TIER_1, 750)
    assert applicant.get_age_on(app_date) == 60

    # Tenure 36 months (ends in 2028-05-10, before 65th birthday in 2030-05-10) -> Pass
    app_valid = LoanApplication("L_60", "TEST_60", Decimal('300000'), 36, "Test", app_date)
    passed, rules, reasons = EligibilityEngine.check_age_and_tenure(applicant, app_valid)
    assert passed

    # Tenure 60 months (ends 2030-05-10, which reaches 65th birthday) -> Fail
    app_invalid = LoanApplication("L_60_long", "TEST_60", Decimal('300000'), 60, "Test", app_date)
    passed, rules, reasons = EligibilityEngine.check_age_and_tenure(applicant, app_invalid)
    assert not passed
    assert "BR-01" in rules


def test_br02_foir_calculation():
    # Salaried: 50% max FOIR
    salaried = create_sample_applicant(income=Decimal('100000'), existing_emis=Decimal('20000'))
    # proposed EMI 25,000 -> Total obligations = 45,000 / 100,000 = 45% -> Pass
    passed, foir, max_foir, rules, reasons = EligibilityEngine.check_foir(salaried, Decimal('25000'))
    assert passed
    assert foir == Decimal('0.45')

    # proposed EMI 35,000 -> Total obligations = 55,000 / 100,000 = 55% -> Fail
    passed, foir, max_foir, rules, reasons = EligibilityEngine.check_foir(salaried, Decimal('35000'))
    assert not passed
    assert foir == Decimal('0.55')
    assert "BR-02" in rules

    # Self-employed: 40% max FOIR
    self_emp = create_sample_applicant(
        income=Decimal('100000'), existing_emis=Decimal('10000'), emp_type=EmploymentType.SELF_EMPLOYED
    )
    # proposed EMI 30,000 -> 40% -> Pass
    passed, foir, max_foir, rules, reasons = EligibilityEngine.check_foir(self_emp, Decimal('30000'))
    assert passed
    assert foir == Decimal('0.40')

    # proposed EMI 35,000 -> 45% -> Fail
    passed, foir, max_foir, rules, reasons = EligibilityEngine.check_foir(self_emp, Decimal('35000'))
    assert not passed
    assert "BR-02" in rules


def test_br03_credit_score():
    # Below 650 -> Reject
    app_low = create_sample_applicant(credit_score=649)
    passed, rules, _ = EligibilityEngine.check_credit_score(app_low)
    assert not passed
    assert "BR-03" in rules

    # Missing credit score -> Reject
    app_none = create_sample_applicant(credit_score=None)
    passed, rules, _ = EligibilityEngine.check_credit_score(app_none)
    assert not passed
    assert "BR-03" in rules

    # 650 to 749 -> Pass
    app_mid = create_sample_applicant(credit_score=700)
    passed, rules, _ = EligibilityEngine.check_credit_score(app_mid)
    assert passed

    # 750+ -> Pass
    app_high = create_sample_applicant(credit_score=750)
    passed, rules, _ = EligibilityEngine.check_credit_score(app_high)
    assert passed


def test_br04_amount_caps():
    # Salaried: 20x monthly income, capped at 25,00,000
    salaried = create_sample_applicant(income=Decimal('100000'))
    # 20x is 20,00,000
    cap = EligibilityEngine.max_loan_amount_cap(salaried)
    assert cap == Decimal('2000000')

    # Salaried with 2,00,000 income -> 20x is 40,00,000 -> Capped at absolute max 25,00,000
    high_earner = create_sample_applicant(income=Decimal('200000'))
    cap_high = EligibilityEngine.max_loan_amount_cap(high_earner)
    assert cap_high == Decimal('2500000')

    # Self-employed: 15x monthly income
    self_emp = create_sample_applicant(income=Decimal('100000'), emp_type=EmploymentType.SELF_EMPLOYED)
    cap_se = EligibilityEngine.max_loan_amount_cap(self_emp)
    assert cap_se == Decimal('1500000')
