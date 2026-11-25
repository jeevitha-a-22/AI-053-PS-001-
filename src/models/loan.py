"""
Loan domain model representing an active or closed personal loan.
Shared between Member 1 (origination) and Member 2 (servicing).
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional
from src.models.enums import Classification
from src.models.installment import Installment
from src.models.repayment import Repayment
from src.utils.currency import to_decimal, round_currency


@dataclass
class Loan:
    loan_id: str
    application_id: str
    applicant_id: str
    sanctioned_amount: Decimal
    annual_interest_rate: Decimal
    tenure_months: int
    disbursal_date: date
    processing_fee: Decimal
    net_disbursal: Decimal
    monthly_emi: Decimal
    schedule: List[Installment] = field(default_factory=list)
    repayments: List[Repayment] = field(default_factory=list)
    classification: Classification = Classification.STANDARD
    dpd: int = 0
    is_closed: bool = False
    closure_date: Optional[date] = None
    closure_type: Optional[str] = None  # MATURED, FORECLOSED

    def __post_init__(self):
        self.sanctioned_amount = round_currency(to_decimal(self.sanctioned_amount))
        self.annual_interest_rate = to_decimal(self.annual_interest_rate)
        self.tenure_months = int(self.tenure_months)
        self.processing_fee = round_currency(to_decimal(self.processing_fee))
        self.net_disbursal = round_currency(to_decimal(self.net_disbursal))
        self.monthly_emi = round_currency(to_decimal(self.monthly_emi))
        if isinstance(self.classification, str):
            self.classification = Classification(self.classification)

    @property
    def outstanding_principal(self) -> Decimal:
        """
        Total remaining principal due across all installments that have unpaid principal.
        """
        if self.is_closed:
            return Decimal('0.00')
        total = Decimal('0.00')
        for inst in self.schedule:
            total += inst.unpaid_principal
        return round_currency(total)

    @property
    def emis_paid_count(self) -> int:
        """Number of regular monthly installments fully paid."""
        return sum(1 for inst in self.schedule if inst.is_fully_paid)

    @property
    def total_penal_interest_due(self) -> Decimal:
        """Sum of unpaid penal interest across all installments."""
        return round_currency(sum(inst.unpaid_penal_interest for inst in self.schedule))

    def get_overdue_emi(self, as_of_date: Optional[date] = None) -> Decimal:
        """Sum of unpaid EMI across all overdue installments up to as_of_date."""
        target_date = as_of_date if as_of_date else date.today()
        return round_currency(
            sum(
                (inst.unpaid_emi for inst in self.schedule if inst.due_date <= target_date),
                start=Decimal('0.00'),
            )
        )

    @property
    def total_overdue_emi(self) -> Decimal:
        """Sum of unpaid EMI across all currently overdue installments."""
        return self.get_overdue_emi(date.today())

    def get_installment(self, number: int) -> Optional[Installment]:
        for inst in self.schedule:
            if inst.installment_number == number:
                return inst
        return None
