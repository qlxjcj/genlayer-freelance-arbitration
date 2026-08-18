"""Direct-mode tests for Freelance Arbitration.

Covers the escrow lifecycle the steward flagged: direct acceptance
(accept_work), cancellation (cancel_contract), timeout recovery
(recover_funds), plus the AI dispute path — with real balance-ledger
assertions on the funded write (create_contract) and every payout path.

No network, no consensus: deterministic and instant.
Run: python -m pytest tests/direct/ -v   (from the project root)
"""

import json
import pytest

from conftest import G, ADJUDICATE_SPLIT, ADJUDICATE_REFUND, LLM_PATTERN


def _balance(vm, addr):
    return vm._balances.get(vm._to_bytes(addr), 0)


def c_json(c, cid):
    return json.loads(c.get_contract(str(cid)))


def _create(vm, c, client, freelancer, amount, deadline="0"):
    vm.sender = client
    vm.value = amount
    vm.deal(client, amount)
    c.create_contract(freelancer.as_hex, "Build a website", deadline)
    vm.value = 0


# ---------- funded write ----------

def test_create_funds_escrow(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    amount = 10 * G
    _create(vm, c, client, direct_bob, amount)

    assert c.get_contract_count() == 1
    assert c_json(c, 1)["status"] == "ACTIVE"
    assert int(c.get_contract_balance()) == amount
    assert _balance(vm, client) == 0  # client debited


# ---------- direct acceptance ----------

def test_accept_work_releases_to_freelancer(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    amount = 10 * G
    _create(vm, c, client, direct_bob, amount)

    vm.sender = client
    c.accept_work("1")

    assert c_json(c, 1)["status"] == "COMPLETED"
    assert _balance(vm, direct_bob) == amount  # freelancer paid in full
    assert int(c.get_contract_balance()) == 0


def test_accept_work_only_client(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    _create(vm, c, client, direct_bob, 10 * G)

    vm.sender = direct_bob
    with pytest.raises(Exception) as ei:
        c.accept_work("1")
    assert "client" in str(ei.value).lower()


# ---------- cancellation ----------

def test_cancel_refunds_client(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    amount = 10 * G
    _create(vm, c, client, direct_bob, amount)

    c.cancel_contract("1")  # client cancels

    assert c_json(c, 1)["status"] == "CANCELLED"
    assert _balance(vm, client) == amount  # client refunded
    assert int(c.get_contract_balance()) == 0


def test_cancel_by_freelancer_refunds_client(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    amount = 10 * G
    _create(vm, c, client, direct_bob, amount)

    vm.sender = direct_bob
    c.cancel_contract("1")  # freelancer gives up -> client refunded

    assert c_json(c, 1)["status"] == "CANCELLED"
    assert _balance(vm, client) == amount


def test_cancel_non_party_rejected(direct_vm, escrow, direct_bob, direct_charlie):
    vm, c = escrow
    client = vm.sender
    _create(vm, c, client, direct_bob, 10 * G)

    vm.sender = direct_charlie
    with pytest.raises(Exception) as ei:
        c.cancel_contract("1")
    assert "parties" in str(ei.value).lower()


# ---------- timeout recovery ----------

def test_recover_past_deadline_refunds_client(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    amount = 10 * G
    _create(vm, c, client, direct_bob, amount, deadline="1")  # already past

    vm.sender = direct_bob
    c.recover_funds("1")

    assert c_json(c, 1)["status"] == "CANCELLED"
    assert _balance(vm, client) == amount


def test_recover_future_deadline_blocked(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    _create(vm, c, client, direct_bob, 10 * G, deadline="99999999999")  # far future

    vm.sender = direct_bob
    with pytest.raises(Exception) as ei:
        c.recover_funds("1")
    assert "deadline" in str(ei.value).lower()


# ---------- AI dispute path (unchanged) ----------

def test_dispute_adjudicate_split_and_claim(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    amount = 100 * G
    _create(vm, c, client, direct_bob, amount)

    c.submit_evidence("1", '["https://client.evidence"]')
    vm.sender = direct_bob
    c.submit_evidence("1", '["https://freelancer.evidence"]')
    c.raise_dispute("1")

    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, ADJUDICATE_SPLIT)
    c.adjudicate("1")

    assert c_json(c, 1)["status"] == "RESOLVED"
    assert c_json(c, 1)["freelancer_percentage"] == 60

    vm.sender = direct_bob
    c.claim_funds("1")  # freelancer gets 60
    assert _balance(vm, direct_bob) == 60 * G

    vm.sender = client
    c.claim_funds("1")  # client gets 40
    assert _balance(vm, client) == 40 * G
    assert int(c.get_contract_balance()) == 0


def test_dispute_adjudicate_full_refund(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    amount = 50 * G
    _create(vm, c, client, direct_bob, amount)

    c.raise_dispute("1")
    vm.clear_mocks()
    vm.mock_llm(LLM_PATTERN, ADJUDICATE_REFUND)
    c.adjudicate("1")

    vm.sender = client
    c.claim_funds("1")
    assert _balance(vm, client) == amount


# ---------- state guards ----------

def test_accept_then_cancel_blocked(direct_vm, escrow, direct_bob):
    vm, c = escrow
    client = vm.sender
    _create(vm, c, client, direct_bob, 10 * G)

    c.accept_work("1")
    with pytest.raises(Exception) as ei:
        c.cancel_contract("1")
    assert "not active" in str(ei.value).lower()
