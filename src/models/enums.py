"""
Domain enumerations for the loan origination and EMI engine.
"""
from enum import Enum


class EmploymentType(str, Enum):
    SALARIED = "SALARIED"
    SELF_EMPLOYED = "SELF_EMPLOYED"

    @classmethod
    def from_str(cls, val: str) -> "EmploymentType":
        cleaned = val.strip().upper().replace(" ", "_").replace("-", "_")
        if cleaned in ("SALARIED", "SALARY"):
            return cls.SALARIED
        if cleaned in ("SELF_EMPLOYED", "SELFEMPLOYED", "BUSINESS"):
            return cls.SELF_EMPLOYED
        raise ValueError(f"Unknown employment type: {val}")


class CityTier(str, Enum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"

    @classmethod
    def from_str(cls, val: str) -> "CityTier":
        cleaned = val.strip().upper().replace(" ", "_").replace("-", "_")
        if cleaned in ("TIER_1", "TIER1", "1"):
            return cls.TIER_1
        if cleaned in ("TIER_2", "TIER2", "2"):
            return cls.TIER_2
        if cleaned in ("TIER_3", "TIER3", "3"):
            return cls.TIER_3
        # Default fallback to TIER_2 if not tier-1
        return cls.TIER_2


class DecisionStatus(str, Enum):
    APPROVE = "APPROVE"
    APPROVE_WITH_CONDITIONS = "APPROVE_WITH_CONDITIONS"
    REJECT = "REJECT"


class Classification(str, Enum):
    STANDARD = "STANDARD"
    SMA_0 = "SMA_0"
    SMA_1 = "SMA_1"
    SMA_2 = "SMA_2"
    NPA = "NPA"


class RepaymentType(str, Enum):
    EMI = "EMI"
    PART_PREPAYMENT = "PART_PREPAYMENT"
    FORECLOSURE = "FORECLOSURE"

    @classmethod
    def from_str(cls, val: str) -> "RepaymentType":
        cleaned = val.strip().upper().replace(" ", "_").replace("-", "_")
        if cleaned in ("EMI", "REGULAR", "INSTALLMENT"):
            return cls.EMI
        if cleaned in ("PART_PREPAYMENT", "PARTPREPAYMENT", "PREPAYMENT", "PARTIAL_PREPAYMENT"):
            return cls.PART_PREPAYMENT
        if cleaned in ("FORECLOSURE", "CLOSURE", "FULL_PREPAYMENT"):
            return cls.FORECLOSURE
        raise ValueError(f"Unknown repayment type: {val}")


class PrepaymentType(str, Enum):
    TENURE_REDUCTION = "TENURE_REDUCTION"
    EMI_REDUCTION = "EMI_REDUCTION"

    @classmethod
    def from_str(cls, val: str) -> "PrepaymentType":
        cleaned = val.strip().upper().replace(" ", "_").replace("-", "_")
        if "TENURE" in cleaned:
            return cls.TENURE_REDUCTION
        if "EMI" in cleaned:
            return cls.EMI_REDUCTION
        return cls.TENURE_REDUCTION
