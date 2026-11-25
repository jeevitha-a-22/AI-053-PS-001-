"""
Applicant CSV Parser.
"""
import csv
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Optional
from src.models.applicant import Applicant
from src.models.enums import EmploymentType, CityTier
from src.utils.currency import to_decimal


def parse_date(date_str: str) -> date:
    """Safely parse date in YYYY-MM-DD or DD/MM/YYYY format."""
    cleaned = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unable to parse date string: '{date_str}'")


def parse_applicant_row(row: Dict[str, str]) -> Applicant:
    """Parse a dictionary row into an Applicant model."""
    applicant_id = row.get("applicant_id", "").strip()
    if not applicant_id:
        raise ValueError("applicant_id is required")

    name = row.get("name", "").strip()
    dob_str = row.get("date_of_birth", "").strip()
    if not dob_str:
        raise ValueError(f"date_of_birth is required for applicant {applicant_id}")
    dob = parse_date(dob_str)

    income = to_decimal(row.get("monthly_income", "0"))
    existing_emis = to_decimal(row.get("existing_emis", "0"))

    emp_type_str = row.get("employment_type", "SALARIED")
    emp_type = EmploymentType.from_str(emp_type_str)

    city_tier_str = row.get("city_tier", "TIER_2")
    city_tier = CityTier.from_str(city_tier_str)

    cs_val = row.get("credit_score", "").strip()
    credit_score = int(cs_val) if cs_val and cs_val.lower() != "none" and cs_val.isdigit() else None

    return Applicant(
        applicant_id=applicant_id,
        name=name,
        date_of_birth=dob,
        monthly_income=income,
        existing_emis=existing_emis,
        employment_type=emp_type,
        city_tier=city_tier,
        credit_score=credit_score,
    )


def parse_applicant_csv(file_path: str) -> List[Applicant]:
    """Parse applicants from a CSV file."""
    applicants: List[Applicant] = []
    with open(file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not any(row.values()):
                continue
            applicants.append(parse_applicant_row(row))
    return applicants
