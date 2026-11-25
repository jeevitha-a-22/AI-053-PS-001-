"""
Approval Engine (Owned by Member 1).
Orchestrates eligibility, rate calculation, EMI computation, and conditional approvals (BR-12).
"""
from datetime import date
from decimal import Decimal
from typing import Optional, List, Tuple
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication, LoanDecision
from src.models.loan import Loan
from src.models.enums import DecisionStatus, Classification
from src.services.eligibility_engine import EligibilityEngine
from src.services.rate_engine import RateEngine
from src.services.emi_engine import EMIEngine
from src.utils.currency import to_decimal, round_rupee
from src.utils.date_utils import add_months


class ApprovalEngine:
    """Coordinates the personal loan approval process, enforcing BR-01 to BR-07 and BR-12."""

    @classmethod
    def evaluate_application(
        cls,
        applicant: Applicant,
        application: LoanApplication,
        disbursal_date: Optional[date] = None,
    ) -> LoanDecision:
        """
        Evaluate loan application and make decision:
        APPROVE, APPROVE_WITH_CONDITIONS, or REJECT.
        """
        rejection_reasons: List[str] = []
        rule_ids: List[str] = []
        conditions: List[str] = []

        # 1. BR-01: Age and Tenure
        age_passed, age_rules, age_reasons = EligibilityEngine.check_age_and_tenure(applicant, application)
        if age_passed and disbursal_date is not None:
            birthday_65 = EligibilityEngine.get_65th_birthday(applicant.date_of_birth)
            disbursal_maturity = add_months(disbursal_date, application.tenure_months)
            if disbursal_maturity >= birthday_65:
                age_passed = False
                age_rules.append("BR-01")
                age_reasons.append(
                    f"BR-01: Actual loan maturity date with disbursal ({disbursal_maturity}) "
                    f"must end before 65th birthday ({birthday_65})."
                )
        if not age_passed:
            rule_ids.extend(age_rules)
            rejection_reasons.extend(age_reasons)

        # 2. BR-03: Credit Score
        cs_passed, cs_rules, cs_reasons = EligibilityEngine.check_credit_score(applicant)
        if not cs_passed:
            rule_ids.extend(cs_rules)
            rejection_reasons.extend(cs_reasons)

        # If age or credit score fails, reject immediately (cannot be rescued by BR-12)
        if not age_passed or not cs_passed:
            return LoanDecision(
                application_id=application.application_id,
                status=DecisionStatus.REJECT,
                rule_ids=sorted(list(set(rule_ids))),
                rejection_reasons=rejection_reasons,
            )

        # Calculate applicable interest rate (BR-05)
        rate, rate_adjustments = RateEngine.calculate_rate(applicant, application)

        # Calculate proposed EMI for requested terms (BR-07)
        proposed_emi = EMIEngine.calculate_emi(application.amount, rate, application.tenure_months)

        # 3. BR-04: Amount Cap
        amt_passed, max_amt_cap, amt_rules, amt_reasons = EligibilityEngine.check_amount_cap(applicant, application)

        # 4. BR-02: FOIR
        foir_passed, foir_val, max_foir, foir_rules, foir_reasons = EligibilityEngine.check_foir(applicant, proposed_emi)

        # Case A: Both Amount Cap and FOIR passed -> Full Approval
        if amt_passed and foir_passed:
            fee, net_disbursal = EMIEngine.calculate_processing_fee(application.amount)
            return LoanDecision(
                application_id=application.application_id,
                status=DecisionStatus.APPROVE,
                rule_ids=["BR-01", "BR-02", "BR-03", "BR-04", "BR-05", "BR-06", "BR-07"],
                sanctioned_amount=application.amount,
                sanctioned_tenure_months=application.tenure_months,
                interest_rate=rate,
                processing_fee=fee,
                net_disbursal=net_disbursal,
                proposed_emi=proposed_emi,
                foir=foir_val,
                conditions=[],
            )

        # Case B: Only FOIR or Amount Cap failed -> BR-12 Conditional Approval evaluation
        # "BR-12: If only FOIR or amount cap fails, provide conditional approval using the largest amount
        # and/or longest tenure that passes all applicable rules."
        conditional_res = cls._compute_conditional_approval(
            applicant=applicant,
            application=application,
            rate=rate,
            max_amt_cap=max_amt_cap,
            max_foir=max_foir,
        )

        if conditional_res is not None:
            cond_amount, cond_tenure, cond_emi, cond_foir, cond_notes = conditional_res
            cond_fee, cond_net = EMIEngine.calculate_processing_fee(cond_amount)
            
            # Record the failing rule(s) along with BR-12
            cond_rule_ids = ["BR-12"]
            if not foir_passed:
                cond_rule_ids.append("BR-02")
            if not amt_passed:
                cond_rule_ids.append("BR-04")

            return LoanDecision(
                application_id=application.application_id,
                status=DecisionStatus.APPROVE_WITH_CONDITIONS,
                rule_ids=sorted(cond_rule_ids),
                rejection_reasons=[],
                sanctioned_amount=cond_amount,
                sanctioned_tenure_months=cond_tenure,
                interest_rate=rate,
                processing_fee=cond_fee,
                net_disbursal=cond_net,
                proposed_emi=cond_emi,
                foir=cond_foir,
                conditions=cond_notes,
            )

        # If conditional approval cannot find any viable amount (> 0)
        failed_rules = []
        if not foir_passed:
            failed_rules.extend(foir_rules)
            rejection_reasons.extend(foir_reasons)
        if not amt_passed:
            failed_rules.extend(amt_rules)
            rejection_reasons.extend(amt_reasons)

        return LoanDecision(
            application_id=application.application_id,
            status=DecisionStatus.REJECT,
            rule_ids=sorted(list(set(failed_rules))),
            rejection_reasons=rejection_reasons,
        )

    @classmethod
    def _get_max_permissible_tenure(cls, applicant: Applicant, application_date: date) -> int:
        """
        Calculate maximum permissible tenure in months such that maturity date < 65th birthday.
        Standard maximum tenure is 60 months.
        """
        birthday_65 = EligibilityEngine.get_65th_birthday(applicant.date_of_birth)
        max_possible = 60
        # Step down months until maturity_date < birthday_65
        for t in range(max_possible, 0, -1):
            if add_months(application_date, t) < birthday_65:
                return t
        return 0

    @classmethod
    def _compute_conditional_approval(
        cls,
        applicant: Applicant,
        application: LoanApplication,
        rate: Decimal,
        max_amt_cap: Decimal,
        max_foir: Decimal,
    ) -> Optional[Tuple[Decimal, int, Decimal, Decimal, List[str]]]:
        """
        Compute largest amount and/or longest tenure satisfying BR-01, BR-02, BR-03, BR-04.
        """
        if applicant.monthly_income <= Decimal('0'):
            return None

        # Maximum allowed total monthly obligations
        max_total_emi = applicant.monthly_income * max_foir
        max_available_emi = max_total_emi - applicant.existing_emis

        if max_available_emi <= Decimal('0'):
            return None  # Cannot afford even minimum EMI

        # Check tenure: either requested tenure, or max permissible tenure ending before 65th birthday
        max_tenure_allowed = cls._get_max_permissible_tenure(applicant, application.application_date)
        if max_tenure_allowed <= 0:
            return None

        # Choose best tenure: at least requested tenure (if valid), or longest valid tenure up to 60
        tenure = min(max_tenure_allowed, max(application.tenure_months, max_tenure_allowed))
        # Recalculate rate if tenure changed to > 48 months
        test_app = LoanApplication(
            application_id=application.application_id,
            applicant_id=application.applicant_id,
            amount=application.amount,
            tenure_months=tenure,
            purpose=application.purpose,
            application_date=application.application_date,
        )
        rate, _ = RateEngine.calculate_rate(applicant, test_app)

        # Invert reducing-balance formula to find maximum loan principal for max_available_emi:
        # P = EMI * ((1 + r)^n - 1) / (r * (1 + r)^n)
        monthly_rate = rate / Decimal('12')
        one_plus_r = Decimal('1') + monthly_rate
        power_term = one_plus_r ** tenure

        numerator = max_available_emi * (power_term - Decimal('1'))
        denominator = monthly_rate * power_term

        max_principal_from_foir = numerator / denominator

        # Max sanctioned amount is bounded by requested amount, FOIR cap, and profile cap
        viable_amount = min(application.amount, max_principal_from_foir, max_amt_cap)
        # Round down to nearest 1,000 for clean sanctioning or whole rupee
        viable_amount = Decimal(int(viable_amount // Decimal('1000')) * 1000)

        if viable_amount <= Decimal('0'):
            return None

        # Recompute exact EMI and FOIR for this viable amount
        viable_emi = EMIEngine.calculate_emi(viable_amount, rate, tenure)
        viable_foir = (applicant.existing_emis + viable_emi) / applicant.monthly_income

        if viable_foir > max_foir or viable_amount > max_amt_cap:
            return None

        conditions = [
            f"BR-12: Conditional approval granted.",
            f"Sanctioned amount set to ₹{viable_amount:,.2f} (Requested: ₹{application.amount:,.2f}).",
            f"Tenure set to {tenure} months (Requested: {application.tenure_months} months).",
        ]

        return viable_amount, tenure, viable_emi, viable_foir, conditions

    @classmethod
    def create_loan(
        cls,
        loan_id: str,
        applicant: Applicant,
        application: LoanApplication,
        decision: LoanDecision,
        disbursal_date: Optional[date] = None,
    ) -> Loan:
        """
        Instantiate an active Loan object with full amortisation schedule from an approved decision.
        """
        if not decision.is_approved:
            raise ValueError(f"Cannot create loan for non-approved decision: {decision.status}")

        disbursal = disbursal_date if disbursal_date else application.application_date

        # BR-01: Loan tenure must end before applicant turns 65
        birthday_65 = EligibilityEngine.get_65th_birthday(applicant.date_of_birth)
        actual_maturity = add_months(disbursal, decision.sanctioned_tenure_months)
        if actual_maturity >= birthday_65:
            raise ValueError(
                f"BR-01 Violation: Actual loan maturity date ({actual_maturity}) with disbursal date ({disbursal}) "
                f"must end before applicant's 65th birthday ({birthday_65})."
            )

        schedule = EMIEngine.generate_amortisation_schedule(
            principal=decision.sanctioned_amount,
            annual_rate=decision.interest_rate,
            tenure_months=decision.sanctioned_tenure_months,
            disbursal_date=disbursal,
            custom_emi=decision.proposed_emi,
        )

        return Loan(
            loan_id=loan_id,
            application_id=application.application_id,
            applicant_id=applicant.applicant_id,
            sanctioned_amount=decision.sanctioned_amount,
            annual_interest_rate=decision.interest_rate,
            tenure_months=decision.sanctioned_tenure_months,
            disbursal_date=disbursal,
            processing_fee=decision.processing_fee,
            net_disbursal=decision.net_disbursal,
            monthly_emi=decision.proposed_emi,
            schedule=schedule,
            repayments=[],
            classification=Classification.STANDARD,
            dpd=0,
        )
