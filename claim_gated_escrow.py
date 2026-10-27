# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
ClaimGatedEscrow - example consumer of FactCheckOracle.

Shows how another contract reuses the oracle: money state moves only after
the oracle has settled a claim. (Token transfers are left out to keep the
example about the integration pattern.)
"""

from genlayer import *


class ClaimGatedEscrow(gl.Contract):
    oracle: Address
    attestation_id: u256
    state: str  # HOLD | RELEASED | REFUNDED
    last_read: str  # what the escrow last read from the oracle (debug)

    def __init__(self, oracle_address: str, attestation_id: int):
        self.oracle = Address(oracle_address)
        self.attestation_id = u256(attestation_id)
        self.state = "HOLD"
        self.last_read = ""

    @gl.public.write
    def settle(self) -> str:
        if self.state != "HOLD":
            return self.state
        oracle = gl.get_contract_at(self.oracle)
        verdict = oracle.view().get_verdict(int(self.attestation_id))
        self.last_read = str(verdict).strip().strip('"').upper()
        verdict = self.last_read
        if verdict == "TRUE":
            self.state = "RELEASED"
        elif verdict == "FALSE":
            self.state = "REFUNDED"
        # UNCLEAR / NOT_FOUND -> stay in HOLD
        return self.state

    @gl.public.view
    def get_state(self) -> str:
        return self.state

    @gl.public.view
    def get_last_read(self) -> str:
        return self.last_read
