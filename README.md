# FactCheckOracle: a reusable claim-verification primitive for GenLayer

A standalone GenLayer Intelligent Contract that lets **any other contract** ask:
*"Is this claim true, according to these sources?"* and receive one settled, on-chain answer.

- Verdict: `TRUE`, `FALSE` or `UNCLEAR`, plus a confidence score
- Stored as an immutable attestation that other contracts can read
- Includes an example consumer (`ClaimGatedEscrow`) and runnable tests

Useful for prediction markets, parametric insurance, escrow release, DAO governance, and bounty or milestone checks.

---

## Why this is not a thin LLM wrapper

The LLM never decides the outcome. It only labels sources. Everything after that is plain, auditable contract code.

| Step | Who does it |
|---|---|
| Fetch each web source | Every validator, independently (non-deterministic) |
| Label each source `SUPPORTS`, `REFUTES` or `NEUTRAL` | LLM, strict three-value enum |
| Turn the labels into a verdict | Deterministic code (`aggregate`) |
| Decide if a validator agrees with the leader | Custom equivalence rule (`equivalent`) |

---

## How consensus works

GenLayer lets validators disagree on the exact wording of an LLM answer, so this contract defines its own agreement rule instead of demanding identical output.

1. The **leader** fetches all sources and labels each one.
2. Every **validator** repeats the same work on its own.
3. A validator accepts the leader only if all of these hold:
   - The verdict derived from the leader's labels equals the verdict derived from the validator's own labels. The leader's claimed verdict is never trusted; it is re-derived.
   - At most **1 source** is labelled differently.
   - Confidence differs by **20 points or less**. Confidence is rounded to steps of 10 to make agreement easier.
4. The verdict is computed from the agreed labels and stored.

A leader that lies about the verdict, or a validator that sees a very different picture, causes the result to be rejected.

### Verdict rules (`aggregate`)
| Condition | Verdict |
|---|---|
| Fewer than `min_evidence` sources take a clear side | `UNCLEAR` |
| 75% or more of the clear sources support the claim | `TRUE` |
| 25% or less support it | `FALSE` |
| Anything in between | `UNCLEAR` |

---

## State design

`attestations: TreeMap[u256, Attestation]` is **append-only**. Each record stores the claim, the requester, the sources, the per-source labels, the verdict, the confidence and `min_evidence`. Records are never edited or deleted, so other protocols can rely on them. A new check always creates a new attestation.

---

## API

| Method | Type | Description |
|---|---|---|
| `check_claim(claim, sources, min_evidence=2)` | write | Verify a claim and store an attestation. Attestation ids start at `0`. |
| `get_verdict(id)` | view | `TRUE`, `FALSE`, `UNCLEAR` or `NOT_FOUND` |
| `get_attestation(id)` | view | Full record |
| `count()` | view | Number of attestations |

Input limits: 1 to 5 unique source URLs, claim up to 500 characters, and `1 <= min_evidence <= number of sources`.

---

## Quick start (GenLayer Studio)

1. Deploy `fact_check_oracle.py` (no constructor arguments).
2. Call `check_claim` with:
   - claim: `The Earth orbits the Sun`
   - sources: `["https://en.wikipedia.org/wiki/Earth", "https://science.nasa.gov/earth/facts/"]`
   - min_evidence: `2`
3. Call `get_verdict` with `0`. Expected result: `"TRUE"`.

### Reuse from another contract
`claim_gated_escrow.py` shows the pattern. Deploy it with the oracle's address and an attestation id. Calling `settle` reads the verdict: `TRUE` moves the state to `RELEASED`, `FALSE` to `REFUNDED`, and `UNCLEAR` leaves it on `HOLD`.

---

## Tested on GenLayer Studio

Test claim: "The Earth orbits the Sun"

Both contracts were deployed and run in GenLayer Studio. The oracle settled the claim as `TRUE`, and the escrow read that verdict and moved to `RELEASED`.

![Studio test 1](genlayer.jpg)
![Studio test 2](genlayer2.jpg)
![Studio test 3](genlayer3.jpg)

## Unit tests

The consensus rules (`aggregate`, `normalize`, `equivalent`) are tested without a network or a GenLayer install:

```
pip install pytest
pytest -v
```

12 tests cover the verdict thresholds, malformed LLM output, confidence rounding, and the validator agreement rule, including a lying leader, a verdict-flipping disagreement, too many differing labels, and a large confidence gap.

---

## Limitations and security notes

Read these before relying on the oracle.

- **The caller chooses the sources.** The contract cannot tell whether a URL is trustworthy. A bad actor could point it at a page they control. Consuming contracts should pass their own fixed, reputable sources, or check which sources an attestation used with `get_attestation`. A future version could add an allow-list of approved domains.
- **Sources can contain hostile text.** A web page may try to instruct the LLM. The design limits the damage: the LLM can only output three labels per source, and the verdict comes from code. A single poisoned source cannot decide the result when several sources are used, but it can still shift a result when `min_evidence` is low. Use at least 3 independent sources for anything valuable.
- **Verdicts are a snapshot in time.** A claim that is true today may be false later. Attestations are never updated. A consumer that needs fresh data should run a new `check_claim` and use the new id.
- **Unreadable pages count as `NEUTRAL`.** If a site blocks scraping or is down, it adds no evidence. This can push a result to `UNCLEAR`.
- **Best for checkable facts.** Opinions, predictions and vague claims will mostly return `UNCLEAR`.
- **Escrow is a pattern demo.** `ClaimGatedEscrow` changes a state label only. It does not hold or move tokens.

---

## Files

| File | Purpose |
|---|---|
| `fact_check_oracle.py` | The oracle primitive |
| `claim_gated_escrow.py` | Example consumer showing reuse |
| `test_fact_check_oracle.py` | Unit tests for the consensus rules |
| `conftest.py` | Lets the tests run without the GenLayer SDK |
