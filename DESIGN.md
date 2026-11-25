# System Design Document: AI-053-PS-001 Personal Loan Engine

## 1. Architectural Overview

The `AI-053-PS-001` backend engine is designed around clean architecture principles with strict modular boundaries, domain-driven models, high-precision financial mathematics, and complete decoupling between the command-file execution layer and core banking business logic.

```
                          +-------------------------+
                          |   Command-Line & File   |
                          |  Parsers (NO GUI Layer) |
                          +------------+------------+
                                       |
                   +-------------------+-------------------+
                   |                                       |
                   v                                       v
        +----------------------+               +----------------------+
        |   Member 1 Domain    |               |   Member 2 Domain    |
        |  Origination & Math  |               | Servicing & Ledger   |
        +----------+-----------+               +-----------+----------+
                   |                                       |
                   +-------------------+-------------------+
                                       |
                                       v
                          +-------------------------+
                          |      Domain Models      |
                          |   (Shared Interfaces)   |
                          +-------------------------+
```

---

## 2. Domain Models & Contracts

### 2.1 Core Entities

1. **`Applicant`**:
   - Holds demographic, employment, and credit profile.
   - Enforces valid types (`EmploymentType`: `SALARIED`, `SELF_EMPLOYED`; `CityTier`: `TIER_1`, `TIER_2`, `TIER_3`).
   - Computes age as of any reference date.

2. **`LoanApplication`**:
   - Represents the loan request: requested amount, tenure in months, purpose, application date.

3. **`LoanDecision`**:
   - Captures underwriting outcome (`APPROVE`, `APPROVE_WITH_CONDITIONS`, `REJECT`).
   - Records rule IDs, rejection reasons, sanctioned amount, revised tenure, interest rate, fee, net disbursal, and proposed EMI.

4. **`Installment`**:
   - Discrete scheduled entry in the monthly amortisation schedule.
   - Maintains beginning principal, scheduled EMI, principal component, interest component, ending principal.
   - Tracks actual servicing: `paid_principal`, `paid_interest`, `penal_interest_accrued`, `penal_interest_paid`, `is_fully_paid`.

5. **`Repayment`**:
   - Record of an incoming payment transaction.
   - Specifies `RepaymentType` (`EMI`, `PART_PREPAYMENT`, `FORECLOSURE`) and optional `PrepaymentType`.
   - Records allocations: `penal_interest_cleared`, `interest_cleared`, `principal_cleared`, `fee_charged`, `excess_refunded`.

6. **`Loan`**:
   - Aggregate root for an active personal loan.
   - Encapsulates terms, amortisation schedule, repayment ledger, DPD, asset classification, and closure status.

---

## 3. Financial Precision & Mathematics

### 3.1 Python `Decimal` Policy
Binary floating-point arithmetic (`float`) causes precision errors (e.g. `0.1 + 0.2 != 0.3`). In compliance with banking standards:
- All monetary amounts, interest rates, FOIR ratios, and penalty figures are represented using `Decimal`.
- Quantization rules:
  - Monetary values: quantized to 2 decimal places (`Decimal('0.01')`) using `ROUND_HALF_UP`.
  - EMI rounding: rounded to the nearest whole rupee (`Decimal('1')`) using `ROUND_HALF_UP` (BR-07).
  - Rates: calculated with full Decimal precision and preserved in basis points.

### 3.2 Reducing-Balance Formula
The standard reducing-balance formula is implemented:
$$EMI = P \times \frac{r(1+r)^n}{(1+r)^n - 1}$$
where:
- $P$ = Principal amount
- $r$ = Monthly interest rate = $\text{annual\_rate} / 12$
- $n$ = Tenure in months

### 3.3 Rounding Difference Absorption
In the final installment ($m = n$):
$$\text{Principal Component} = \text{Beginning Principal}$$
$$\text{Last EMI} = \text{Beginning Principal} + \text{Interest Component}$$
$$\text{Ending Principal} = 0.00$$
This guarantees the entire principal is amortized to zero.

---

## 4. Subsystem Breakdown

### 4.1 Member 1: Origination & Underwriting Subsystem
- **`EligibilityEngine`**:
  - `check_age_and_tenure`: Age between 21 and 60. Maturity date $< 65$th birthday.
  - `check_credit_score`: Credit score $\ge 650$. Rejects below 650 or missing.
  - `check_amount_cap`: $20\times$ monthly income (salaried) or $15\times$ (self-employed), capped at ₹25,00,000.
  - `check_foir`: Existing + Proposed EMI $\le 50\%$ (salaried) or $40\%$ (self-employed).
- **`RateEngine`**:
  - Base rates: Salaried 11%, Self-employed 13%.
  - Adjustments: Tier-1 (-0.5%), tenure > 48m (+0.5%), credit 650–749 (+2.0%).
- **`ApprovalEngine`**:
  - Orchestrates rules.
  - Inverts the reducing-balance formula to calculate maximum eligible loan amount under BR-12 conditional approval:
    $$P_{\max} = \frac{EMI_{\text{available}} \times ((1+r)^n - 1)}{r(1+r)^n}$$

### 4.2 Member 2: Servicing, Restructuring & Classification Subsystem
- **`ClassificationEngine`**:
  - DPD = days between oldest unpaid due date and current date.
  - 5-day grace period: if days $\le 5$, penal interest is zero.
  - If days $> 5$: Daily penal interest $= \text{overdue\_emi} \times \left(\frac{0.02}{30}\right) \times \text{days\_overdue}$.
  - Asset quality: DPD 0 $\rightarrow$ STANDARD, 1–30 $\rightarrow$ SMA-0, 31–60 $\rightarrow$ SMA-1, 61–90 $\rightarrow$ SMA-2, >90 $\rightarrow$ NPA.
  - Full catch-up immediately restores STANDARD.
- **`RepaymentEngine`**:
  - Banking waterfall:
    1. Overdue penal interest (oldest first).
    2. Overdue/due installment interest (oldest first).
    3. Overdue/due installment principal (oldest first).
    4. Prepayment / advance principal reduction.
- **`PrepaymentEngine`**:
  - Validates $\ge 6$ EMIs paid, amount $\ge ₹25,000$.
  - Applies 2% fee within first 24 months.
  - Restructures schedule under `TENURE_REDUCTION` or `EMI_REDUCTION`.
- **`ForeclosureEngine`**:
  - Validates $\ge 12$ EMIs paid.
  - 4% fee if $\le 36$ months; 0% fee if $> 36$ months.
  - Calculates full payoff quote including penal interest.
- **`StatementEngine`**:
  - Point-in-time loan statement generation.
