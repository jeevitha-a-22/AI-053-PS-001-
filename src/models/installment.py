"""
Installment model representing a scheduled monthly payment in the amortisation schedule.
Shared interface between Member 1 and Member 2.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from src.utils.currency import to_decimal, round_currency


@dataclass
class Installment:
    installment_number: int
    due_date: date
    beginning_principal: Decimal
    emi_amount: Decimal
    principal_component: Decimal
    interest_component: Decimal
    ending_principal: Decimal

    # Tracking actual payments and dues
    paid_principal: Decimal = Decimal('0.00')
    paid_interest: Decimal = Decimal('0.00')
    penal_interest_accrued: Decimal = Decimal('0.00')
    penal_interest_paid: Decimal = Decimal('0.00')
    is_fully_paid: bool = False
    last_payment_date: Optional[date] = None

    def __post_init__(self):
        self.beginning_principal = round_currency(to_decimal(self.beginning_principal))
        self.emi_amount = round_currency(to_decimal(self.emi_amount))
        self.principal_component = round_currency(to_decimal(self.principal_component))
        self.interest_component = round_currency(to_decimal(self.interest_component))
        self.ending_principal = round_currency(to_decimal(self.ending_principal))
        self.paid_principal = round_currency(to_decimal(self.paid_principal))
        self.paid_interest = round_currency(to_decimal(self.paid_interest))
        self.penal_interest_accrued = round_currency(to_decimal(self.penal_interest_accrued))
        self.penal_interest_paid = round_currency(to_decimal(self.penal_interest_paid))

    @property
    def unpaid_interest(self) -> Decimal:
        return max(Decimal('0.00'), self.interest_component - self.paid_interest)

    @property
    def unpaid_principal(self) -> Decimal:
        return max(Decimal('0.00'), self.principal_component - self.paid_principal)

    @property
    def unpaid_emi(self) -> Decimal:
        return self.unpaid_interest + self.unpaid_principal

    @property
    def unpaid_penal_interest(self) -> Decimal:
        return max(Decimal('0.00'), self.penal_interest_accrued - self.penal_interest_paid)

    @property
    def total_unpaid(self) -> Decimal:
        return self.unpaid_emi + self.unpaid_penal_interest

    def check_and_update_status(self):
        """Update is_fully_paid status flag."""
        if self.unpaid_emi == Decimal('0.00') and self.unpaid_penal_interest == Decimal('0.00'):
            self.is_fully_paid = True
        else:
            self.is_fully_paid = False
