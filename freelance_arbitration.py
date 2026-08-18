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
    freelancer_percentage: u256
    deadline: str


class FreelanceArbitration(gl.Contract):
    contracts: TreeMap[str, str]
    contract_count: u256
    claimed: TreeMap[str, str]

    def __init__(self):
        pass

    def _addr_hex(self, a) -> str:
        if hasattr(a, "as_hex"):
            return a.as_hex
        return str(a)

    def _norm_addr(self, a: str) -> str:
        try:
            return Address(a).as_hex
        except Exception:
            return str(a)

    def _decode_body(self, content) -> str:
        body = getattr(content, "body", None)
        if body is None:
            return str(content)
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        return str(body)

    def _now_unix(self) -> int:
        try:
            dt = str(gl.message_raw.get("datetime", ""))
        except Exception:
            dt = ""
        if not dt:
            return 0
        try:
            from datetime import datetime as _dt
            return int(_dt.fromisoformat(dt.replace("Z", "+00:00")).timestamp())
        except Exception:
            return 0

    def _adjudicate(self, description: str, client_evidence: str, freelancer_evidence: str) -> dict:
        def gather_and_adjudicate() -> dict:
            def fetch(urls_json: str) -> list:
                texts = []
                try:
                    urls = json.loads(urls_json)
                except Exception:
                    urls = []
                for url in urls:
                    try:
                        content = gl.nondet.web.get(url)
                        texts.append(f"[{url}]\n{self._decode_body(content)[:2000]}")
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
    "freelancer_percentage": int,
    "confidence": int
}}
"""
            result = gl.nondet.exec_prompt(task, response_format="json")
            if isinstance(result, str):
                result = json.loads(result.replace("```json", "").replace("```", ""))
            if not isinstance(result, dict):
                raise gl.vm.UserError("[LLM_ERROR] LLM returned non-dict result")
            return result

        principle = "Validators must agree on ALL THREE outputs: outcome (RELEASE_TO_FREELANCER/REFUND_TO_CLIENT/SPLIT), freelancer_percentage (0-100), and confidence (0-100)."
        return gl.eq_principle.prompt_comparative(gather_and_adjudicate, principle)

    @gl.public.write.payable
    def create_contract(self, freelancer: str, description: str, deadline: str):
        sender = gl.message.sender_address
        amount = gl.message.value
        if amount == u256(0):
            raise gl.vm.UserError("Send value to fund contract")

        self.contract_count += 1
        contract_id = str(self.contract_count)

        contract = Contract(
            contract_id=contract_id,
            client=self._addr_hex(sender),
            freelancer=self._norm_addr(freelancer),
            description=description,
            amount=int(str(amount)),
            status="ACTIVE",
            client_evidence="[]",
            freelancer_evidence="[]",
            outcome="",
            confidence=0,
            freelancer_percentage=0,
            deadline=deadline.strip() or "0",
        )
        self.contracts[contract_id] = json.dumps(contract.__dict__)
        self.claimed[contract_id] = "[]"

    @gl.public.write
    def accept_work(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise gl.vm.UserError("Contract not found")
        if self._addr_hex(sender) != contract["client"]:
            raise gl.vm.UserError("Only client can accept work")
        if contract["status"] != "ACTIVE":
            raise gl.vm.UserError("Contract not active")

        contract["status"] = "COMPLETED"
        contract["outcome"] = "RELEASE_TO_FREELANCER"
        contract["freelancer_percentage"] = 100
        self.contracts[contract_id] = json.dumps(contract)

        amount = int(contract["amount"])
        if amount > 0:
            self.send_value(Address(contract["freelancer"]), u256(amount))

    @gl.public.write
    def cancel_contract(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise gl.vm.UserError("Contract not found")
        if self._addr_hex(sender) not in (contract["client"], contract["freelancer"]):
            raise gl.vm.UserError("Only parties can cancel")
        if contract["status"] != "ACTIVE":
            raise gl.vm.UserError("Contract not active")

        contract["status"] = "CANCELLED"
        contract["outcome"] = "REFUND_TO_CLIENT"
        contract["freelancer_percentage"] = 0
        self.contracts[contract_id] = json.dumps(contract)

        amount = int(contract["amount"])
        if amount > 0:
            self.send_value(Address(contract["client"]), u256(amount))

    @gl.public.write
    def recover_funds(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise gl.vm.UserError("Contract not found")
        if self._addr_hex(sender) not in (contract["client"], contract["freelancer"]):
            raise gl.vm.UserError("Only parties can recover")
        if contract["status"] not in ("ACTIVE", "DISPUTED"):
            raise gl.vm.UserError("Nothing to recover")

        now = self._now_unix()
        deadline = int(contract.get("deadline", "0") or "0")
        if now != 0 and deadline > 0 and now < deadline:
            raise gl.vm.UserError("Deadline not passed")

        contract["status"] = "CANCELLED"
        contract["outcome"] = "REFUND_TO_CLIENT"
        contract["freelancer_percentage"] = 0
        self.contracts[contract_id] = json.dumps(contract)

        amount = int(contract["amount"])
        if amount > 0:
            self.send_value(Address(contract["client"]), u256(amount))

    @gl.public.write
    def submit_evidence(self, contract_id: str, evidence_urls_json: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise gl.vm.UserError("Contract not found")
        if contract["status"] not in ("ACTIVE", "DISPUTED"):
            raise gl.vm.UserError("Cannot submit evidence at this stage")

        if self._addr_hex(sender) == contract["client"]:
            contract["client_evidence"] = evidence_urls_json
        elif self._addr_hex(sender) == contract["freelancer"]:
            contract["freelancer_evidence"] = evidence_urls_json
        else:
            raise gl.vm.UserError("Only parties can submit evidence")

        self.contracts[contract_id] = json.dumps(contract)

    @gl.public.write
    def raise_dispute(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise gl.vm.UserError("Contract not found")
        if self._addr_hex(sender) not in (contract["client"], contract["freelancer"]):
            raise gl.vm.UserError("Only parties can raise dispute")
        if contract["status"] != "ACTIVE":
            raise gl.vm.UserError("Contract not active")

        contract["status"] = "DISPUTED"
        self.contracts[contract_id] = json.dumps(contract)

    @gl.public.write
    def adjudicate(self, contract_id: str):
        sender = gl.message.sender_address
        contract = json.loads(self.contracts.get(contract_id, "{}"))
        if not contract:
            raise gl.vm.UserError("Contract not found")
        if self._addr_hex(sender) not in (contract["client"], contract["freelancer"]):
            raise gl.vm.UserError("Only parties can request adjudication")
        if contract["status"] != "DISPUTED":
            raise gl.vm.UserError("Only disputed contracts can be adjudicated")

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

        if outcome == "RELEASE_TO_FREELANCER":
            pct = 100
        if outcome == "REFUND_TO_CLIENT":
            pct = 0

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
            raise gl.vm.UserError("Contract not found")
        if contract["status"] != "RESOLVED":
            raise gl.vm.UserError("Contract not resolved")
        sender_hex = self._addr_hex(sender)
        if sender_hex not in (contract["client"], contract["freelancer"]):
            raise gl.vm.UserError("Only parties can claim")

        claimed_list = json.loads(self.claimed.get(contract_id, "[]"))
        if sender_hex in claimed_list:
            raise gl.vm.UserError("Already claimed")
        claimed_list.append(sender_hex)
        self.claimed[contract_id] = json.dumps(claimed_list)

        total = int(contract["amount"])
        pct = int(contract["freelancer_percentage"])
        freelancer_share = total * pct // 100
        client_share = total - freelancer_share

        payout = freelancer_share if sender_hex == contract["freelancer"] else client_share

        if payout > 0:
            self.send_value(sender, u256(payout))

    def send_value(self, recipient: Address, amount: u256):
        if amount <= 0:
            return
        gl.get_contract_at(recipient).emit_transfer(value=amount, on="accepted")

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
        active = disputed = adjudicating = resolved = completed = cancelled = 0
        for v in self.contracts.values():
            c = json.loads(v)
            if c["status"] == "ACTIVE": active += 1
            elif c["status"] == "DISPUTED": disputed += 1
            elif c["status"] == "ADJUDICATING": adjudicating += 1
            elif c["status"] == "RESOLVED": resolved += 1
            elif c["status"] == "COMPLETED": completed += 1
            elif c["status"] == "CANCELLED": cancelled += 1
        return {
            "total": len(self.contracts),
            "active": active,
            "disputed": disputed,
            "adjudicating": adjudicating,
            "resolved": resolved,
            "completed": completed,
            "cancelled": cancelled,
        }

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
