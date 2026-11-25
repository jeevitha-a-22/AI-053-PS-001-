"""
Loan Statement Engine (Owned by Member 2).
Generates comprehensive loan account statements as of any requested date.
"""
from datetime import date
from decimal import Decimal
from typing import Dict, Any, List
from src.models.loan import Loan
from src.models.applicant import Applicant
from src.services.classification_engine import ClassificationEngine
from src.utils.currency import round_currency


class StatementEngine:
    """Generates detailed loan account statements for borrowers and bank operations."""

    @classmethod
    def generate_statement(cls, loan: Loan, as_of_date: date, applicant: Applicant = None) -> Dict[str, Any]:
        """
        Generate complete loan statement as of the specified date.
        """
        # Refresh loan status and accruals up to statement date
        dpd, classification = ClassificationEngine.update_loan_status(loan, as_of_date)

        # Filter repayments up to as_of_date
        filtered_repayments = [r for r in loan.repayments if r.payment_date <= as_of_date]

        total_principal_paid = sum(r.principal_cleared for r in filtered_repayments)
        total_interest_paid = sum(r.interest_cleared for r in filtered_repayments)
        total_penal_paid = sum(r.penal_interest_cleared for r in filtered_repayments)
        total_fees_paid = sum(r.fee_charged for r in filtered_repayments)

        # Summary of installments up to as_of_date
        overdue_installments = []
        for inst in loan.schedule:
            if inst.due_date <= as_of_date and not inst.is_fully_paid:
                overdue_installments.append({
                    "installment_number": inst.installment_number,
                    "due_date": str(inst.due_date),
                    "unpaid_principal": float(inst.unpaid_principal),
                    "unpaid_interest": float(inst.unpaid_interest),
                    "unpaid_penal_interest": float(inst.unpaid_penal_interest),
                    "total_unpaid": float(inst.total_unpaid),
                })

        statement = {
            "account_summary": {
                "loan_id": loan.loan_id,
                "applicant_id": loan.applicant_id,
                "applicant_name": applicant.name if applicant else "N/A",
                "statement_date": str(as_of_date),
                "disbursal_date": str(loan.disbursal_date),
                "sanctioned_amount": float(loan.sanctioned_amount),
                "annual_interest_rate_percent": float(loan.annual_interest_rate * Decimal('100')),
                "original_tenure_months": loan.tenure_months,
                "current_monthly_emi": float(loan.monthly_emi),
                "processing_fee": float(loan.processing_fee),
                "net_disbursal_amount": float(loan.net_disbursal),
                "status": "CLOSED" if loan.is_closed else "ACTIVE",
                "closure_type": loan.closure_type if loan.is_closed else None,
                "closure_date": str(loan.closure_date) if loan.is_closed else None,
            },
            "asset_classification": {
                "dpd": dpd,
                "classification": classification.value,
            },
            "financial_balances": {
                "outstanding_principal": float(loan.outstanding_principal),
                "total_principal_repaid": float(total_principal_paid),
                "total_interest_paid": float(total_interest_paid),
                "total_penal_interest_paid": float(total_penal_paid),
                "total_fees_paid": float(total_fees_paid),
                "total_overdue_emi": float(loan.get_overdue_emi(as_of_date)),
                "pending_penal_interest_due": float(loan.total_penal_interest_due),
                "emis_fully_paid_count": loan.emis_paid_count,
            },
            "overdue_installments": overdue_installments,
            "repayments_history": [
                {
                    "repayment_id": r.repayment_id,
                    "payment_date": str(r.payment_date),
                    "amount": float(r.amount),
                    "type": r.repayment_type.value,
                    "principal_cleared": float(r.principal_cleared),
                    "interest_cleared": float(r.interest_cleared),
                    "penal_interest_cleared": float(r.penal_interest_cleared),
                    "fee_charged": float(r.fee_charged),
                    "excess_refunded": float(r.excess_refunded),
                }
                for r in filtered_repayments
            ],
        }
        return statement

    @classmethod
    def format_statement_text(cls, statement: Dict[str, Any]) -> str:
        """Formats statement dictionary into a human-readable text report."""
        acc = statement["account_summary"]
        bal = statement["financial_balances"]
        asset = statement["asset_classification"]

        lines = [
            "=" * 70,
            f"             PERSONAL LOAN ACCOUNT STATEMENT",
            "=" * 70,
            f"Loan ID:             {acc['loan_id']}",
            f"Applicant ID:        {acc['applicant_id']} ({acc['applicant_name']})",
            f"Statement As-Of:     {acc['statement_date']}",
            f"Disbursal Date:      {acc['disbursal_date']}",
            f"Sanctioned Amount:   INR {acc['sanctioned_amount']:,.2f}",
            f"Interest Rate:       {acc['annual_interest_rate_percent']:.2f}% p.a.",
            f"Tenure:              {acc['original_tenure_months']} months",
            f"Monthly EMI:         INR {acc['current_monthly_emi']:,.2f}",
            f"Account Status:      {acc['status']}" + (f" ({acc['closure_type']} on {acc['closure_date']})" if acc['closure_type'] else ""),
            "-" * 70,
            f"ASSET QUALITY & CLASSIFICATION:",
            f"Days Past Due (DPD): {asset['dpd']} days",
            f"Classification:      {asset['classification']}",
            "-" * 70,
            f"FINANCIAL BALANCES:",
            f"Outstanding Principal:    INR {bal['outstanding_principal']:,.2f}",
            f"Total Overdue EMI:        INR {bal['total_overdue_emi']:,.2f}",
            f"Pending Penal Interest:   INR {bal['pending_penal_interest_due']:,.2f}",
            f"Principal Repaid To Date: INR {bal['total_principal_repaid']:,.2f}",
            f"Interest Repaid To Date:  INR {bal['total_interest_paid']:,.2f}",
            f"Penal Interest Repaid:    INR {bal['total_penal_interest_paid']:,.2f}",
            f"EMIs Fully Paid:          {bal['emis_fully_paid_count']}",
            "=" * 70,
        ]

        repayments = statement["repayments_history"]
        if repayments:
            lines.append("RECENT REPAYMENTS:")
            lines.append(f"{'Date':<12} {'Type':<16} {'Amount (INR)':<14} {'Principal':<12} {'Interest':<10} {'Penal':<8}")
            lines.append("-" * 70)
            for r in repayments:
                lines.append(
                    f"{r['payment_date']:<12} {r['type']:<16} {r['amount']:<14,.2f} "
                    f"{r['principal_cleared']:<12,.2f} {r['interest_cleared']:<10,.2f} {r['penal_interest_cleared']:<8,.2f}"
                )
            lines.append("=" * 70)

        return "\n".join(lines)
