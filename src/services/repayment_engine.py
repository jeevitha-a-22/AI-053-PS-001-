"""
Repayment Engine (Owned by Member 2).
Orchestrates payment processing for:
- On-time payment
- Grace period payment
- Late payment with penal interest (BR-08)
- Partial payment
- Part prepayment (BR-09)
- Foreclosure (BR-10)
- Multiple repayments on the same day
- Catch-up payment restoring STANDARD (BR-11)
"""
from datetime import date
from decimal import Decimal
from typing import List, Tuple, Optional
from src.models.loan import Loan
from src.models.repayment import Repayment
from src.models.installment import Installment
from src.models.enums import RepaymentType, PrepaymentType, Classification
from src.services.classification_engine import ClassificationEngine
from src.services.prepayment_engine import PrepaymentEngine
from src.services.foreclosure_engine import ForeclosureEngine
from src.utils.currency import round_currency


class RepaymentEngine:
    """Processes all borrower repayments against loan ledger and schedules."""

    @classmethod
    def process_repayment(cls, loan: Loan, repayment: Repayment) -> Repayment:
        """
        Process a repayment against the loan schedule.
        Order of allocation:
        1. Overdue penal interest (oldest installment first)
        2. Overdue interest (oldest installment first)
        3. Overdue principal (oldest installment first)
        4. Current/upcoming installment dues
        5. Part prepayment or principal reduction
        """
        # First update status up to payment date
        ClassificationEngine.update_loan_status(loan, repayment.payment_date)

        # Route foreclosure requests
        if repayment.repayment_type == RepaymentType.FORECLOSURE:
            success, quote, msg = ForeclosureEngine.execute_foreclosure(
                loan=loan,
                payment_amount=repayment.amount,
                payment_date=repayment.payment_date,
            )
            if not success:
                raise ValueError(msg)
            repayment.penal_interest_cleared = quote.pending_penal_interest
            repayment.interest_cleared = quote.pending_interest
            repayment.fee_charged = quote.foreclosure_fee
            repayment.principal_cleared = quote.outstanding_principal
            excess = repayment.amount - quote.total_settlement_amount
            repayment.excess_refunded = max(Decimal('0.00'), excess)
            loan.repayments.append(repayment)
            return repayment

        # Route part-prepayment requests
        if repayment.repayment_type == RepaymentType.PART_PREPAYMENT:
            # Check if there are overdue EMIs or penal interest that must be cleared first
            if loan.total_overdue_emi > Decimal('0.00') or loan.total_penal_interest_due > Decimal('0.00'):
                # Allocate to dues first
                remaining = cls._allocate_dues(loan, repayment)
                if remaining <= Decimal('0.00'):
                    loan.repayments.append(repayment)
                    ClassificationEngine.update_loan_status(loan, repayment.payment_date)
                    return repayment
                prepay_amount = remaining
            else:
                prepay_amount = repayment.amount

            choice = repayment.prepayment_choice or PrepaymentType.TENURE_REDUCTION
            net_p, fee, excess = PrepaymentEngine.apply_part_prepayment(
                loan=loan,
                amount=prepay_amount,
                choice=choice,
                payment_date=repayment.payment_date,
            )
            repayment.principal_cleared += net_p
            repayment.fee_charged += fee
            repayment.excess_refunded += excess
            loan.repayments.append(repayment)
            ClassificationEngine.update_loan_status(loan, repayment.payment_date)
            return repayment

        # Regular or partial EMI repayment
        remaining_funds = cls._allocate_dues(loan, repayment)

        # If funds still remain after clearing all current/due installments:
        if remaining_funds > Decimal('0.00'):
            # Check if applicant wanted excess to prepay principal
            unpaid_future = [inst for inst in loan.schedule if not inst.is_fully_paid]
            if unpaid_future:
                # Apply excess to reduce principal of future installments
                for inst in unpaid_future:
                    if remaining_funds <= Decimal('0.00'):
                        break
                    p_needed = inst.unpaid_principal
                    p_alloc = min(remaining_funds, p_needed)
                    inst.paid_principal += p_alloc
                    repayment.principal_cleared += p_alloc
                    remaining_funds -= p_alloc
                    inst.check_and_update_status()

            repayment.excess_refunded = max(Decimal('0.00'), remaining_funds)

        loan.repayments.append(repayment)

        # Update loan classification and DPD after payment
        ClassificationEngine.update_loan_status(loan, repayment.payment_date)

        # Check if loan is now fully cleared
        if loan.outstanding_principal <= Decimal('0.00') and loan.total_overdue_emi <= Decimal('0.00'):
            loan.is_closed = True
            loan.closure_date = repayment.payment_date
            loan.closure_type = "MATURED"

        return repayment

    @classmethod
    def _allocate_dues(cls, loan: Loan, repayment: Repayment) -> Decimal:
        """
        Allocate available repayment amount across installments in chronological order:
        1. Overdue penal interest across all installments (oldest due date first).
        2. Dues for installments due on or before payment date:
           interest first, then principal (oldest due date first).
        Returns any leftover funds.
        """
        funds = repayment.amount

        # 1. Clear unpaid penal interest across all installments
        for inst in loan.schedule:
            if funds <= Decimal('0.00'):
                break
            penal_needed = inst.unpaid_penal_interest
            if penal_needed > Decimal('0.00'):
                alloc = min(funds, penal_needed)
                inst.penal_interest_paid += alloc
                repayment.penal_interest_cleared += alloc
                funds -= alloc
                inst.last_payment_date = repayment.payment_date
                inst.check_and_update_status()

        # 2. Clear dues for installments due on or before payment date (in chronological order)
        for inst in loan.schedule:
            if funds <= Decimal('0.00'):
                break
            if inst.due_date <= repayment.payment_date and not inst.is_fully_paid:
                # Interest first
                int_needed = inst.unpaid_interest
                if int_needed > Decimal('0.00') and funds > Decimal('0.00'):
                    alloc_int = min(funds, int_needed)
                    inst.paid_interest += alloc_int
                    repayment.interest_cleared += alloc_int
                    funds -= alloc_int

                # Principal next
                p_needed = inst.unpaid_principal
                if p_needed > Decimal('0.00') and funds > Decimal('0.00'):
                    alloc_p = min(funds, p_needed)
                    inst.paid_principal += alloc_p
                    repayment.principal_cleared += alloc_p
                    funds -= alloc_p

                inst.last_payment_date = repayment.payment_date
                inst.check_and_update_status()

        return funds
