# Protocol notes

Protocol identifier: `quotestone.citation-ledger.v1`.

## Text handling

Every comparison uses the same folding, so owners and validators see identical strings:

1. HTML bodies drop `script`, `style`, `noscript` and `template` blocks and comments in a single linear pass. An unclosed block hides the rest of the page, as a browser would.
2. Inline tags (`a`, `b`, `i`, `em`, `strong`, `span`, `code`, `sup`, `sub` and a few more) are removed without a space, so `un<b>believ</b>able` reads `unbelievable`. All other tags become a space.
3. Numeric entities and common named entities are decoded; surrogate and out-of-range code points become a space.
4. Typographic quotes and dashes are folded to ASCII, zero-width characters and soft hyphens are deleted, text is lower-cased, and whitespace runs collapse to one space.
5. A quote or claim matches only on whole-word boundaries, so `increase it` never matches inside `decrease it`.

Quotes (including a challenger's evidence quote) need at least 20 characters and four words (at most 300 characters). Claims need 12 to 400 characters. The excerpt around a quote is 280 characters either side.

## Data model

| Record | Key | Contents |
|---|---|---|
| Dossier | `id` | owner, title, state, document URL and digest, citation ids, grade, review window, challenge counters, last re-check |
| Document | `id` | folded visible text of the pinned document |
| Citation | `id:cite_id` | claim, source URL, quote, anchor (body digest, excerpt, excerpt digest, time) |
| Audit | `id:cite_id` | latest observation: code, status, body digest, excerpt digest, anchor match, verdict, challenge outcome, result, attempt, audit digest |
| Challenge | `id:n` | citation, kind, evidence URL, quote, excerpt, challenger, resolution |
| Attestation | `id` | grade, document digest, per-citation rows, freshness root, attestation digest |
| Event | ring buffer of 256 | ordered log of every state change |

## Permissions

| Action | Who | Condition |
|---|---|---|
| `open_dossier` | anyone | valid title, URL, window |
| `pin_document`, `add_citation`, `anchor_citation`, `seal_dossier` | owner | state `DRAFT` |
| `audit_citation`, first time | anyone | state `SEALED` or `INCONCLUSIVE` |
| `audit_citation`, retry after `UNKNOWN` | owner after 60 s, anyone after 3600 s | fewer than five ordinary audits so far |
| `audit_citation`, after `PASS` or `WEAK` | owner only | any auditable state; restarts the review window if `CLEARED` |
| `audit_citation`, during a dispute | anyone | only the challenged citation; retries wait 3600 s |
| `derive_verdict` | anyone | state `SEALED` or `INCONCLUSIVE`, every citation audited |
| `open_challenge` | anyone except the owner | state `CLEARED`, before the deadline, fewer than five used |
| `attest` | anyone | state `CLEARED`, no open challenge, deadline reached, fresh re-fetch passes |
| `recheck` | anyone | state `ATTESTED`, 3600 s since the last check |

A `BLOCK` result locks its citation for good. `FLAGGED`, `REVOKED` and an exhausted `INCONCLUSIVE` are terminal.

## Challenge resolution

Opening a challenge verifies that the challenger's quote exists on the evidence page and stores the excerpt. Resolution is an ordinary audit of the challenged citation with the evidence attached:

| Challenge outcome | Result | Dossier |
|---|---|---|
| `UPHELD` | `BLOCK` | `FLAGGED` after `derive_verdict` |
| `REJECTED` | from the verdict | back to `CLEARED` with a fresh full review window |
| `UNRESOLVED` or unreadable source | `UNKNOWN` | stays `DISPUTED` for up to five tries (one hour apart), then the challenge closes as unresolved and the dossier becomes `INCONCLUSIVE` |
| source quote missing | `BLOCK` (challenge recorded as `MOOT`) | `FLAGGED` |

## Consensus

Each nondeterministic step returns a plain dictionary. Validators recompute it from scratch and accept only if every field matches, ignoring only the short `reason` text, which must still be a string of at most 240 characters. For audits the model's `verdict` and `challenge` labels are first checked against their closed sets and then compared by outcome class (`PASS`, `WEAK`, `BLOCK`, `UNKNOWN`); the leader's own label is what gets stored. Anything observed on the web is reduced to digests and bounded excerpts before it leaves the block.

## Attestation record

`freshness_root` is the canonical-JSON SHA-256 of the seal: protocol id, dossier id, grade, document digest, and one row per citation with the source body digest, excerpt digest and audit digest. `attestation_digest` hashes the full record including the root, review deadline and attestation time.

Canonical JSON means sorted keys, `,` and `:` separators, ASCII escaping.
