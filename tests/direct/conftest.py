"""Shared fixtures for Freelance Arbitration direct-mode tests.

Direct mode runs the real contract source in-process and does NOT track native
value flows, so this conftest installs two accounting hooks:

1. Payable value: ``create_contract`` is wrapped so the sent value moves
   sender -> contract in the VM balance ledger.
2. EthSend transfers: the contract's ``emit_transfer`` produces an ``EthSend``
   gl_call (contract -> recipient). We intercept it and move contract ->
   recipient, so release / refund / payout assertions are real.
"""

import json
import os
import pytest

G = 10**18

CONTRACT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "freelance_arbitration.py",
)

ADJUDICATE_RELEASE = json.dumps({
    "outcome": "RELEASE_TO_FREELANCER", "freelancer_percentage": 100, "confidence": 90,
})
ADJUDICATE_REFUND = json.dumps({
    "outcome": "REFUND_TO_CLIENT", "freelancer_percentage": 0, "confidence": 90,
})
ADJUDICATE_SPLIT = json.dumps({
    "outcome": "SPLIT", "freelancer_percentage": 60, "confidence": 85,
})

LLM_PATTERN = r".*freelance arbitration judge.*"


def _addr_bytes(vm, addr):
    return vm._to_bytes(addr)


def _balance(vm, addr):
    return vm._balances.get(_addr_bytes(vm, addr), 0)


@pytest.fixture
def escrow(direct_vm, direct_deploy):
    vm = direct_vm
    vm.mock_llm(LLM_PATTERN, ADJUDICATE_RELEASE)

    def _value_transfer_hook(vm, request):
        if "PostMessage" not in request:
            return None
        msg = request["PostMessage"]
        amount = int(msg.get("value", 0))
        if amount > 0:
            contract = vm._contract_address
            recipient = _addr_bytes(vm, msg["address"])
            vm._balances[contract] = _balance(vm, contract) - amount
            vm._balances[recipient] = _balance(vm, recipient) + amount
        return {"ok": None}

    vm._gl_call_hook = _value_transfer_hook
    c = direct_deploy(CONTRACT)

    _orig_create = c.create_contract
    def _create(freelancer, description, deadline):
        if vm.value > 0:
            sender = _addr_bytes(vm, vm.sender)
            contract = vm._contract_address
            vm._balances[sender] = _balance(vm, sender) - vm.value
            vm._balances[contract] = _balance(vm, contract) + vm.value
        return _orig_create(freelancer, description, deadline)
    c.create_contract = _create

    return vm, c
