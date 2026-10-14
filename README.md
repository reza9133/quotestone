# Quotestone

Quotestone is a GenLayer Intelligent Contract that checks whether the sources a document cites really say what the document claims, and keeps checking afterwards.

A publisher pins a public document, lists each claim together with the source URL and the exact sentence that is supposed to back it, and lets validators audit every pair. Anyone can challenge a cleared citation with public counter-evidence. When the review window closes without a surviving objection the contract records an attestation, and from then on anyone can re-check it: if a cited sentence disappears from its source, the attestation is revoked on-chain.

## What is verified, and how

| Question | Decided by |
|---|---|
| Is the claim really in the pinned document? | Deterministic whole-word text match against the document text stored at pin time |
| Does the cited sentence really exist in the source? | Deterministic whole-word match on the live page, repeated by every validator |
| Are we looking at the bytes the owner committed to? | SHA-256 of the exact HTTP response body, compared with the owner's commitment |
| Does the excerpt back the claim? | Validator language model, restricted to a closed verdict set, only after the checks above pass |
| Is the evidence behind a challenge real? | Deterministic match of the challenger's quoted sentence on the evidence page |
| Is the source still the same? | SHA-256 of the excerpt window around the quote, re-fetched at attestation and at every re-check |

The model never sees a source whose quote is missing, never produces free-form output that reaches storage, and any reply outside the exact schema fails closed to `UNKNOWN`.

## Verdicts and results

Per citation the model chooses one of `SUPPORTS`, `PARTIAL`, `OVERSTATES`, `CONTRADICTS`, `UNRELATED`. The contract adds two deterministic outcomes, `QUOTE_MISSING` and `UNREADABLE`, and collapses everything into a result:

| Result | Produced by | Effect on the dossier |
|---|---|---|
| `PASS` | `SUPPORTS` | counts toward grade `SOUND` |
| `WEAK` | `PARTIAL` | counts toward grade `QUALIFIED` |
| `BLOCK` | `OVERSTATES`, `CONTRADICTS`, `UNRELATED`, `QUOTE_MISSING`, an upheld challenge | dossier becomes `FLAGGED` (terminal) |
| `UNKNOWN` | `UNREADABLE`, invalid model output, unresolved challenge | dossier becomes `INCONCLUSIVE` |

A blocking result locks its citation: restoring the page afterwards cannot turn it back into a pass.

## Lifecycle

1. `open_dossier` fixes the owner, title, document URL and a review window of 300 to 1,209,600 seconds.
2. `pin_document` fetches the document, requires its body digest to equal the owner's commitment, and stores the visible text (at most 20,000 characters).
3. `add_citation` registers a claim that must occur in the pinned text, a source URL, and a verbatim quote of at least four words.
4. `anchor_citation` fetches the source, requires the committed body digest and the quote, and stores an excerpt window as evidence of what the owner relied on.
5. `seal_dossier` freezes the citation set once every citation is anchored.
6. `audit_citation` re-fetches the source and records a verdict. `derive_verdict` then aggregates the latest results into `CLEARED`, `FLAGGED` or `INCONCLUSIVE` and starts the review window when cleared.
7. During the window any non-owner can call `open_challenge` with an evidence URL, a challenge kind and a verbatim quote from that page. The dossier is `DISPUTED` until the challenged citation is audited again; a rejected challenge restarts a full window.
8. `attest` runs after the window. It re-fetches the document and every source and requires unchanged document bytes, present claims, present quotes and unchanged excerpt windows, then stores the attestation with a freshness root.
9. `recheck` can be called by anyone every hour. Missing quotes or claims revoke the attestation; outages produce `UNVERIFIED`; moved context produces `DRIFTED` without revoking.

```text
DRAFT -> SEALED -> CLEARED -> ATTESTED -> REVOKED
            |         |
            |         +-> DISPUTED -> SEALED (re-derive)
            +-> FLAGGED (terminal)
            +-> INCONCLUSIVE (re-audit while attempts remain)
```

## Safeguards

- Every nondeterministic result is recomputed by the validators. Every recorded fact must match exactly; only the short model explanation is free, and the model's verdict label is compared by outcome class (`OVERSTATES` and `CONTRADICTS` are both blocking, while `SUPPORTS` and `PARTIAL` must agree), so harmless label differences do not stall consensus.
- Non-deterministic blocks use only plain values captured beforehand: no storage reads, no sender, no clock.
- Block time comes from the validator-agreed message timestamp, never from a wall clock.
- Web pages are reduced to visible text by a linear-time parser that drops scripts, styles, templates and comments, so hidden text cannot satisfy a quote and hostile markup cannot stall validators.
- Page text is fenced and neutralised before it reaches the model, and the reply must be an exact JSON object.
- Ordinary audits are capped at five per citation, and each challenge has its own budget of five tries, so a pile of objections cannot exhaust the budget of the citation they target. The owner may retry after 60 seconds; everyone else only after one hour, so strangers cannot burn attempts during a short outage.
- Only the owner can re-audit a citation that already passed, and doing so restarts the review window. Third parties can only fill in missing audits or retry unreadable ones.
- Challenges are capped at five per dossier, need a deterministic match of a quote of at least four words on the evidence page, and a rejected challenge restarts a full review window, so every challenger gets a fresh opportunity.

## Public API

Write methods: `open_dossier`, `pin_document`, `add_citation`, `anchor_citation`, `seal_dossier`, `audit_citation`, `derive_verdict`, `open_challenge`, `attest`, `recheck`.

Read methods: `get_protocol_identity`, `get_dossier`, `get_document`, `get_citation`, `get_audit`, `get_challenge`, `get_attestation`, `list_dossiers`, `get_events`.

Digests are lowercase hexadecimal SHA-256 over the exact response bytes. Compute them with `curl -s URL | sha256sum`.

## Limits and honest caveats

- Cited pages must serve identical bytes to every validator while a transaction runs. Prefer immutable snapshots or static hosting; pages with rotating banners will make consensus fail rather than produce a wrong answer.
- The document is pinned by exact bytes. If it is edited after pinning, attestation fails closed and a new dossier is needed.
- A source owner can remove a quote at any time and thereby revoke an attestation that cites them; that is intended, and recheck exists to surface it.
- The challenge cap counts rejected challenges too, so a dossier that has absorbed five rejected objections accepts no more. Watch the review window and challenge early.
- `INCONCLUSIVE` after the attempt limit is permanent. Open a new dossier if a source stays unreadable for hours.
- Only UTF-8 text and HTML are parsed. JavaScript-rendered content is not executed.
- The contract judges whether a source supports a claim, not whether the claim is true.

## Repository layout

```text
contracts/quotestone.py          Intelligent Contract source
tests/                           Unit, behavior, adversarial and fixture-driven tests
tests/sim/genlayer.py            Local runtime simulator used by the tests
fixtures/                        Public evidence fixture (three scenarios) and digest tool
docs/PROTOCOL.md                 Rules, permissions and data model
docs/LIVE_TEST_REPORT.md          StudioNet run: one dossier attested and re-checked
docs/TESTING.md                  Verification, deployment and live-run walkthrough
gltest.config.yaml               StudioNet project configuration
```

## Live run

Contract `0x69DeE8f8891d2B9B5d408178Dd13fCfDbD2DE359` on StudioNet took one dossier from `open_dossier` through `attest` and `recheck` (`INTACT`). Transactions and the source digest are in [docs/LIVE_TEST_REPORT.md](docs/LIVE_TEST_REPORT.md).

## Local verification

```bash
python3 -m py_compile contracts/quotestone.py
python3 -m unittest discover -s tests
```

`tests/sim/genlayer.py` imitates the parts of the runtime the contract depends on. It does not replace running the contract on StudioNet; see [docs/TESTING.md](docs/TESTING.md).
