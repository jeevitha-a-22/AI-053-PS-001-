"""
Repayment CSV Parser.
"""
import csv
from typing import List, Dict, Optional
from src.models.repayment import Repayment
from src.models.enums import RepaymentType, PrepaymentType
from src.parsers.applicant_parser import parse_date
from src.utils.currency import to_decimal


def parse_repayment_row(row: Dict[str, str]) -> Repayment:
    """Parse a dictionary row into a Repayment model."""
    repayment_id = row.get("repayment_id", "").strip()
    loan_id = row.get("loan_id", "").strip()
    if not repayment_id or not loan_id:
        raise ValueError("repayment_id and loan_id are required")

    payment_date = parse_date(row.get("payment_date", "").strip())
    amount = to_decimal(row.get("amount", "0"))

    type_str = row.get("repayment_type", "EMI").strip()
    repayment_type = RepaymentType.from_str(type_str)

    choice_str = row.get("prepayment_choice", "").strip()
    choice = PrepaymentType.from_str(choice_str) if choice_str and choice_str.lower() != "none" else None

    return Repayment(
        repayment_id=repayment_id,
        loan_id=loan_id,
        payment_date=payment_date,
        amount=amount,
        repayment_type=repayment_type,
        prepayment_choice=choice,
    )


def parse_repayment_csv(file_path: str) -> List[Repayment]:
    """Parse repayments from a CSV file."""
    repayments: List[Repayment] = []
    with open(file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not any(row.values()):
                continue
            repayments.append(parse_repayment_row(row))
    return repayments
