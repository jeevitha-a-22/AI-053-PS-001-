# Architecture Decision Log (ADR): AI-053-PS-001

## ADR-001: Separation of Member 1 and Member 2 Modules
- **Context**: The project requires clear separation between two developers so both can work independently on origination and servicing.
- **Decision**:
  - Member 1 owns origination models, eligibility (BR-01, BR-02, BR-03, BR-04), rate engine (BR-05), fee engine (BR-06), EMI/amortisation (BR-07), and approval engine (BR-12).
  - Member 2 owns repayment servicing, late payment/penal interest (BR-08), prepayment (BR-09), foreclosure (BR-10), DPD/classification (BR-11), and statement engine.
  - The shared interface is mediated by dataclasses in `src/models/` (`Loan`, `Installment`, `Repayment`).
- **Consequences**: Enables parallel development without merge conflicts or overlapping concerns.

---

## ADR-002: Use of Python `Decimal` for Financial Calculations
- **Context**: Floats lead to binary rounding inaccuracies in financial applications.
- **Decision**: All financial figures (principal, interest, fees, installments) use Python's `Decimal` type with `ROUND_HALF_UP` rounding.
- **Consequences**: Exact rupee and paise accounting with zero floating-point drift.

---

## ADR-003: Month Addition and End-of-Month Clamping
- **Context**: Monthly installment due dates must handle varying month lengths (e.g., 28, 29, 30, 31 days) and leap years.
- **Decision**: Implemented `add_months` using the standard library `calendar.monthrange`. If the start day exceeds the maximum days in the target month (e.g. Jan 31 + 1 month), the date clamps to the final day of the target month (Feb 28 in non-leap year, Feb 29 in leap year).
- **Consequences**: Clean, predictable calendar arithmetic without external third-party dependencies.

---

## ADR-004: Inversion of Reducing-Balance EMI for BR-12 Conditional Approval
- **Context**: BR-12 requires granting conditional approval with the largest affordable loan amount if FOIR or amount cap fails.
- **Decision**: The reducing-balance equation is inverted algebraically:
  $$P_{\max} = \frac{\text{Available EMI} \times ((1+r)^n - 1)}{r \times (1+r)^n}$$
  The sanctioned amount is set to the minimum of requested amount, $P_{\max}$, and the profile amount cap, rounded down to the nearest ₹1,000.
- **Consequences**: Deterministic, optimal conditional offers generated in $O(1)$ time without trial-and-error searching.

---

## ADR-005: Daily Penal Interest Calculation (BR-08)
- **Context**: BR-08 specifies a 5-day grace period, after which penal interest is 2% per month on overdue EMI calculated daily.
- **Decision**:
  - If payment is made on or before `due_date + 5 days`, penal interest is zero.
  - If overdue past 5 days, daily penal rate is $(0.02 / 30)$. Penal interest accrues for the overdue period:
    $$\text{Penal Interest} = \text{Overdue EMI} \times \left(\frac{0.02}{30}\right) \times \text{Days Overdue}$$
- **Consequences**: Matches banking practice where grace period offers cure time; failure to cure within grace triggers standard daily penalty.

---

## ADR-006: Prepayment Restructuring Choices (BR-09)
- **Context**: Part prepayments reduce outstanding principal, and the borrower may choose tenure reduction or EMI reduction.
- **Decision**:
  - `TENURE_REDUCTION`: Monthly EMI remains constant, remaining schedule is regenerated with reduced principal, shortening tenure.
  - `EMI_REDUCTION`: Remaining tenure remains constant, lower EMI is calculated with reducing-balance formula.
- **Consequences**: Both restructuring options adhere strictly to reducing-balance interest math.

---

## ADR-007: Foreclosure Settlement Waterfall (BR-10)
- **Context**: Foreclosure requires full early settlement, which may include accrued penal charges.
- **Decision**:
  - Total quote $= \text{Outstanding Principal} + \text{Foreclosure Fee} + \text{Pending Interest} + \text{Pending Penal Interest}$.
  - Foreclosure fee is 4% within 36 months, 0% thereafter.
  - Foreclosure execution marks all scheduled installments paid and sets `loan.is_closed = True` and `classification = STANDARD`.
- **Consequences**: Fully resolves edge case "foreclosure with pending penal interest".

---

## ADR-008: DPD and Asset Quality Classification (BR-11)
- **Context**: RBI prudential norms require daily classification based on Days Past Due (DPD).
- **Decision**:
  - DPD is computed dynamically as of any requested date against the oldest unpaid installment.
  - DPD 0 $\rightarrow$ STANDARD, 1–30 $\rightarrow$ SMA-0, 31–60 $\rightarrow$ SMA-1, 61–90 $\rightarrow$ SMA-2, >90 $\rightarrow$ NPA.
  - A full catch-up payment clears overdue amounts and immediately resets DPD to 0 and classification to STANDARD.
- **Consequences**: Regulatory compliance and accurate point-in-time portfolio reporting.

---

## ADR-009: Decoupled Command-File Architecture (NO GUI)
- **Context**: The engine must be command-file-driven with NO GUI.
- **Decision**: Built a command interpreter (`CommandEngineSession`) that parses directives from text files or CSV streams. `main.py` is a light CLI runner with no business logic.
- **Consequences**: High testability, scriptability for automated evaluation, and complete compliance with requirements.
