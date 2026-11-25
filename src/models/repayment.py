"""
Repayment domain model (Owned by Member 2).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from src.models.enums import RepaymentType, PrepaymentType
from src.utils.currency import to_decimal, round_currency


@dataclass
class Repayment:
    repayment_id: str
    loan_id: str
    payment_date: date
    amount: Decimal
    repayment_type: RepaymentType
    prepayment_choice: Optional[PrepaymentType] = None

    # Settlement allocations
    penal_interest_cleared: Decimal = Decimal('0.00')
    interest_cleared: Decimal = Decimal('0.00')
    principal_cleared: Decimal = Decimal('0.00')
    fee_charged: Decimal = Decimal('0.00')
    excess_refunded: Decimal = Decimal('0.00')

    def __post_init__(self):
        self.amount = round_currency(to_decimal(self.amount))
        if isinstance(self.repayment_type, str):
            self.repayment_type = RepaymentType.from_str(self.repayment_type)
        if isinstance(self.prepayment_choice, str):
            self.prepayment_choice = PrepaymentType.from_str(self.prepayment_choice)
        self.penal_interest_cleared = round_currency(to_decimal(self.penal_interest_cleared))
        self.interest_cleared = round_currency(to_decimal(self.interest_cleared))
        self.principal_cleared = round_currency(to_decimal(self.principal_cleared))
        self.fee_charged = round_currency(to_decimal(self.fee_charged))
        self.excess_refunded = round_currency(to_decimal(self.excess_refunded))
