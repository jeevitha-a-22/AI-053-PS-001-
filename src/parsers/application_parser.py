"""
Loan Application CSV Parser.
"""
import csv
from typing import List, Dict
from src.models.loan_application import LoanApplication
from src.parsers.applicant_parser import parse_date
from src.utils.currency import to_decimal


def parse_application_row(row: Dict[str, str]) -> LoanApplication:
    """Parse a dictionary row into a LoanApplication model."""
    app_id = row.get("application_id", "").strip()
    applicant_id = row.get("applicant_id", "").strip()
    if not app_id or not applicant_id:
        raise ValueError("application_id and applicant_id are required")

    amount = to_decimal(row.get("amount", "0"))
    tenure = int(row.get("tenure_months", "0"))
    purpose = row.get("purpose", "").strip()
    app_date_str = row.get("application_date", "").strip()
    app_date = parse_date(app_date_str) if app_date_str else parse_date("2026-01-01")

    return LoanApplication(
        application_id=app_id,
        applicant_id=applicant_id,
        amount=amount,
        tenure_months=tenure,
        purpose=purpose,
        application_date=app_date,
    )


def parse_application_csv(file_path: str) -> List[LoanApplication]:
    """Parse applications from a CSV file."""
    applications: List[LoanApplication] = []
    with open(file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not any(row.values()):
                continue
            applications.append(parse_application_row(row))
    return applications
