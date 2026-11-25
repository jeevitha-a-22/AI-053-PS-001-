"""
Classification and Asset Quality Engine (Owned by Member 2).
Implements BR-08 and BR-11:
BR-08:
5-day grace period.
After grace, penal interest is 2% per month on overdue EMI, calculated daily.

BR-11:
Classification:
- DPD 1–30 → SMA-0
- DPD 31–60 → SMA-1
- DPD 61–90 → SMA-2
- DPD >90 → NPA
- full catch-up payment restores STANDARD
"""
from datetime import date
from decimal import Decimal
from typing import Tuple, Optional
from src.models.loan import Loan
from src.models.enums import Classification
from src.utils.currency import round_currency
from src.utils.date_utils import days_between


class ClassificationEngine:
    """Manages Days Past Due (DPD), asset quality classification, and penal interest calculation."""

    GRACE_DAYS = 5
    MONTHLY_PENAL_RATE = Decimal('0.02')  # 2% per month
    DAILY_PENAL_RATE = Decimal('0.02') / Decimal('30')  # 2% / 30 days

    @classmethod
    def calculate_installment_penal_interest(cls, overdue_amount: Decimal, days_late: int) -> Decimal:
        """
        BR-08:
        5-day grace period.
        If paid within grace period (days_late <= 5), penal interest is 0.
        After grace (days_late > 5), penal interest is 2% per month on overdue EMI, calculated daily.
        """
        if days_late <= cls.GRACE_DAYS or overdue_amount <= Decimal('0.00'):
            return Decimal('0.00')

        penal_interest = overdue_amount * cls.DAILY_PENAL_RATE * Decimal(days_late)
        return round_currency(penal_interest)

    @classmethod
    def update_loan_status(cls, loan: Loan, as_of_date: date) -> Tuple[int, Classification]:
        """
        Calculate DPD and Classification for a loan as of a specific date.
        Also updates accrued penal interest on overdue installments.
        """
        if loan.is_closed:
            loan.dpd = 0
            loan.classification = Classification.STANDARD
            return 0, Classification.STANDARD

        max_dpd = 0
        has_unpaid_overdue = False

        for inst in loan.schedule:
            # Installment is due on or before as_of_date
            if inst.due_date <= as_of_date:
                unpaid_amount = inst.unpaid_emi
                if unpaid_amount > Decimal('0.00'):
                    has_unpaid_overdue = True
                    days_overdue = days_between(inst.due_date, as_of_date)
                    if days_overdue > 0:
                        max_dpd = max(max_dpd, days_overdue)
                        # Accrue penal interest if past grace period
                        inst.penal_interest_accrued = cls.calculate_installment_penal_interest(
                            unpaid_amount, days_overdue
                        )
                else:
                    # Unpaid EMI is 0, but check if penal interest is still pending
                    if inst.unpaid_penal_interest > Decimal('0.00'):
                        has_unpaid_overdue = True
                        days_overdue = days_between(inst.due_date, as_of_date)
                        max_dpd = max(max_dpd, days_overdue)

        # Classification mapping (BR-11)
        if not has_unpaid_overdue or max_dpd == 0:
            classification = Classification.STANDARD
            max_dpd = 0
        elif 1 <= max_dpd <= 30:
            classification = Classification.SMA_0
        elif 31 <= max_dpd <= 60:
            classification = Classification.SMA_1
        elif 61 <= max_dpd <= 90:
            classification = Classification.SMA_2
        else:
            classification = Classification.NPA

        loan.dpd = max_dpd
        loan.classification = classification
        return max_dpd, classification
