"""
Loan Application and Decision domain models (Owned by Member 1).
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional
from src.models.enums import DecisionStatus
from src.utils.currency import to_decimal


@dataclass
class LoanApplication:
    application_id: str
    applicant_id: str
    amount: Decimal
    tenure_months: int
    purpose: str
    application_date: date

    def __post_init__(self):
        self.amount = to_decimal(self.amount)
        self.tenure_months = int(self.tenure_months)


@dataclass
class LoanDecision:
    application_id: str
    status: DecisionStatus
    rule_ids: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    sanctioned_amount: Optional[Decimal] = None
    sanctioned_tenure_months: Optional[int] = None
    interest_rate: Optional[Decimal] = None
    processing_fee: Optional[Decimal] = None
    net_disbursal: Optional[Decimal] = None
    proposed_emi: Optional[Decimal] = None
    foir: Optional[Decimal] = None
    conditions: List[str] = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.status in (DecisionStatus.APPROVE, DecisionStatus.APPROVE_WITH_CONDITIONS)
