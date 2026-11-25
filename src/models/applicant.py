"""
Applicant domain model (Owned by Member 1).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from src.models.enums import EmploymentType, CityTier
from src.utils.currency import to_decimal
from src.utils.date_utils import calculate_age


@dataclass
class Applicant:
    applicant_id: str
    date_of_birth: date
    monthly_income: Decimal
    existing_emis: Decimal
    employment_type: EmploymentType
    city_tier: CityTier
    credit_score: Optional[int] = None
    name: Optional[str] = ""

    def __post_init__(self):
        self.monthly_income = to_decimal(self.monthly_income)
        self.existing_emis = to_decimal(self.existing_emis)
        if isinstance(self.employment_type, str):
            self.employment_type = EmploymentType.from_str(self.employment_type)
        if isinstance(self.city_tier, str):
            self.city_tier = CityTier.from_str(self.city_tier)
        if self.credit_score is not None:
            self.credit_score = int(self.credit_score)

    def get_age_on(self, on_date: date) -> int:
        """Returns completed age on the specified date."""
        return calculate_age(self.date_of_birth, on_date)
