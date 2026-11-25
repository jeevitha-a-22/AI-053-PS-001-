"""
Tests for Parsers and Command File Engine.
"""
from datetime import date
from decimal import Decimal
import os
import pytest
from src.parsers.applicant_parser import parse_applicant_csv
from src.parsers.application_parser import parse_application_csv
from src.parsers.repayment_parser import parse_repayment_csv
from src.parsers.command_parser import CommandEngineSession


def test_parse_sample_applicants():
    file_path = os.path.join("data", "sample_applicants.csv")
    applicants = parse_applicant_csv(file_path)
    assert len(applicants) == 8
    app1 = applicants[0]
    assert app1.applicant_id == "APP001"
    assert app1.credit_score == 780
    assert app1.monthly_income == Decimal('100000')

    # Verify missing credit score parsed as None
    app7 = applicants[6]
    assert app7.credit_score is None


def test_parse_sample_applications():
    file_path = os.path.join("data", "sample_applications.csv")
    applications = parse_application_csv(file_path)
    assert len(applications) == 8
    app1 = applications[0]
    assert app1.application_id == "LNAPP001"
    assert app1.amount == Decimal('500000')
    assert app1.tenure_months == 36


def test_parse_sample_repayments():
    file_path = os.path.join("data", "sample_repayments.csv")
    repayments = parse_repayment_csv(file_path)
    assert len(repayments) == 7
    rep1 = repayments[0]
    assert rep1.repayment_id == "REP001"
    assert rep1.amount == Decimal('16252')


def test_command_file_execution():
    file_path = os.path.join("data", "sample_commands.txt")
    session = CommandEngineSession()
    session.execute_file(file_path)

    # Check session state
    assert "APP101" in session.applicants
    assert "APP_LN101" in session.applications
    assert "LN_101" in session.loans
    loan = session.loans["LN_101"]
    assert loan.emis_paid_count >= 6
    assert len(loan.repayments) == 7


def test_batch_statement_generation_past_current_future_dates(tmp_path):
    """
    Regression test for batch mode statement generation across:
    1. A past as-of date where no installments exist (e.g. 2024-01-01)
    2. A normal/current as-of date (e.g. 2025-09-15)
    3. A future as-of date (e.g. 2032-01-01)
    """
    from src.main import run_batch_pipeline

    applicants_file = os.path.join("data", "sample_applicants.csv")
    applications_file = os.path.join("data", "sample_applications.csv")
    repayments_file = os.path.join("data", "sample_repayments.csv")

    # 1. Past as-of date where no installments exist yet for loans disbursed in 2025/2026
    output_past = str(tmp_path / "statements_past.json")
    run_batch_pipeline(
        applicants_path=applicants_file,
        applications_path=applications_file,
        repayments_path=repayments_file,
        as_of_date_str="2024-01-01",
        output_json_path=output_past,
    )
    assert os.path.exists(output_past)

    # 2. Normal / current as-of date (2025-09-15, where some loans are active, some future)
    output_current = str(tmp_path / "statements_current.json")
    run_batch_pipeline(
        applicants_path=applicants_file,
        applications_path=applications_file,
        repayments_path=repayments_file,
        as_of_date_str="2025-09-15",
        output_json_path=output_current,
    )
    assert os.path.exists(output_current)

    # 3. Future as-of date (2032-01-01, where all loans have matured)
    output_future = str(tmp_path / "statements_future.json")
    run_batch_pipeline(
        applicants_path=applicants_file,
        applications_path=applications_file,
        repayments_path=repayments_file,
        as_of_date_str="2032-01-01",
        output_json_path=output_future,
    )
    assert os.path.exists(output_future)
