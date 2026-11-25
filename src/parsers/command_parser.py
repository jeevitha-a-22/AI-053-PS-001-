"""
Command-File Interpreter for Command-File-Driven Engine.
Executes textual instruction scripts line-by-line against a persistent session state.
"""
import os
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any
from src.models.applicant import Applicant
from src.models.loan_application import LoanApplication, LoanDecision
from src.models.loan import Loan
from src.models.repayment import Repayment
from src.models.enums import EmploymentType, CityTier, RepaymentType, PrepaymentType
from src.parsers.applicant_parser import parse_date
from src.services.approval_engine import ApprovalEngine
from src.services.repayment_engine import RepaymentEngine
from src.services.classification_engine import ClassificationEngine
from src.services.foreclosure_engine import ForeclosureEngine
from src.services.statement_engine import StatementEngine
from src.utils.currency import to_decimal


class CommandEngineSession:
    """Stateful runtime session managing applicants, applications, and loans."""

    def __init__(self):
        self.applicants: Dict[str, Applicant] = {}
        self.applications: Dict[str, LoanApplication] = {}
        self.decisions: Dict[str, LoanDecision] = {}
        self.loans: Dict[str, Loan] = {}
        self.logs: List[str] = []

    def log(self, message: str):
        self.logs.append(message)
        print(message)

    def execute_line(self, line: str) -> Optional[Any]:
        """Execute a single command string."""
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        # Split command token and argument payload
        parts = line.split(maxsplit=1)
        command = parts[0].upper()
        args_str = parts[1] if len(parts) > 1 else ""
        args = [arg.strip() for arg in args_str.split(",")] if args_str else []

        if command == "REGISTER_APPLICANT":
            # REGISTER_APPLICANT applicant_id,name,dob,monthly_income,existing_emis,employment_type,credit_score,city_tier
            if len(args) < 6:
                raise ValueError(f"Insufficient arguments for REGISTER_APPLICANT: {line}")
            app_id = args[0]
            name = args[1]
            dob = parse_date(args[2])
            income = to_decimal(args[3])
            emis = to_decimal(args[4])
            emp_type = EmploymentType.from_str(args[5])
            cs_val = args[6] if len(args) > 6 else ""
            credit_score = int(cs_val) if cs_val and cs_val.lower() != "none" and cs_val.isdigit() else None
            tier_val = args[7] if len(args) > 7 else "TIER_2"
            city_tier = CityTier.from_str(tier_val)

            applicant = Applicant(
                applicant_id=app_id,
                name=name,
                date_of_birth=dob,
                monthly_income=income,
                existing_emis=emis,
                employment_type=emp_type,
                credit_score=credit_score,
                city_tier=city_tier,
            )
            self.applicants[app_id] = applicant
            self.log(f"[REGISTERED] Applicant {app_id} ({name}), Income: ₹{income:,.2f}, Score: {credit_score}")
            return applicant

        elif command == "APPLY_LOAN":
            # APPLY_LOAN application_id,applicant_id,amount,tenure_months,purpose,application_date
            if len(args) < 5:
                raise ValueError(f"Insufficient arguments for APPLY_LOAN: {line}")
            app_id = args[0]
            applicant_id = args[1]
            amount = to_decimal(args[2])
            tenure = int(args[3])
            purpose = args[4]
            app_date = parse_date(args[5]) if len(args) > 5 else date.today()

            application = LoanApplication(
                application_id=app_id,
                applicant_id=applicant_id,
                amount=amount,
                tenure_months=tenure,
                purpose=purpose,
                application_date=app_date,
            )
            self.applications[app_id] = application
            self.log(f"[APPLIED] Application {app_id} for Applicant {applicant_id}: ₹{amount:,.2f} for {tenure}m")
            return application

        elif command == "EVALUATE_APPLICATION":
            # EVALUATE_APPLICATION application_id,[loan_id]
            if len(args) < 1:
                raise ValueError("EVALUATE_APPLICATION requires application_id")
            app_id = args[0]
            loan_id = args[1] if len(args) > 1 else f"LN_{app_id}"

            if app_id not in self.applications:
                raise ValueError(f"Application {app_id} not found in session")
            application = self.applications[app_id]

            if application.applicant_id not in self.applicants:
                raise ValueError(f"Applicant {application.applicant_id} not registered")
            applicant = self.applicants[application.applicant_id]

            decision = ApprovalEngine.evaluate_application(applicant, application)
            self.decisions[app_id] = decision

            rule_display = ", ".join(decision.rule_ids) if decision.rule_ids else "None"
            self.log(f"[DECISION] Application {app_id}: {decision.status.value} (Rules: {rule_display})")
            if decision.rejection_reasons:
                for r in decision.rejection_reasons:
                    self.log(f"  - Rejection: {r}")
            if decision.conditions:
                for c in decision.conditions:
                    self.log(f"  - Condition: {c}")

            if decision.is_approved:
                loan = ApprovalEngine.create_loan(
                    loan_id=loan_id,
                    applicant=applicant,
                    application=application,
                    decision=decision,
                    disbursal_date=application.application_date,
                )
                self.loans[loan_id] = loan
                self.log(
                    f"  [DISBURSED] Loan {loan_id}: Sanctioned ₹{loan.sanctioned_amount:,.2f}, "
                    f"Fee ₹{loan.processing_fee:,.2f}, Net Disbursal ₹{loan.net_disbursal:,.2f}, "
                    f"EMI ₹{loan.monthly_emi:,.2f} @ {loan.annual_interest_rate*100:.2f}%"
                )
            return decision

        elif command == "RECORD_REPAYMENT":
            # RECORD_REPAYMENT repayment_id,loan_id,payment_date,amount,repayment_type,[prepayment_choice]
            if len(args) < 5:
                raise ValueError(f"Insufficient arguments for RECORD_REPAYMENT: {line}")
            rep_id = args[0]
            loan_id = args[1]
            pay_date = parse_date(args[2])
            amount = to_decimal(args[3])
            rep_type = RepaymentType.from_str(args[4])
            prep_choice = PrepaymentType.from_str(args[5]) if len(args) > 5 and args[5].strip() else None

            if loan_id not in self.loans:
                raise ValueError(f"Loan {loan_id} not found in session")
            loan = self.loans[loan_id]

            repayment = Repayment(
                repayment_id=rep_id,
                loan_id=loan_id,
                payment_date=pay_date,
                amount=amount,
                repayment_type=rep_type,
                prepayment_choice=prep_choice,
            )
            processed = RepaymentEngine.process_repayment(loan, repayment)
            self.log(
                f"[REPAYMENT] Repayment {rep_id} on {pay_date} for Loan {loan_id} (INR {amount:,.2f}): "
                f"Principal: ₹{processed.principal_cleared:,.2f}, Interest: ₹{processed.interest_cleared:,.2f}, "
                f"Penal: ₹{processed.penal_interest_cleared:,.2f}, Fee: ₹{processed.fee_charged:,.2f}, "
                f"Outstanding: ₹{loan.outstanding_principal:,.2f}"
            )
            return processed

        elif command == "CLASSIFY_LOAN":
            # CLASSIFY_LOAN loan_id,as_of_date
            if len(args) < 2:
                raise ValueError("CLASSIFY_LOAN requires loan_id,as_of_date")
            loan_id = args[0]
            as_of = parse_date(args[1])
            if loan_id not in self.loans:
                raise ValueError(f"Loan {loan_id} not found")
            loan = self.loans[loan_id]

            dpd, classification = ClassificationEngine.update_loan_status(loan, as_of)
            self.log(f"[CLASSIFICATION] Loan {loan_id} on {as_of}: DPD = {dpd}, Asset Class = {classification.value}")
            return dpd, classification

        elif command == "GET_FORECLOSURE_QUOTE":
            # GET_FORECLOSURE_QUOTE loan_id,as_of_date
            if len(args) < 2:
                raise ValueError("GET_FORECLOSURE_QUOTE requires loan_id,as_of_date")
            loan_id = args[0]
            as_of = parse_date(args[1])
            if loan_id not in self.loans:
                raise ValueError(f"Loan {loan_id} not found")
            loan = self.loans[loan_id]

            quote = ForeclosureEngine.calculate_foreclosure_quote(loan, as_of)
            self.log(
                f"[FORECLOSURE QUOTE] Loan {loan_id} on {as_of}: Eligible={quote.is_eligible}, "
                f"Principal: ₹{quote.outstanding_principal:,.2f}, Fee: ₹{quote.foreclosure_fee:,.2f}, "
                f"Pending Interest: ₹{quote.pending_interest:,.2f}, Penal: ₹{quote.pending_penal_interest:,.2f}, "
                f"Total Settlement: ₹{quote.total_settlement_amount:,.2f}"
            )
            return quote

        elif command == "GENERATE_STATEMENT":
            # GENERATE_STATEMENT loan_id,as_of_date
            if len(args) < 2:
                raise ValueError("GENERATE_STATEMENT requires loan_id,as_of_date")
            loan_id = args[0]
            as_of = parse_date(args[1])
            if loan_id not in self.loans:
                raise ValueError(f"Loan {loan_id} not found")
            loan = self.loans[loan_id]
            applicant = self.applicants.get(loan.applicant_id)

            statement = StatementEngine.generate_statement(loan, as_of, applicant)
            text_repr = StatementEngine.format_statement_text(statement)
            self.log(text_repr)
            return statement

        else:
            raise ValueError(f"Unrecognized command: '{command}'")

    def execute_file(self, file_path: str):
        """Execute a text file containing commands."""
        with open(file_path, mode="r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"):
                    continue
                try:
                    self.execute_line(clean_line)
                except Exception as e:
                    self.log(f"Error on line {line_no} ('{clean_line}'): {e}")
                    raise
