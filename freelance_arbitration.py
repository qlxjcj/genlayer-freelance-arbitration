# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from dataclasses import dataclass
from genlayer import *


@allow_storage
@dataclass
class Contract:
    contract_id: str
    client: str
    freelancer: str
    description: str
    amount: u256
    status: str
    client_evidence: str
    freelancer_evidence: str
    outcome: str
    confidence: u256
    timestamp: str


class FreelanceArbitration(gl.Contract):
    contracts: TreeMap[str, str]
    contract_count: u256
    claimed: TreeMap[str, str]

    def __init__(self):
        pass

    def _adjudicate(self, description: str, client_evidence: str, freelancer_evidence: str) -> dict:
        def gather_and_adjudicate() -> str:
            def fetch(urls_json: str) -> list:
                texts = []
                for url in json.loads(urls_json):
                    try:
                        content = gl.get_webpage(url, mode="text")
                        texts.append(f"[{url}]\n{content[:2500]}")
                    except Exception:
                        texts.append(f"[{url}] [FETCH_FAILED]")
                return texts

            client_texts = fetch(client_evidence) if client_evidence else []
            freelancer_texts = fetch(freelancer_evidence) if freelancer_evidence else []

            task = f"""
You are a freelance arbitration judge. A client and freelancer dispute whether work was delivered satisfactorily. Review both sides and rule.

WORK DESCRIPTION:
{description}

CLIENT EVIDENCE:
{chr(10).join(client_texts) if client_texts else "[none submitted]"}

FREELANCER EVIDENCE:
{chr(10).join(freelancer_texts) if freelancer_texts else "[none submitted]"}

Respond ONLY in this JSON format with exact fields:
{{
    "outcome": "RELEASE_TO_FREELANCER" | "REFUND_TO_CLIENT" | "SPLIT",
    "freelancer_percentage": int,  // 0-100, share of funds to freelancer. 100=release, 0=refund, 1-99=split
    "confidence": int  // 0-100
}}
"""
            result = gl.exec_prompt(task).replace("```json", "").replace("```", "")
            return json.dumps(json.loads(result), sort_keys=True)

        principle = "Validators must agree on ALL THREE outputs: the exact outcome label (RELEASE_TO_FREELANCER/REFUND_TO_CLIENT/SPLIT), the exact freelancer_percentage (0-100), and the exact confidence (0-100)."
        result_json = json.loads(gl.eq_principle_prompt_comparative(gather_and_adjudicate, principle))
        return result_json

    @gl.public.write.payable
    def create_contract(self, freelancer: str, description: str):
        sender = gl.message.sender_address
        amount = gl.message.value
        if amount == u256(0):
            raise Exception("Send value to fund contract")

        self.contract_count += 1
        contract_id = str(self.contract_count)

        contract = Contract(
            contract_id=contract_id, client=sender.as_hex,
            freelancer=freelancer, description=description,
            amount=int(str(amount)), status="ACTIVE",
            client_evidence="[]", freelancer_evidence="[]",
            outcome="", confidence=0, timestamp=str(gl.message.timestamp),
        )
        self.contracts[contract_id] = json.dumps(contract.__dict__)
        self.claimed[contract_id] = "[]"

    @gl.public.write
    def submit_evidence(self, contract_id: str, evidence_urls_json: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise Exception("Contract not found")
        if contract["status"] not in ("ACTIVE", "DISPUTED"):
            raise Exception("Cannot submit evidence at this stage")

        if sender.as_hex == contract["client"]:
            contract["client_evidence"] = evidence_urls_json
        elif sender.as_hex == contract["freelancer"]:
            contract["freelancer_evidence"] = evidence_urls_json
        else:
            raise Exception("Only parties can submit evidence")

        self.contracts[contract_id] = json.dumps(contract)

    @gl.public.write
    def raise_dispute(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise Exception("Contract not found")
        if sender.as_hex not in (contract["client"], contract["freelancer"]):
            raise Exception("Only parties can raise dispute")
        if contract["status"] != "ACTIVE":
            raise Exception("Contract not active")

        contract["status"] = "DISPUTED"
        self.contracts[contract_id] = json.dumps(contract)

    @gl.public.write
    def adjudicate(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise Exception("Contract not found")
        if sender.as_hex not in (contract["client"], contract["freelancer"]):
            raise Exception("Only parties can request adjudication")
        if contract["status"] != "DISPUTED":
            raise Exception("Only disputed contracts can be adjudicated")

        contract["status"] = "ADJUDICATING"
        self.contracts[contract_id] = json.dumps(contract)

        result = self._adjudicate(
            contract["description"],
            contract["client_evidence"],
            contract["freelancer_evidence"],
        )

        outcome = result.get("outcome", "SPLIT")
        if outcome not in ("RELEASE_TO_FREELANCER", "REFUND_TO_CLIENT", "SPLIT"):
            outcome = "SPLIT"
        pct = int(result.get("freelancer_percentage", 50))
        pct = max(0, min(100, pct))
        conf = int(result.get("confidence", 0))
        conf = max(0, min(100, conf))

        if outcome == "RELEASE_TO_FREELANCER": pct = 100
        if outcome == "REFUND_TO_CLIENT": pct = 0

        contract["status"] = "RESOLVED"
        contract["outcome"] = outcome
        contract["confidence"] = conf
        contract["freelancer_percentage"] = pct
        self.contracts[contract_id] = json.dumps(contract)

    @gl.public.write
    def claim_funds(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise Exception("Contract not found")
        if contract["status"] != "RESOLVED":
            raise Exception("Contract not resolved")
        if sender.as_hex not in (contract["client"], contract["freelancer"]):
            raise Exception("Only parties can claim")

        claimed_list = json.loads(self.claimed.get(contract_id, "[]"))
        if sender.as_hex in claimed_list:
            raise Exception("Already claimed")
        claimed_list.append(sender.as_hex)
        self.claimed[contract_id] = json.dumps(claimed_list)

        total = contract["amount"]
        pct = contract["freelancer_percentage"]
        freelancer_share = total * pct // 100
        client_share = total - freelancer_share

        if sender.as_hex == contract["freelancer"]:
            payout = freelancer_share
        else:
            payout = client_share

        if payout > 0:
            self.send_value(sender, u256(payout))

    def send_value(self, recipient: Address, amount: u256):
        @gl.evm.contract_interface
        class _Recipient:
            class View:
                pass
            class Write:
                pass
        _Recipient(recipient).emit_transfer(value=amount)

    @gl.public.view
    def get_contract(self, contract_id: str) -> str:
        return self.contracts.get(contract_id, "{}")

    @gl.public.view
    def get_contract_count(self) -> int:
        return self.contract_count

    @gl.public.view
    def get_contract_balance(self) -> u256:
        return self.balance

    @gl.public.view
    def get_stats(self) -> dict:
        active = disputed = adjudicating = resolved = 0
        for v in self.contracts.values():
            c = json.loads(v)
            if c["status"] == "ACTIVE": active += 1
            elif c["status"] == "DISPUTED": disputed += 1
            elif c["status"] == "ADJUDICATING": adjudicating += 1
            elif c["status"] == "RESOLVED": resolved += 1
        return {"total": len(self.contracts), "active": active, "disputed": disputed, "adjudicating": adjudicating, "resolved": resolved}

    @gl.public.view
    def list_contracts(self) -> dict:
        result = {}
        for k, v in self.contracts.items():
            c = json.loads(v)
            result[k] = {
                "client": c["client"],
                "freelancer": c["freelancer"],
                "status": c["status"],
                "outcome": c["outcome"],
            }
        return result
