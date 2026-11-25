"""
Eligibility Engine (Owned by Member 1).
Implements BR-01, BR-02, BR-03, and BR-04.
"""
from datetime import date
from decimal import Decimal
from typing import Tuple, List, Optional
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication
from src.models.enums import EmploymentType
from src.utils.date_utils import calculate_age, add_months
from src.utils.currency import to_decimal, round_rupee


class EligibilityEngine:
    """Evaluates applicant and application eligibility criteria."""

    MAX_ABSOLUTE_LOAN = Decimal('2500000')  # ₹25,00,000 (BR-04)
    MIN_AGE = 21  # BR-01
    MAX_APPLICATION_AGE = 60  # BR-01
    MAX_MATURITY_AGE = 65  # BR-01

    SALARIED_FOIR_CAP = Decimal('0.50')  # 50% (BR-02)
    SELF_EMPLOYED_FOIR_CAP = Decimal('0.40')  # 40% (BR-02)

    SALARIED_INCOME_MULTIPLIER = Decimal('20')  # 20x (BR-04)
    SELF_EMPLOYED_INCOME_MULTIPLIER = Decimal('15')  # 15x (BR-04)

    @classmethod
    def get_65th_birthday(cls, dob: date) -> date:
        """Returns the exact date the applicant turns 65."""
        try:
            return date(dob.year + 65, dob.month, dob.day)
        except ValueError:
            # Handles Feb 29 birthdate in non-leap year
            return date(dob.year + 65, 2, 28)

    @classmethod
    def check_age_and_tenure(cls, applicant: Applicant, application: LoanApplication) -> Tuple[bool, List[str], List[str]]:
        """
        BR-01:
        Age must be 21–60 at application.
        Loan tenure must end before the applicant turns 65.
        """
        passed = True
        rules: List[str] = []
        reasons: List[str] = []

        age_at_app = applicant.get_age_on(application.application_date)
        if age_at_app < cls.MIN_AGE or age_at_app > cls.MAX_APPLICATION_AGE:
            passed = False
            rules.append("BR-01")
            reasons.append(
                f"BR-01: Applicant age {age_at_app} is outside allowed range of {cls.MIN_AGE}–{cls.MAX_APPLICATION_AGE}."
            )

        # Tenure end date
        maturity_date = add_months(application.application_date, application.tenure_months)
        birthday_65 = cls.get_65th_birthday(applicant.date_of_birth)

        # Tenure must end strictly BEFORE turning 65
        if maturity_date >= birthday_65:
            passed = False
            if "BR-01" not in rules:
                rules.append("BR-01")
            reasons.append(
                f"BR-01: Loan maturity date ({maturity_date}) must end before 65th birthday ({birthday_65})."
            )

        return passed, rules, reasons

    @classmethod
    def check_credit_score(cls, applicant: Applicant) -> Tuple[bool, List[str], List[str]]:
        """
        BR-03:
        Credit score:
        - missing -> REJECT
        - below 650 -> REJECT
        - 650–749 -> approve with +2% rate
        - 750+ -> base rate
        """
        if applicant.credit_score is None:
            return False, ["BR-03"], ["BR-03: Missing credit score; applicant rejected."]
        if applicant.credit_score < 650:
            return False, ["BR-03"], [f"BR-03: Credit score {applicant.credit_score} is below minimum requirement of 650."]
        return True, ["BR-03"], []

    @classmethod
    def max_loan_amount_cap(cls, applicant: Applicant) -> Decimal:
        """Calculate max allowed loan by applicant profile under BR-04."""
        if applicant.monthly_income <= Decimal('0'):
            return Decimal('0')

        if applicant.employment_type == EmploymentType.SALARIED:
            income_cap = cls.SALARIED_INCOME_MULTIPLIER * applicant.monthly_income
        else:
            income_cap = cls.SELF_EMPLOYED_INCOME_MULTIPLIER * applicant.monthly_income

        return min(income_cap, cls.MAX_ABSOLUTE_LOAN)

    @classmethod
    def check_amount_cap(cls, applicant: Applicant, application: LoanApplication) -> Tuple[bool, Decimal, List[str], List[str]]:
        """
        BR-04:
        Maximum loan:
        - salaried: 20 × monthly income
        - self-employed: 15 × monthly income
        - absolute maximum: ₹25,00,000
        """
        max_allowed = cls.max_loan_amount_cap(applicant)
        if application.amount <= Decimal('0'):
            return False, max_allowed, ["BR-04"], ["BR-04: Loan amount must be greater than zero."]
        if application.amount > max_allowed:
            return (
                False,
                max_allowed,
                ["BR-04"],
                [f"BR-04: Requested amount ₹{application.amount} exceeds maximum allowed ₹{max_allowed}."],
            )
        return True, max_allowed, ["BR-04"], []

    @classmethod
    def max_foir_limit(cls, employment_type: EmploymentType) -> Decimal:
        """Returns max FOIR ratio under BR-02."""
        if employment_type == EmploymentType.SALARIED:
            return cls.SALARIED_FOIR_CAP
        return cls.SELF_EMPLOYED_FOIR_CAP

    @classmethod
    def check_foir(
        cls, applicant: Applicant, proposed_emi: Decimal
    ) -> Tuple[bool, Decimal, Decimal, List[str], List[str]]:
        """
        BR-02:
        FOIR = (existing EMIs + proposed EMI) / monthly income.
        Maximum FOIR:
        - salaried: 50%
        - self-employed: 40%
        """
        max_foir = cls.max_foir_limit(applicant.employment_type)
        if applicant.monthly_income <= Decimal('0'):
            return (
                False,
                Decimal('1.00'),
                max_foir,
                ["BR-02"],
                ["BR-02: Zero monthly income; FOIR cannot be satisfied."],
            )

        total_obligations = applicant.existing_emis + proposed_emi
        foir = total_obligations / applicant.monthly_income

        if foir > max_foir:
            return (
                False,
                foir,
                max_foir,
                ["BR-02"],
                [
                    f"BR-02: FOIR {foir * 100:.2f}% exceeds maximum permissible {max_foir * 100:.0f}% for {applicant.employment_type.value}."
                ],
            )
        return True, foir, max_foir, ["BR-02"], []
