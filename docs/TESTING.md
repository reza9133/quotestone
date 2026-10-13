# Testing Quotestone

## Local checks

```bash
python3 -m py_compile contracts/quotestone.py
python3 -m unittest discover -s tests
```

`pytest tests` works too when pytest is installed. Nothing outside the Python standard library is required; the fixture tests additionally need Node.js and are skipped without it.

### What the suites cover

| File | Focus |
|---|---|
| `tests/test_text.py` | clock parsing against Python's own calendar, markup stripping, entities, folding, whole-word matching, bounded-time parsing of hostile markup |
| `tests/test_behavior.py` | every lifecycle step, validation failures, verdict aggregation, retry and cooldown rules, challenges, attestation, re-checks, paging and the event ring |
| `tests/test_adversarial.py` | dishonest leaders, validators that disagree, prompt-injection pages, hidden text, late edits, restoring a page after a blocking result, isolation between dossiers |
| `tests/test_fixtures.py` | full scenarios built from the exact bytes served by `fixtures/` |
| `tests/test_fuzz.py` | random call sequences with random page, model and clock behavior; invariants checked after every step (terminal states, block locks, window arithmetic, challenge bookkeeping). `QUOTESTONE_FUZZ_RUNS=4000` runs a longer campaign |
| `tests/test_static.py` | storage layout, public surface, annotations, absence of clocks, floats and storage access inside non-deterministic blocks |

### The runtime simulator

`tests/sim/genlayer.py` registers a module named `genlayer` that provides `gl`, `TreeMap`, `u256` and `Address`. It enforces the rules the contract must obey:

- a failing call rolls storage back, and view methods cannot write;
- storage, sender and block time are unreachable inside non-deterministic blocks;
- web and model access exist only inside those blocks, and the web only serves pages the test registers;
- results must be calldata-encodable (no floats, tuples or sets);
- every block is replayed on four validator nodes that can be given different pages or models;
- public arguments are type-checked against their annotations.

It is a test aid, not the real GenVM. Passing it means the logic and the data-flow rules hold; the final check is a run on StudioNet.

## Fixture

`fixtures/` serves a small public evidence set: a review document, two cited sources and a correction notice. The same handler runs in three scenarios chosen by the `MODE` environment variable:

| Mode | Behavior |
|---|---|
| `sound` | sources back both claims |
| `overstated` | the quoted sentence stays, but surrounding text narrows what it covers |
| `rotted` | the quoted sentences are gone |

Print the commitments for each mode:

```bash
node fixtures/digests.js
```

Commitments for the `sound` set:

```text
document  1af0135a13ab05a6141d204d193df69a83c015e527c5305922d932d442a72983
visits    659e19670677f22d695984003aeb006c8172631bf04f85822537bf9ef59c73b6
branches  2f7b0b36fb87fc730a11036c804cdfb2a48d295279bfa4d67ecc2bb16a71c08b
```

Deploy `fixtures/` as a static function (see `fixtures/vercel.json`) and confirm the served bytes match: `curl -s "$BASE/review.html" | sha256sum`. To simulate rot, change `MODE` and redeploy to the same alias after the citations are anchored.

## Deploying to StudioNet

Use the GenLayer CLI against StudioNet (`genlayer --help` lists the exact commands for your version):

```bash
genlayer deploy --contract contracts/quotestone.py
ADDRESS=0x...   # printed by the deployment
genlayer call "$ADDRESS" get_protocol_identity
```

## A live walkthrough

With `BASE` pointing at the deployed fixture in `sound` mode:

```bash
genlayer write "$ADDRESS" open_dossier --args "Library review" "$BASE/review.html" 300
genlayer write "$ADDRESS" pin_document --args 1 1af0135a13ab05a6141d204d193df69a83c015e527c5305922d932d442a72983

genlayer write "$ADDRESS" add_citation --args 1 visits \
  "Public library visits rose by 12 percent in 2025 compared with 2024." \
  "$BASE/sources/visits.html" "visits rose by 12 percent in 2025 compared with 2024"
genlayer write "$ADDRESS" anchor_citation --args 1 visits 659e19670677f22d695984003aeb006c8172631bf04f85822537bf9ef59c73b6

genlayer write "$ADDRESS" add_citation --args 1 branches \
  "The city opened four new branch locations during 2025." \
  "$BASE/sources/branches.html" "opened four new branch locations during 2025"
genlayer write "$ADDRESS" anchor_citation --args 1 branches 2f7b0b36fb87fc730a11036c804cdfb2a48d295279bfa4d67ecc2bb16a71c08b

genlayer write "$ADDRESS" seal_dossier --args 1
genlayer write "$ADDRESS" audit_citation --args 1 visits
genlayer write "$ADDRESS" audit_citation --args 1 branches
genlayer write "$ADDRESS" derive_verdict --args 1
# wait for the 300 second review window
genlayer write "$ADDRESS" attest --args 1
genlayer call  "$ADDRESS" get_attestation --args 1
```

Re-check an attestation at least an hour later with `recheck`. To see a revocation, switch the fixture to `rotted` and call `recheck` again.

Record the deployed address, transaction hashes and source digest (`sha256sum contracts/quotestone.py`) alongside any live results you publish.
