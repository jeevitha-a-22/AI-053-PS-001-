"""
EMI Engine and Amortisation Schedule Generator (Owned by Member 1).
Implements BR-06 and BR-07:
BR-06:
Processing fee:
- 1.5% of sanctioned amount
- minimum ₹999
- maximum ₹9,999
- deducted from disbursal

BR-07:
EMI must use the standard reducing-balance formula.
Round EMI to nearest rupee.
Last instalment absorbs rounding difference.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple
from src.models.installment import Installment
from src.utils.currency import to_decimal, round_currency, round_rupee
from src.utils.date_utils import add_months


class EMIEngine:
    """Handles reducing-balance EMI calculations, processing fees, and amortisation schedules."""

    PROCESSING_FEE_RATE = Decimal('0.015')  # 1.5%
    PROCESSING_FEE_MIN = Decimal('999')  # ₹999
    PROCESSING_FEE_MAX = Decimal('9999')  # ₹9,999

    @classmethod
    def calculate_processing_fee(cls, sanctioned_amount: Decimal) -> Tuple[Decimal, Decimal]:
        """
        BR-06:
        Calculate processing fee and net disbursal amount.
        Returns (processing_fee, net_disbursal).
        """
        raw_fee = sanctioned_amount * cls.PROCESSING_FEE_RATE
        # Round fee to nearest 2 decimal places or rupee
        fee = round_rupee(raw_fee)
        if fee < cls.PROCESSING_FEE_MIN:
            fee = cls.PROCESSING_FEE_MIN
        elif fee > cls.PROCESSING_FEE_MAX:
            fee = cls.PROCESSING_FEE_MAX

        net_disbursal = max(Decimal('0'), sanctioned_amount - fee)
        return fee, net_disbursal

    @classmethod
    def calculate_emi(cls, principal: Decimal, annual_rate: Decimal, tenure_months: int) -> Decimal:
        """
        BR-07:
        Standard reducing-balance EMI formula:
        EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
        Rounded to nearest whole rupee.
        """
        if principal <= Decimal('0') or tenure_months <= 0:
            return Decimal('0')

        if annual_rate <= Decimal('0'):
            # Zero interest edge-case
            return round_rupee(principal / Decimal(tenure_months))

        monthly_rate = annual_rate / Decimal('12')
        # Decimal power calculation: (1 + r)^n
        one_plus_r = Decimal('1') + monthly_rate
        power_term = one_plus_r ** tenure_months

        numerator = principal * monthly_rate * power_term
        denominator = power_term - Decimal('1')

        raw_emi = numerator / denominator
        return round_rupee(raw_emi)

    @classmethod
    def generate_amortisation_schedule(
        cls,
        principal: Decimal,
        annual_rate: Decimal,
        tenure_months: int,
        disbursal_date: date,
        custom_emi: Decimal = None,
    ) -> List[Installment]:
        """
        BR-07:
        Generate complete monthly amortisation schedule.
        Reducing-balance interest component = Beginning Principal * (annual_rate / 12)
        Principal component = EMI - Interest component
        Last instalment absorbs rounding difference:
        - Remaining principal is fully cleared.
        - Last EMI = Remaining Principal + Last Interest component.
        """
        if principal <= Decimal('0') or tenure_months <= 0:
            return []

        monthly_rate = annual_rate / Decimal('12')
        emi = custom_emi if custom_emi is not None else cls.calculate_emi(principal, annual_rate, tenure_months)

        schedule: List[Installment] = []
        current_principal = round_currency(principal)

        for month in range(1, tenure_months + 1):
            due_date = add_months(disbursal_date, month)
            beginning_principal = current_principal

            # Interest for the month
            raw_interest = beginning_principal * monthly_rate
            interest_component = round_currency(raw_interest)

            if month == tenure_months:
                # BR-07: Last instalment absorbs rounding difference
                principal_component = beginning_principal
                actual_emi = round_currency(principal_component + interest_component)
                ending_principal = Decimal('0.00')
            else:
                principal_component = round_currency(emi - interest_component)
                # Safeguard against over-reduction in unusual rounding
                if principal_component > beginning_principal:
                    principal_component = beginning_principal
                    actual_emi = round_currency(principal_component + interest_component)
                    ending_principal = Decimal('0.00')
                else:
                    actual_emi = round_currency(emi)
                    ending_principal = round_currency(beginning_principal - principal_component)

            current_principal = ending_principal

            installment = Installment(
                installment_number=month,
                due_date=due_date,
                beginning_principal=beginning_principal,
                emi_amount=actual_emi,
                principal_component=principal_component,
                interest_component=interest_component,
                ending_principal=ending_principal,
            )
            schedule.append(installment)

            if ending_principal == Decimal('0.00'):
                break

        return schedule
