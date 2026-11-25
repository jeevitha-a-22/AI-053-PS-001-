"""
Prepayment Engine (Owned by Member 2).
Implements BR-09:
Part prepayment:
- allowed after 6 EMIs
- minimum ₹25,00,000 / ₹25,000 (minimum ₹25,000)
- borrower chooses tenure reduction or EMI reduction
- 2% fee if within first 24 months
"""
from datetime import date
from decimal import Decimal
from typing import Tuple, List, Optional
from src.models.loan import Loan
from src.models.installment import Installment
from src.models.enums import PrepaymentType
from src.services.emi_engine import EMIEngine
from src.utils.currency import round_currency, round_rupee
from src.utils.date_utils import add_months


class PrepaymentEngine:
    """Handles part prepayments, eligibility validation, and schedule restructuring."""

    MIN_EMIS_REQUIRED = 6
    MIN_PREPAYMENT_AMOUNT = Decimal('25000')  # ₹25,000
    PREPAYMENT_FEE_RATE = Decimal('0.02')  # 2%
    FEE_CUTOFF_MONTHS = 24  # Fee applies within first 24 months

    @classmethod
    def check_prepayment_eligibility(
        cls, loan: Loan, amount: Decimal, payment_date: date
    ) -> Tuple[bool, List[str]]:
        """
        Validate BR-09 criteria:
        1. Loan must have at least 6 EMIs paid.
        2. Amount must be at least ₹25,000.
        3. Amount cannot exceed current outstanding principal.
        """
        errors = []
        if loan.is_closed:
            errors.append("BR-09: Cannot prepay a closed loan.")

        if loan.emis_paid_count < cls.MIN_EMIS_REQUIRED:
            errors.append(
                f"BR-09: Part prepayment only allowed after {cls.MIN_EMIS_REQUIRED} EMIs paid. "
                f"Currently paid: {loan.emis_paid_count} EMIs."
            )

        if amount < cls.MIN_PREPAYMENT_AMOUNT:
            errors.append(
                f"BR-09: Minimum part prepayment amount is ₹{cls.MIN_PREPAYMENT_AMOUNT:,.2f}. "
                f"Received: ₹{amount:,.2f}."
            )

        if amount > loan.outstanding_principal:
            errors.append(
                f"BR-09: Prepayment amount ₹{amount:,.2f} exceeds outstanding principal ₹{loan.outstanding_principal:,.2f}. "
                "Consider foreclosure instead."
            )

        return len(errors) == 0, errors

    @classmethod
    def calculate_prepayment_fee(cls, loan: Loan, payment_date: date, amount: Decimal) -> Decimal:
        """
        BR-09:
        2% fee if within first 24 months from disbursal.
        0% thereafter.
        """
        months_elapsed = (payment_date.year - loan.disbursal_date.year) * 12 + (
            payment_date.month - loan.disbursal_date.month
        )
        if months_elapsed <= cls.FEE_CUTOFF_MONTHS:
            return round_currency(amount * cls.PREPAYMENT_FEE_RATE)
        return Decimal('0.00')

    @classmethod
    def apply_part_prepayment(
        cls,
        loan: Loan,
        amount: Decimal,
        choice: PrepaymentType,
        payment_date: date,
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Execute part prepayment.
        Returns (principal_reduced, fee_charged, excess_refunded).
        """
        is_eligible, errors = cls.check_prepayment_eligibility(loan, amount, payment_date)
        if not is_eligible:
            raise ValueError("; ".join(errors))

        fee = cls.calculate_prepayment_fee(loan, payment_date, amount)
        net_principal_reduction = amount - fee

        if net_principal_reduction <= Decimal('0'):
            raise ValueError("Prepayment amount does not cover the applicable prepayment fee.")

        # Cap reduction to current outstanding principal
        outstanding = loan.outstanding_principal
        if net_principal_reduction > outstanding:
            excess = net_principal_reduction - outstanding
            net_principal_reduction = outstanding
        else:
            excess = Decimal('0.00')

        # Find remaining unpaid installments
        unpaid_installments = [inst for inst in loan.schedule if not inst.is_fully_paid]
        if not unpaid_installments:
            raise ValueError("No unpaid installments remaining to restructure.")

        new_principal = outstanding - net_principal_reduction

        if new_principal <= Decimal('0.00'):
            # Fully cleared principal
            for inst in unpaid_installments:
                inst.paid_principal = inst.principal_component
                inst.ending_principal = Decimal('0.00')
                inst.check_and_update_status()
            loan.is_closed = True
            loan.closure_date = payment_date
            loan.closure_type = "PREPAID_IN_FULL"
            return net_principal_reduction, fee, excess

        # Restructure future schedule based on borrower choice
        if choice == PrepaymentType.TENURE_REDUCTION:
            cls._restructure_tenure_reduction(loan, unpaid_installments, new_principal, payment_date)
        else:
            cls._restructure_emi_reduction(loan, unpaid_installments, new_principal, payment_date)

        return net_principal_reduction, fee, excess

    @classmethod
    def _restructure_tenure_reduction(
        cls,
        loan: Loan,
        unpaid_installments: List[Installment],
        new_principal: Decimal,
        payment_date: date,
    ):
        """
        Keeps monthly EMI the same, recalculating remaining schedule with reduced principal (reducing tenure).
        """
        emi = loan.monthly_emi
        monthly_rate = loan.annual_interest_rate / Decimal('12')
        current_p = new_principal

        rebuilt_schedule = []
        inst_num = unpaid_installments[0].installment_number
        base_due_date = unpaid_installments[0].due_date

        idx = 0
        while current_p > Decimal('0.00'):
            due_date = add_months(base_due_date, idx)
            raw_interest = current_p * monthly_rate
            interest_comp = round_currency(raw_interest)

            if emi <= interest_comp:
                # If existing EMI cannot service interest, force principal payoff
                principal_comp = current_p
                actual_emi = round_currency(principal_comp + interest_comp)
                ending_p = Decimal('0.00')
            elif (current_p + interest_comp) <= emi:
                # Final payoff installment
                principal_comp = current_p
                actual_emi = round_currency(principal_comp + interest_comp)
                ending_p = Decimal('0.00')
            else:
                principal_comp = round_currency(emi - interest_comp)
                actual_emi = round_currency(emi)
                ending_p = round_currency(current_p - principal_comp)

            inst = Installment(
                installment_number=inst_num + idx,
                due_date=due_date,
                beginning_principal=current_p,
                emi_amount=actual_emi,
                principal_component=principal_comp,
                interest_component=interest_comp,
                ending_principal=ending_p,
            )
            rebuilt_schedule.append(inst)
            current_p = ending_p
            idx += 1

        # Replace unpaid portion of schedule
        paid_installments = [inst for inst in loan.schedule if inst.is_fully_paid]
        loan.schedule = paid_installments + rebuilt_schedule
        loan.tenure_months = len(loan.schedule)

    @classmethod
    def _restructure_emi_reduction(
        cls,
        loan: Loan,
        unpaid_installments: List[Installment],
        new_principal: Decimal,
        payment_date: date,
    ):
        """
        Keeps remaining tenure constant, recalculating a lower monthly EMI.
        """
        remaining_months = len(unpaid_installments)
        new_emi = EMIEngine.calculate_emi(new_principal, loan.annual_interest_rate, remaining_months)
        loan.monthly_emi = new_emi

        base_date = unpaid_installments[0].due_date
        # Regenerate remaining installments with new EMI
        recalculated_unpaid = EMIEngine.generate_amortisation_schedule(
            principal=new_principal,
            annual_rate=loan.annual_interest_rate,
            tenure_months=remaining_months,
            disbursal_date=add_months(base_date, -1),
            custom_emi=new_emi,
        )

        start_num = unpaid_installments[0].installment_number
        for i, inst in enumerate(recalculated_unpaid):
            inst.installment_number = start_num + i

        paid_installments = [inst for inst in loan.schedule if inst.is_fully_paid]
        loan.schedule = paid_installments + recalculated_unpaid
