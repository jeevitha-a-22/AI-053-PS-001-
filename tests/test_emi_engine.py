"""
Tests for EMI Engine and Amortisation Schedule (Member 1).
Covers BR-06 and BR-07.
"""
from datetime import date
from decimal import Decimal
import pytest
from src.services.emi_engine import EMIEngine


def test_br06_processing_fee_bounds():
    # 1.5% of 50,000 = 750 -> Min cap is 999
    fee, net = EMIEngine.calculate_processing_fee(Decimal('50000'))
    assert fee == Decimal('999')
    assert net == Decimal('50000') - Decimal('999')

    # 1.5% of 5,00,000 = 7,500 -> Within 999 and 9,999
    fee_mid, net_mid = EMIEngine.calculate_processing_fee(Decimal('500000'))
    assert fee_mid == Decimal('7500')
    assert net_mid == Decimal('500000') - Decimal('7500')

    # 1.5% of 10,00,000 = 15,000 -> Max cap is 9,999
    fee_high, net_high = EMIEngine.calculate_processing_fee(Decimal('1000000'))
    assert fee_high == Decimal('9999')
    assert net_high == Decimal('1000000') - Decimal('9999')


def test_br07_emi_reducing_balance_formula():
    # Loan ₹1,00,000, 12% p.a., 12 months
    # Formula check: monthly rate = 1%
    # EMI = 100000 * 0.01 * (1.01)^12 / ((1.01)^12 - 1) = 8884.8788... -> 8885
    emi = EMIEngine.calculate_emi(Decimal('100000'), Decimal('0.12'), 12)
    assert emi == Decimal('8885')


def test_br07_amortisation_schedule_and_last_emi_absorption():
    principal = Decimal('100000')
    annual_rate = Decimal('0.12')
    tenure = 12
    disbursal = date(2025, 1, 1)

    schedule = EMIEngine.generate_amortisation_schedule(principal, annual_rate, tenure, disbursal)
    assert len(schedule) == tenure

    # Verify every installment's principal + interest matches its beginning principal reduction
    total_principal_paid = Decimal('0.00')
    for inst in schedule[:-1]:
        assert inst.ending_principal == inst.beginning_principal - inst.principal_component
        total_principal_paid += inst.principal_component

    # Verify last installment absorbs rounding difference
    last_inst = schedule[-1]
    assert last_inst.ending_principal == Decimal('0.00')
    assert last_inst.principal_component == last_inst.beginning_principal

    # Sum of all principal components must exactly equal sanctioned principal
    sum_principal = sum(i.principal_component for i in schedule)
    assert sum_principal == principal
