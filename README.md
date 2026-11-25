# AI-053-PS-001: Loan Origination and EMI Engine

A high-precision, command-file-driven backend engine for bank personal loan origination, reducing-balance EMI amortisation, repayment servicing, part-prepayment, foreclosure, and regulatory asset classification (NO GUI).

---

## 1. Project Overview

The `AI-053-PS-001` backend engine executes the entire lifecycle of a personal loan:
1. **Applicant Registration & Eligibility Screening**: Validates age, employment type, city tier, income, FOIR, and credit score.
2. **Underwriting & Decisioning**: Supports `APPROVE`, `APPROVE_WITH_CONDITIONS` (BR-12), and `REJECT` with exact rule ID attribution.
3. **EMI & Amortisation Engine**: Standard reducing-balance formula, nearest-rupee rounding, with the final installment absorbing rounding differences.
4. **Loan Servicing & Repayments**: Handles on-time, grace-period (5 days), late payments with daily penal interest, part-prepayments (tenure/EMI reduction), and full foreclosures.
5. **Regulatory Asset Quality Classification**: Real-time Days Past Due (DPD) computation categorizing accounts into `STANDARD`, `SMA-0`, `SMA-1`, `SMA-2`, and `NPA`, with instant restoration upon catch-up payment.
6. **Loan Account Statements**: Point-in-time financial and ledger statements generated for any requested date.

---

## 2. Team Architecture & Ownership

The system is strictly partitioned into **Member 1** and **Member 2** domains with decoupled service boundaries communicating via standard data models:

```
+-----------------------------------------------------------------------------------+
|                                  SHARED MODELS                                    |
|   Applicant | LoanApplication | LoanDecision | Installment | Repayment | Loan     |
+-----------------------------------------+-----------------------------------------+
                                          |
        +---------------------------------+---------------------------------+
        |                                                                   |
        v                                                                   v
+-------------------------------+                         +---------------------------------+
|      MEMBER 1 DOMAIN          |                         |       MEMBER 2 DOMAIN           |
| (Origination & Amortisation)  |                         |  (Servicing & Classification)   |
+-------------------------------+                         +---------------------------------+
| • Applicant & Application     |                         | • Repayment Engine              |
| • Eligibility Engine (BR-01)  |                         | • Late Payment & Penal (BR-08)  |
| • Credit Score Check (BR-03)  |  Passed Loan & Schedule | • Prepayment Engine (BR-09)     |
| • Amount Cap Engine (BR-04)   | ----------------------> | • Foreclosure Engine (BR-10)    |
| • FOIR Engine (BR-02)         |                         | • DPD & Classification (BR-11)  |
| • Rate Engine (BR-05)         |                         | • Loan Statement Engine         |
| • Processing Fee (BR-06)      |                         +---------------------------------+
| • Approval Engine (BR-12)     |
| • EMI Engine (BR-07)          |
+-------------------------------+
```

### Member 1 Ownership:
- **Models**: `Applicant`, `LoanApplication`, `LoanDecision`
- **Engines**: `eligibility_engine`, `rate_engine`, `emi_engine`, `approval_engine`
- **Rules**: BR-01 (Age & Maturity), BR-02 (FOIR), BR-03 (Credit Score), BR-04 (Amount Multiplier & ₹25L cap), BR-05 (Cumulative Interest Rates), BR-06 (Processing Fee ₹999–₹9,999), BR-07 (Reducing-balance EMI & Amortisation), BR-12 (Conditional Approval).

### Member 2 Ownership:
- **Models**: `Repayment`, `Installment` (tracking properties), `Loan` (lifecycle & ledger)
- **Engines**: `repayment_engine`, `prepayment_engine`, `foreclosure_engine`, `classification_engine`, `statement_engine`
- **Rules**: BR-08 (5-day grace period & 2%/month daily penal interest), BR-09 (Part Prepayment after 6 EMIs, min ₹25k, 2% fee in first 24m), BR-10 (Foreclosure after 12 EMIs, 4% fee, 0% after 36m), BR-11 (DPD & SMA/NPA classification), Capability 7 (Point-in-time Statements).

---

## 3. Directory Layout

```
AI-053-PS-001/
├── src/
│   ├── main.py                     # CLI & command-file runner (NO GUI)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── enums.py                # EmploymentType, CityTier, DecisionStatus, etc.
│   │   ├── applicant.py            # Applicant profile model
│   │   ├── loan_application.py     # Application & LoanDecision models
│   │   ├── installment.py          # Scheduled payment & ledger tracking model
│   │   ├── repayment.py            # Repayment transaction model
│   │   └── loan.py                 # Loan aggregate root model
│   ├── services/
│   │   ├── __init__.py
│   │   ├── eligibility_engine.py   # Member 1: BR-01, BR-02, BR-03, BR-04
│   │   ├── rate_engine.py          # Member 1: BR-05
│   │   ├── emi_engine.py           # Member 1: BR-06, BR-07
│   │   ├── approval_engine.py      # Member 1: BR-12 orchestration
│   │   ├── classification_engine.py# Member 2: BR-08, BR-11
│   │   ├── prepayment_engine.py    # Member 2: BR-09
│   │   ├── foreclosure_engine.py   # Member 2: BR-10
│   │   ├── repayment_engine.py     # Member 2: Waterfall allocations
│   │   └── statement_engine.py     # Member 2: Statement generation
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── applicant_parser.py     # CSV parsing for applicants
│   │   ├── application_parser.py   # CSV parsing for loan applications
│   │   ├── repayment_parser.py     # CSV parsing for repayments
│   │   └── command_parser.py       # Command-file script execution
│   └── utils/
│       ├── __init__.py
│       ├── currency.py             # Decimal rounding & rupee quantizing
│       └── date_utils.py           # Calendar month math & leap-year handling
├── tests/
│   ├── test_eligibility_engine.py
│   ├── test_rate_engine.py
│   ├── test_emi_engine.py
│   ├── test_approval_engine.py
│   ├── test_repayment_engine.py
│   ├── test_prepayment_engine.py
│   ├── test_foreclosure_engine.py
│   ├── test_classification_engine.py
│   ├── test_parsers_and_cli.py
│   └── test_edge_cases.py         # 8 explicit edge cases tested
├── data/
│   ├── sample_applicants.csv
│   ├── sample_applications.csv
│   ├── sample_repayments.csv
│   └── sample_commands.txt
├── requirements.txt
├── .gitignore
├── README.md
├── DESIGN.md
└── DECISION_LOG.md
```

---

## 4. Setup and Installation

### Prerequisites
- Python 3.10+ (Tested on Python 3.14)
- Standard library utilized throughout core logic.

### Install Dependencies
```bash
python -m pip install -r requirements.txt
```

---

## 5. Running Tests

Run all unit tests with verbose output:
```bash
python -m pytest -v
```

Run specific test suites:
```bash
# Member 1 Eligibility & Approval tests
python -m pytest tests/test_eligibility_engine.py tests/test_approval_engine.py -v

# Member 2 Repayment & Classification tests
python -m pytest tests/test_repayment_engine.py tests/test_classification_engine.py -v

# Edge cases suite (all 8 required edge cases)
python -m pytest tests/test_edge_cases.py -v
```

---

## 6. How to Run the Backend Engine

The system is strictly command-driven with NO GUI. It provides two primary execution modes:

### Mode 1: Command-File Execution
Run directives line-by-line from a script file:
```bash
python src/main.py run-commands data/sample_commands.txt
```

Example command script syntax:
```text
REGISTER_APPLICANT APP101,Karan Mehra,1992-04-10,120000,15000,SALARIED,770,TIER_1
APPLY_LOAN APP_LN101,APP101,600000,36,Home Renovation,2025-01-01
EVALUATE_APPLICATION APP_LN101,LN_101
RECORD_REPAYMENT REP101,LN_101,2025-02-01,19502,EMI
CLASSIFY_LOAN LN_101,2025-09-15
GENERATE_STATEMENT LN_101,2025-09-15
```

### Mode 2: Batch CSV Processing
Process applicant registrations, applications, and repayment ledgers in batch:
```bash
python src/main.py batch \
  --applicants data/sample_applicants.csv \
  --applications data/sample_applications.csv \
  --repayments data/sample_repayments.csv \
  --as-of-date 2025-09-15
```

Save statements to JSON:
```bash
python src/main.py batch \
  --applicants data/sample_applicants.csv \
  --applications data/sample_applications.csv \
  --repayments data/sample_repayments.csv \
  --as-of-date 2025-09-15 \
  --output-json statements.json
```

---

## 7. Business Rules Implemented

| Rule ID | Name | Description |
|---|---|---|
| **BR-01** | Age & Maturity | Age 21–60 at application. Loan maturity date must end strictly before 65th birthday. |
| **BR-02** | FOIR Limit | FOIR = (Existing EMIs + Proposed EMI) / Monthly Income. Salaried max 50%, Self-Employed max 40%. |
| **BR-03** | Credit Score | Below 650: REJECT. 650–749: Approve with +2% rate. 750+: Base rate. Missing: REJECT. |
| **BR-04** | Amount Cap | Salaried: 20x income. Self-employed: 15x income. Absolute cap: ₹25,00,000. |
| **BR-05** | Rate Engine | Salaried base 11%, Self-Employed base 13%. Cumulative adjustments: Tier-1 city (-0.5%), tenure > 48m (+0.5%), credit 650–749 (+2.0%). |
| **BR-06** | Processing Fee | 1.5% of sanctioned amount (Min ₹999, Max ₹9,999), deducted from disbursal. |
| **BR-07** | EMI & Amortisation | Reducing-balance formula. EMI rounded to nearest whole rupee. Final installment absorbs rounding difference. |
| **BR-08** | Grace & Penal Interest | 5-day grace period. After grace, 2% per month penal interest on overdue EMI calculated daily (2%/30). |
| **BR-09** | Part Prepayment | Allowed after 6 EMIs. Min ₹25,000. 2% fee within first 24 months. Choice of Tenure or EMI reduction. |
| **BR-10** | Foreclosure | Allowed after 12 EMIs. 4% fee of outstanding principal. 0% fee after 36 months. Clears penal interest first. |
| **BR-11** | Asset Classification | DPD 1–30: SMA-0; 31–60: SMA-1; 61–90: SMA-2; >90: NPA. Full catch-up payment restores STANDARD. |
| **BR-12** | Conditional Approval | If only FOIR or amount cap fails, grant conditional approval with largest affordable amount and longest permissible tenure. |

---

## 8. Explicit Edge Cases Handled

1. **Applicant exactly age 60**: Evaluates completed years on application date. Age 60 is permitted.
2. **Tenure crossing 65th birthday mid-month**: Maturity date computed via month addition; if maturity date >= 65th birthday, rule BR-01 rejects or restricts tenure.
3. **Zero income**: Rejects gracefully with BR-02/BR-04 without division-by-zero crashes.
4. **Missing credit score**: Rejects under BR-03 with clear diagnostic message.
5. **Prepayment on EMI due date**: Automatically settles scheduled regular installment dues before directing prepayment funds to principal restructuring.
6. **Two repayments on the same day**: Sequential ledger execution correctly allocating dues and updating DPD and status.
7. **Foreclosure with pending penal interest**: Total settlement quote includes accrued penal interest, outstanding principal, regular interest, and foreclosure fee; payment settles all obligations simultaneously.
8. **Leap-year February**: Month-end date arithmetic correctly handles February 28/29 transitions without date overflow errors.
