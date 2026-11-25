"""
Foreclosure Engine (Owned by Member 2).
Implements BR-10:
Foreclosure:
- allowed after 12 EMIs
- 4% of outstanding principal
- 0% if loan is older than 36 months
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Tuple, List, Optional
from src.models.loan import Loan
from src.services.classification_engine import ClassificationEngine
from src.utils.currency import round_currency, round_rupee


@dataclass
class ForeclosureQuote:
    loan_id: str
    quote_date: date
    outstanding_principal: Decimal
    foreclosure_fee_rate: Decimal
    foreclosure_fee: Decimal
    pending_interest: Decimal
    pending_penal_interest: Decimal
    total_settlement_amount: Decimal
    is_eligible: bool
    ineligibility_reasons: List[str]


class ForeclosureEngine:
    """Handles full loan foreclosure and early settlement calculations."""

    MIN_EMIS_REQUIRED = 12  # BR-10: allowed after 12 EMIs
    FORECLOSURE_FEE_RATE = Decimal('0.04')  # 4%
    FEE_EXEMPTION_MONTHS = 36  # 0% if loan older than 36 months

    @classmethod
    def calculate_foreclosure_quote(cls, loan: Loan, request_date: date) -> ForeclosureQuote:
        """
        Generate foreclosure statement and settlement quote as of request_date.
        Includes outstanding principal, foreclosure fee, pending interest, and pending penal interest.
        """
        reasons = []
        if loan.is_closed:
            reasons.append("Loan is already closed.")

        if loan.emis_paid_count < cls.MIN_EMIS_REQUIRED:
            reasons.append(
                f"BR-10: Foreclosure only allowed after {cls.MIN_EMIS_REQUIRED} EMIs paid. "
                f"Currently paid: {loan.emis_paid_count} EMIs."
            )

        is_eligible = len(reasons) == 0

        # Update penal interest to request date
        ClassificationEngine.update_loan_status(loan, request_date)

        outstanding_p = loan.outstanding_principal
        months_elapsed = (request_date.year - loan.disbursal_date.year) * 12 + (
            request_date.month - loan.disbursal_date.month
        )

        if months_elapsed > cls.FEE_EXEMPTION_MONTHS:
            fee_rate = Decimal('0.00')
            fee = Decimal('0.00')
        else:
            fee_rate = cls.FORECLOSURE_FEE_RATE
            fee = round_currency(outstanding_p * fee_rate)

        # Accrued pending interest from overdue or current installments
        pending_int = Decimal('0.00')
        for inst in loan.schedule:
            if not inst.is_fully_paid and inst.due_date <= request_date:
                pending_int += inst.unpaid_interest

        pending_penal = loan.total_penal_interest_due
        total_settlement = round_currency(outstanding_p + fee + pending_int + pending_penal)

        return ForeclosureQuote(
            loan_id=loan.loan_id,
            quote_date=request_date,
            outstanding_principal=outstanding_p,
            foreclosure_fee_rate=fee_rate,
            foreclosure_fee=fee,
            pending_interest=pending_int,
            pending_penal_interest=pending_penal,
            total_settlement_amount=total_settlement,
            is_eligible=is_eligible,
            ineligibility_reasons=reasons,
        )

    @classmethod
    def execute_foreclosure(
        cls, loan: Loan, payment_amount: Decimal, payment_date: date
    ) -> Tuple[bool, ForeclosureQuote, str]:
        """
        Execute loan foreclosure.
        Payment clears penal interest, then regular interest, then foreclosure fee, then principal.
        """
        quote = cls.calculate_foreclosure_quote(loan, payment_date)
        if not quote.is_eligible:
            return False, quote, f"BR-10 Foreclosure Ineligible: {'; '.join(quote.ineligibility_reasons)}"

        if payment_amount < quote.total_settlement_amount:
            return (
                False,
                quote,
                f"Payment amount ₹{payment_amount:,.2f} is less than required settlement amount ₹{quote.total_settlement_amount:,.2f}",
            )

        # Close all remaining installments
        for inst in loan.schedule:
            inst.paid_principal = inst.principal_component
            inst.paid_interest = inst.interest_component
            inst.penal_interest_paid = inst.penal_interest_accrued
            inst.ending_principal = Decimal('0.00')
            inst.last_payment_date = payment_date
            inst.is_fully_paid = True

        loan.is_closed = True
        loan.closure_date = payment_date
        loan.closure_type = "FORECLOSED"
        loan.dpd = 0
        from src.models.enums import Classification
        loan.classification = Classification.STANDARD

        return True, quote, "Loan successfully foreclosed and closed."
