# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
FactCheckOracle - a reusable GenLayer primitive for verifying real-world claims.

Other contracts call `check_claim(claim, sources)` and later read a settled,
immutable attestation (TRUE / FALSE / UNCLEAR + confidence).

Design idea (why this is not a thin LLM wrapper):
  1. The LLM is only used to classify EACH source as SUPPORTS / REFUTES / NEUTRAL.
  2. The final verdict is computed by deterministic contract code from those
     per-source stances (quorum rules, minimum evidence, ratio thresholds).
  3. Validators re-fetch the sources, re-classify, and a custom equivalence
     function decides if they agree with the leader (see `equivalent`).
"""

from genlayer import *

import json
from dataclasses import dataclass

# ---- constants -------------------------------------------------------------
TRUE = "TRUE"
FALSE = "FALSE"
UNCLEAR = "UNCLEAR"

SUPPORTS = "SUPPORTS"
REFUTES = "REFUTES"
NEUTRAL = "NEUTRAL"
VALID_STANCES = (SUPPORTS, REFUTES, NEUTRAL)

MAX_SOURCES = 5
MAX_CLAIM_CHARS = 500
PAGE_CHARS = 6000          # per-source text sent to the LLM
CONF_STEP = 10             # confidence is bucketed to ease consensus
CONF_TOLERANCE = 20        # validators may differ by this many points
PCT_TRUE = 75              # >= 75% of decisive sources support -> TRUE
PCT_FALSE = 25             # <= 25% of decisive sources support -> FALSE
MAX_STANCE_DISAGREEMENTS = 1


# ---- pure deterministic helpers (no storage, safe inside nondet blocks) ----
def aggregate(stances: list, min_evidence: int) -> str:
    """Deterministic verdict from per-source stances."""
    supports = stances.count(SUPPORTS)
    refutes = stances.count(REFUTES)
    decisive = supports + refutes
    if decisive < min_evidence:
        return UNCLEAR
    pct = supports * 100 // decisive
    if pct >= PCT_TRUE:
        return TRUE
    if pct <= PCT_FALSE:
        return FALSE
    return UNCLEAR


def normalize(raw, n_sources: int) -> dict:
    """Force whatever the LLM returned into a strict, comparable shape."""
    if isinstance(raw, str):
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    items = raw.get("sources", [])
    if not isinstance(items, list):
        items = []

    stances = []
    for i in range(n_sources):
        stance = NEUTRAL
        if i < len(items) and isinstance(items[i], dict):
            value = str(items[i].get("stance", "")).upper().strip()
            if value in VALID_STANCES:
                stance = value
        stances.append(stance)

    try:
        conf = int(raw.get("confidence", 0))
    except Exception:
        conf = 0
    conf = max(0, min(100, conf))
    conf = (conf + CONF_STEP // 2) // CONF_STEP * CONF_STEP
    return {"stances": stances, "confidence": conf}


def equivalent(leader: dict, mine: dict, min_evidence: int) -> bool:
    """
    Validator agreement rule. Validators accept the leader if:
      - the verdict derived from the leader's stances equals the verdict
        derived from the validator's own stances,
      - at most MAX_STANCE_DISAGREEMENTS sources are classified differently,
      - confidence differs by no more than CONF_TOLERANCE.
    The leader's own claimed verdict is never trusted; it is re-derived.
    """
    if len(leader["stances"]) != len(mine["stances"]):
        return False
    if aggregate(leader["stances"], min_evidence) != aggregate(mine["stances"], min_evidence):
        return False
    diffs = sum(1 for a, b in zip(leader["stances"], mine["stances"]) if a != b)
    if diffs > MAX_STANCE_DISAGREEMENTS:
        return False
    return abs(leader["confidence"] - mine["confidence"]) <= CONF_TOLERANCE


def evaluate(claim: str, sources: list) -> dict:
    """Non-deterministic step: fetch every source, ask the LLM to classify each."""
    blocks = []
    for i, url in enumerate(sources):
        try:
            text = gl.nondet.web.render(url, mode="text")[:PAGE_CHARS]
        except Exception:
            text = "[SOURCE UNAVAILABLE]"
        blocks.append(f"### SOURCE {i} ({url})\n{text}")

    prompt = f"""You are a strict fact-checking assistant.
CLAIM: {claim}

For EACH source below decide whether it SUPPORTS the claim, REFUTES it, or is
NEUTRAL (unrelated, unavailable, or not conclusive). Judge each source on its
own. Use only the text given. Do not use outside knowledge.

{chr(10).join(blocks)}

Reply with JSON only, exactly in this shape:
{{"sources": [{{"stance": "SUPPORTS|REFUTES|NEUTRAL"}}], "confidence": 0-100}}
"sources" must have {len(sources)} entries in the same order as the sources.
"confidence" is how sure you are about the overall picture."""

    raw = gl.nondet.exec_prompt(prompt, response_format="json")
    return normalize(raw, len(sources))


# ---- storage ----------------------------------------------------------------
@allow_storage
@dataclass
class Attestation:
    claim: str
    requester: Address
    sources_json: str
    stances_json: str
    verdict: str
    confidence: u256
    min_evidence: u256


# ---- contract ---------------------------------------------------------------
class FactCheckOracle(gl.Contract):
    attestations: TreeMap[u256, Attestation]
    next_id: u256

    def __init__(self):
        self.next_id = u256(0)

    @gl.public.write
    def check_claim(self, claim: str, sources: list[str], min_evidence: int = 2) -> int:
        """
        Verify `claim` against `sources` (URLs). Stores an immutable attestation
        and returns its id. `min_evidence` = how many sources must take a clear
        side (SUPPORTS or REFUTES) before a TRUE/FALSE verdict is allowed.
        """
        if not (1 <= len(claim) <= MAX_CLAIM_CHARS):
            raise Exception("claim length must be 1-500 chars")
        if not (1 <= len(sources) <= MAX_SOURCES):
            raise Exception("provide 1-5 sources")
        if len(set(sources)) != len(sources):
            raise Exception("duplicate sources are not allowed")
        if not (1 <= min_evidence <= len(sources)):
            raise Exception("min_evidence must be between 1 and number of sources")

        # Copy to plain locals: storage cannot be read inside nondet blocks.
        claim_l = str(claim)
        sources_l = [str(s) for s in sources]
        min_l = int(min_evidence)

        def leader_fn():
            return evaluate(claim_l, sources_l)

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False
            leader = leaders_res.calldata
            try:
                mine = evaluate(claim_l, sources_l)
            except Exception:
                return False
            return equivalent(leader, mine, min_l)

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        # Verdict is derived deterministically from the agreed stances.
        verdict = aggregate(result["stances"], min_l)

        att_id = self.next_id
        self.attestations[att_id] = Attestation(
            claim=claim_l,
            requester=gl.message.sender_address,
            sources_json=json.dumps(sources_l),
            stances_json=json.dumps(result["stances"]),
            verdict=verdict,
            confidence=u256(result["confidence"]),
            min_evidence=u256(min_l),
        )
        self.next_id = u256(int(att_id) + 1)
        return int(att_id)

    # ---- read API (what other contracts call) ------------------------------
    @gl.public.view
    def get_verdict(self, att_id: int) -> str:
        """TRUE, FALSE, UNCLEAR, or NOT_FOUND."""
        key = u256(att_id)
        if key not in self.attestations:
            return "NOT_FOUND"
        return self.attestations[key].verdict

    @gl.public.view
    def get_attestation(self, att_id: int) -> dict:
        key = u256(att_id)
        if key not in self.attestations:
            return {}
        a = self.attestations[key]
        return {
            "claim": a.claim,
            "requester": a.requester.as_hex,
            "sources": json.loads(a.sources_json),
            "stances": json.loads(a.stances_json),
            "verdict": a.verdict,
            "confidence": int(a.confidence),
            "min_evidence": int(a.min_evidence),
        }

    @gl.public.view
    def count(self) -> int:
        return int(self.next_id)
