# Freelance Arbitration — GenLayer

On-chain escrow for freelancer payments with AI dispute resolution, plus
direct acceptance / cancellation / timeout recovery so funds never lock.

## Lifecycle

```
create_contract(freelancer, description, deadline)   # payable — client funds escrow
accept_work(contract_id)      # client accepts → release 100% to freelancer (no AI)
cancel_contract(contract_id)  # either party cancels (ACTIVE) → refund 100% to client
recover_funds(contract_id)    # either party recovers (ACTIVE/DISPUTED, past deadline) → refund client
raise_dispute(contract_id)    # ACTIVE → DISPUTED
submit_evidence(...)          # parties submit evidence URLs
adjudicate(contract_id)       # AI consensus → RELEASE / REFUND / SPLIT
claim_funds(contract_id)      # distribute escrow per consensus split
```

Successful work is settled directly via `accept_work`; only genuine disputes go
through AI adjudication. Cancellation and timeout recovery give both parties an
escape hatch so escrow never locks. Funds move via `gl.get_contract_at(...).emit_transfer`
(native PostMessage transfer), with `msg.sender`-derived party authorization on every action.

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/direct/ -v
```

Direct-mode tests (in-memory VM, no consensus) cover the funded write and every
payout path with balance-ledger assertions: create escrow, accept → freelancer,
cancel → client, recover (past/future deadline), and dispute → adjudicate → claim split.

## Live

- Contract: `0xc3FA52455849A8ffC2aA681A4B1435b15B3ec8cD`
- Explorer: https://explorer-bradbury.genlayer.com/address/0xc3FA52455849A8ffC2aA681A4B1435b15B3ec8cD
- Frontend: https://qlxjcj.github.io/genlayer-freelance-arbitration/
