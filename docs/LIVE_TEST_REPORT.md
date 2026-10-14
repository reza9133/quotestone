# Quotestone End-to-End on StudioNet

Live on-chain execution audit trail for the Quotestone Intelligent Contract deployed on GenLayer StudioNet.

* **Contract Address:** `0x69DeE8f8891d2B9B5d408178Dd13fCfDbD2DE359`

* **Contract Source Digest (SHA-256):** `d20835eb634ea2b3e836b7b2759274191a7190b2f0df02c60f6e268b0eb4cb32`

* **Dossier:** ID 1 (Title: "Library review")

* **Document URL:** `https://quotestone-fixtures.vercel.app/review.html`

* **Evidence Source URL:** `https://quotestone-fixtures.vercel.app/sources/visits.html`

* **Final State:** **ATTESTED** (Check Outcome: `INTACT`)

## Transactions

| \# | call | hash | decision | execution | 
| ----- | ----- | ----- | ----- | ----- | 
| 1 | `open_dossier` | `0xb560c378bd3dfe1df9b016088c7accdf96c1ca7d7cd9f12326cf6193c2155226` | ACCEPTED | SUCCESS | 
| 2 | `pin_document` | `0x1bf3e6c4385776b45ab639fe6be60591fe21b8d6a36e4f34222f236b24b74b08` | ACCEPTED | SUCCESS | 
| 3 | `add_citation` | `0xe5e533c0c230b50f803e4c2fe644bd56c8f9d05e4baa21b5bbd1cd92c49a8225` | ACCEPTED | SUCCESS | 
| 4 | `anchor_citation` | `0xeca57ed8bfd8ee135f66fe269afb648402e3f3fb5d0639b32d6723c345519f58` | ACCEPTED | SUCCESS | 
| 5 | `seal_dossier` | `0xd4bafc7173499c8b2d754dfba0c24b34d4864f3a6102e339cd0492a7bce22d51` | ACCEPTED | SUCCESS | 
| 6 | `audit_citation` | `0x4afae429e64f151bca0595bc9f638dcd8f668591b22c69c86baffb700f210ba4` | ACCEPTED | SUCCESS | 
| 7 | `derive_verdict` | `0xe3f70b452bece388c496ac5d6291ae63181b501711ef3954711abd97f9c1913e` | ACCEPTED | SUCCESS | 
| 8 | `attest` | `0xf7cf237a575a00d5c0540fa8998d92310de5384301ad6a5a834fba4531695f94` | ACCEPTED | SUCCESS | 
| 9 | `recheck` | `0xbbb9b85680695471ed5cb410201d5a2c68e6c88d60722aec136eb79cc70eb2b9` | ACCEPTED | SUCCESS | 

## On-Chain Audit & Verification

| Property | Value | 
| ----- | ----- | 
| Dossier ID | `1` | 
| Citation ID | `visits` | 
| Grade | `SOUND` | 
| Document Commitment Digest | `1af0135a13ab05a6141d204d193df69a83c015e527c5305922d932d442a72983` | 
| Source Anchor Digest | `659e19670677f22d695984003aeb006c8172631bf04f85822537bf9ef59c73b6` | 
| LLM Result Class | `PASS` | 
| Recheck Outcome | `INTACT` | 

## LLM Adjudication Details

* **Claim:** "Public library visits rose by 12 percent in 2025 compared with 2024."

* **Source Quote Anchored:** "visits rose by 12 percent in 2025 compared with 2024"

* **Model Verdict:** `SUPPORTS`

* **Consensus Reason:**

  > "The source excerpt explicitly states that total visits rose by 12 percent in 2025 compared with 2024, directly supporting the claim."

## Lifecycle Summary

1. **Document Registration (`open_dossier`, `pin_document`):**
   Dossier initialized with a 300-second review window. The target document text was pinned via SHA-256 validation (`1af0135...`).

2. **Citation Anchoring (`add_citation`, `anchor_citation`):**
   A claim and source reference were registered. Validators fetched the source page, executed linear HTML parsing to extract visible text, and anchored an excerpt window backed by a SHA-256 hash (`659e19...`).

3. **Consensus Audit (`audit_citation`, `derive_verdict`):**
   The dossier was `SEALED`. Validators independently retrieved the anchored excerpts and reached consensus on the LLM's assessment. The output evaluated to `SUPPORTS`, advancing the state to `CLEARED`.

4. **Attestation & Monitoring (`attest`, `recheck`):**
   After the 300-second review window closed without active challenges, `attest` recorded the attestation digest on-chain. A subsequent `recheck` confirmed the document and references remained unaltered (`INTACT`).