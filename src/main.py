"""
Main Entrypoint for AI-053-PS-001 Personal Loan Backend Engine.
Command-line and command-file driven backend engine (NO GUI).
Delegates all business logic to service and parser modules.
"""
import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models.enums import DecisionStatus
from src.parsers.applicant_parser import parse_applicant_csv, parse_date
from src.parsers.application_parser import parse_application_csv
from src.parsers.repayment_parser import parse_repayment_csv
from src.parsers.command_parser import CommandEngineSession
from src.services.approval_engine import ApprovalEngine
from src.services.repayment_engine import RepaymentEngine
from src.services.classification_engine import ClassificationEngine
from src.services.statement_engine import StatementEngine


def run_command_file(file_path: str):
    """Run an instruction script containing command engine directives."""
    print(f"Executing command file: {file_path}")
    session = CommandEngineSession()
    session.execute_file(file_path)
    print("\nCommand file execution completed successfully.")


def run_batch_pipeline(
    applicants_path: str,
    applications_path: str,
    repayments_path: str = None,
    as_of_date_str: str = None,
    output_json_path: str = None,
):
    """
    Run full batch origination, decisioning, repayment, and statement generation.
    """
    as_of = parse_date(as_of_date_str) if as_of_date_str else date.today()
    print("=" * 70)
    print("      AI-053-PS-001: PERSONAL LOAN BATCH ENGINE EXECUTION")
    print("=" * 70)

    # 1. Parse inputs
    print(f"[1/4] Parsing applicants from: {applicants_path}")
    applicants = {a.applicant_id: a for a in parse_applicant_csv(applicants_path)}
    print(f"      Loaded {len(applicants)} applicant(s).")

    print(f"[2/4] Parsing loan applications from: {applications_path}")
    applications = parse_application_csv(applications_path)
    print(f"      Loaded {len(applications)} application(s).")

    # 2. Decision and Loan Origination
    loans = {}
    decisions = {}
    print(f"[3/4] Evaluating eligibility and origination decisions:")
    for app in applications:
        applicant = applicants.get(app.applicant_id)
        if not applicant:
            print(f"      [ERROR] Applicant {app.applicant_id} not found for Application {app.application_id}")
            continue

        decision = ApprovalEngine.evaluate_application(applicant, app)
        decisions[app.application_id] = decision

        rule_tags = f" (Rules: {', '.join(decision.rule_ids)})" if decision.rule_ids else ""
        print(f"      - App {app.application_id}: {decision.status.value}{rule_tags}")

        if decision.is_approved:
            loan_id = f"LN_{app.application_id}"
            loan = ApprovalEngine.create_loan(
                loan_id=loan_id,
                applicant=applicant,
                application=app,
                decision=decision,
                disbursal_date=app.application_date,
            )
            loans[loan_id] = loan
            print(
                f"        Disbursed {loan_id}: ₹{loan.sanctioned_amount:,.2f} for {loan.tenure_months}m "
                f"@ {loan.annual_interest_rate*100:.2f}%, EMI: ₹{loan.monthly_emi:,.2f}"
            )

    # 3. Process Repayments (if supplied)
    if repayments_path:
        print(f"[4/4] Processing repayments from: {repayments_path}")
        repayments = parse_repayment_csv(repayments_path)
        # Sort repayments by payment date
        repayments.sort(key=lambda r: r.payment_date)

        for rep in repayments:
            loan = loans.get(rep.loan_id)
            if not loan:
                print(f"      [WARNING] Loan {rep.loan_id} not found for Repayment {rep.repayment_id}")
                continue
            processed = RepaymentEngine.process_repayment(loan, rep)
            print(
                f"      - {processed.repayment_id} on {processed.payment_date}: ₹{processed.amount:,.2f} "
                f"-> Principal: ₹{processed.principal_cleared:,.2f}, Interest: ₹{processed.interest_cleared:,.2f}, "
                f"Penal: ₹{processed.penal_interest_cleared:,.2f}, Fee: ₹{processed.fee_charged:,.2f}"
            )
    else:
        print("[4/4] No repayments file supplied; skipping payment ledger.")

    # 4. Generate Summaries and Statements
    print("\n" + "=" * 70)
    print(f"PORTFOLIO CLASSIFICATION & STATEMENTS AS OF: {as_of}")
    print("=" * 70)
    all_statements = []
    for loan_id, loan in loans.items():
        applicant = applicants.get(loan.applicant_id)
        stmt = StatementEngine.generate_statement(loan, as_of, applicant)
        all_statements.append(stmt)
        print(StatementEngine.format_statement_text(stmt))
        print()

    if output_json_path:
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(all_statements, f, indent=2)
        print(f"Saved complete batch output to: {output_json_path}")


def main():
    parser = argparse.ArgumentParser(
        description="AI-053-PS-001: Personal Loan Origination and EMI Engine (Command-Driven Backend)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Subcommand: run-commands
    cmd_file_parser = subparsers.add_parser("run-commands", help="Execute command file with directives")
    cmd_file_parser.add_argument("file", help="Path to text file containing instructions")

    # Subcommand: batch
    batch_parser = subparsers.add_parser("batch", help="Batch process applicants, applications, and repayments")
    batch_parser.add_argument("--applicants", required=True, help="Path to applicants CSV")
    batch_parser.add_argument("--applications", required=True, help="Path to loan applications CSV")
    batch_parser.add_argument("--repayments", required=False, default=None, help="Path to repayments CSV")
    batch_parser.add_argument("--as-of-date", required=False, default=None, help="As-of date in YYYY-MM-DD")
    batch_parser.add_argument("--output-json", required=False, default=None, help="Path to save statements in JSON")

    args = parser.parse_args()

    if args.command == "run-commands":
        run_command_file(args.file)
    elif args.command == "batch":
        run_batch_pipeline(
            applicants_path=args.applicants,
            applications_path=args.applications,
            repayments_path=args.repayments,
            as_of_date_str=args.as_of_date,
            output_json_path=args.output_json,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
