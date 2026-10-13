"""Randomized state-machine test: random call sequences, random web and model behavior, invariants after every step."""
import os
import random
import unittest

from helpers import (Base, CLAIM_A, CLAIM_B, DOC_BODY, DOC_URL, EVIDENCE, EVIDENCE_QUOTE, OTHER, OWNER, QUOTE_A, QUOTE_B, RT,
                     SRC_A, SRC_A_BODY, SRC_B, SRC_B_BODY, THIRD, page, sha, sim)

STATES = {"DRAFT", "SEALED", "CLEARED", "FLAGGED", "INCONCLUSIVE", "DISPUTED", "ATTESTED", "REVOKED"}
TERMINAL = {"FLAGGED", "REVOKED"}
SENDERS = [OWNER, OWNER, OTHER, THIRD]
STEPS = [0, 1, 59, 60, 61, 599, 600, 3599, 3600, 7200, 86400]
SOURCE_VARIANTS = {
    SRC_A: [(200, SRC_A_BODY), (200, SRC_A_BODY), (200, page("Gone.")), (503, b"down"),
            (200, page("Edited: " + QUOTE_A + " (pending review)"))],
    SRC_B: [(200, SRC_B_BODY), (200, SRC_B_BODY), (200, page("Gone.")), (404, b"gone")],
}
DOC_VARIANTS = [(200, DOC_BODY), (200, DOC_BODY), (200, page(CLAIM_A)), (500, b"down"), (200, DOC_BODY + b" ")]
VERDICTS = ["SUPPORTS", "SUPPORTS", "SUPPORTS", "PARTIAL", "OVERSTATES", "CONTRADICTS", "UNRELATED"]


class FuzzTests(Base):
    def run_sequence(self, seed, length=45):
        rng = random.Random(seed)
        self.setUp()
        self.reset_state = None
        seen_results = {}
        last_state = {}
        for step in range(length):
            self.mutate_world(rng)
            guided = self.natural_call(rng) if rng.random() < 0.8 else None
            name, args, sender = guided if guided else self.pick_call(rng) + (rng.choice(SENDERS),)
            RT.sender = sender
            try:
                getattr(self.c, name)(*args)
            except sim.UserError:
                pass
            except Exception as error:  # anything else is a contract bug
                self.fail("seed %d step %d: %s%r raised %s: %s" % (seed, step, name, args, type(error).__name__, error))
            self.check_invariants(seed, step, name, last_state, seen_results)

    def natural_call(self, rng):
        """The next sensible lifecycle step for a random existing dossier, so runs reach deep states."""
        total = int(self.c.dossier_count)
        if total == 0:
            return ("open_dossier", ("Fuzz review", DOC_URL, rng.choice([300, 600, 3600])), OWNER)
        did = rng.randint(1, total)
        d = self.c.get_dossier(did)
        state, owner = d["state"], OWNER
        cites = {"resp-time": (CLAIM_A, SRC_A, QUOTE_A, SRC_A_BODY), "enrollment": (CLAIM_B, SRC_B, QUOTE_B, SRC_B_BODY)}
        if state == "DRAFT":
            if not d["doc_sha256"]:
                return ("pin_document", (did, sha(DOC_BODY)), owner)
            for cid, (claim, url, quote, body) in cites.items():
                if cid not in d["cite_ids"]:
                    return ("add_citation", (did, cid, claim, url, quote), owner)
                if not self.c.get_citation(did, cid)["anchored"]:
                    return ("anchor_citation", (did, cid, sha(body)), owner)
            return ("seal_dossier", (did,), owner)
        if state in ("SEALED", "INCONCLUSIVE"):
            pending = [c for c in d["cite_ids"] if self.c.get_audit(did, c).get("result", "UNKNOWN") == "UNKNOWN"]
            if pending and rng.random() < 0.85:
                return ("audit_citation", (did, rng.choice(pending)), rng.choice([OWNER, OTHER]))
            if rng.random() < 0.3:
                return ("audit_citation", (did, rng.choice(d["cite_ids"])), rng.choice(SENDERS))
            return ("derive_verdict", (did,), rng.choice(SENDERS))
        if state == "CLEARED":
            roll = rng.random()
            if roll < 0.3:
                return ("open_challenge", (did, rng.choice(d["cite_ids"]), "SOURCE_CORRECTED", EVIDENCE, EVIDENCE_QUOTE), rng.choice([OTHER, THIRD, OWNER]))
            if roll < 0.45:
                return ("audit_citation", (did, rng.choice(d["cite_ids"])), rng.choice(SENDERS))
            RT.time += rng.choice([0, 300, 600, 3600])
            return ("attest", (did,), rng.choice(SENDERS))
        if state == "DISPUTED":
            cite = self.c.get_challenge(did, d["open_challenge"])["cite_id"]
            return ("audit_citation", (did, cite), rng.choice(SENDERS))
        if state == "ATTESTED":
            RT.time += rng.choice([0, 3600, 7200])
            return ("recheck", (did,), rng.choice(SENDERS))
        return None

    def mutate_world(self, rng):
        roll = rng.random()
        if roll < 0.2:
            RT.time += rng.choice(STEPS)
        if roll > 0.88:
            target = rng.choice([SRC_A, SRC_B, DOC_URL])
            RT.pages[target] = rng.choice(DOC_VARIANTS if target == DOC_URL else SOURCE_VARIANTS[target])
        if rng.random() < 0.15:
            pick = rng.choice(VERDICTS)
            challenge = rng.choice(["UPHELD", "REJECTED", "REJECTED", "UNRESOLVED"])
            RT.llm = lambda prompt, v=pick, c=challenge: {"verdict": v, "challenge": c if "CHALLENGE_KIND" in prompt else "NONE", "reason": "r"}

    def pick_call(self, rng):
        did = rng.choice([1, 1, 1, 2, 3])
        cid = rng.choice(["resp-time", "enrollment", "nope"])
        digests = {SRC_A: sha(SRC_A_BODY), SRC_B: sha(SRC_B_BODY)}
        options = [
            ("open_dossier", ("Fuzz review", DOC_URL, rng.choice([300, 600, 3600, 100000]))),
            ("pin_document", (did, rng.choice([sha(DOC_BODY), "0" * 64, "zz"]))),
            ("add_citation", (did, rng.choice(["resp-time", "enrollment", "x1"]), rng.choice([CLAIM_A, CLAIM_B, "nope nope nope nope"]),
                              rng.choice([SRC_A, SRC_B, DOC_URL, "ftp://x"]), rng.choice([QUOTE_A, QUOTE_B, "a b c d e f g h i j k"]))),
            ("anchor_citation", (did, cid, rng.choice([digests[SRC_A], digests[SRC_B], "0" * 64]))),
            ("seal_dossier", (did,)),
            ("audit_citation", (did, cid)),
            ("audit_citation", (did, cid)),
            ("derive_verdict", (did,)),
            ("open_challenge", (did, cid, rng.choice(["SOURCE_CORRECTED", "MISQUOTED", "bad"]), rng.choice([EVIDENCE, DOC_URL]),
                                rng.choice([EVIDENCE_QUOTE, "not on the page at all, really"]))),
            ("attest", (did,)),
            ("recheck", (did,)),
        ]
        weights = [1, 2, 4, 4, 3, 7, 7, 5, 3, 4, 3]
        return rng.choices(options, weights)[0]

    def check_invariants(self, seed, step, call, last_state, seen_results):
        where = "seed %d step %d after %s" % (seed, step, call)
        total = int(self.c.dossier_count)
        for did in range(1, total + 1):
            d = self.c.get_dossier(did)
            self.assertIn(d["state"], STATES, where)
            if did in last_state and last_state[did] in TERMINAL:
                self.assertEqual(d["state"], last_state[did], where + ": terminal state changed")
            last_state[did] = d["state"]
            self.assertEqual(bool(d["open_challenge"]), d["state"] == "DISPUTED", where)
            self.assertLessEqual(d["challenge_count"], self.mod.MAX_CHALLENGES, where)
            self.assertLessEqual(len(d["cite_ids"]), self.mod.MAX_CITATIONS, where)
            if d["state"] != "DRAFT":
                self.assertTrue(d["doc_sha256"], where)
                self.assertTrue(d["cite_ids"], where)
                for cid in d["cite_ids"]:
                    self.assertTrue(self.c.get_citation(did, cid)["anchored"], where)
            if d["state"] == "CLEARED":
                self.assertEqual(d["review_deadline"], d["clear_at"] + d["review_seconds"], where)
                self.assertIn(d["grade"], ("SOUND", "QUALIFIED"), where)
                for cid in d["cite_ids"]:
                    self.assertIn(self.c.get_audit(did, cid)["result"], ("PASS", "WEAK"), where)
            if d["state"] in ("DRAFT", "SEALED", "FLAGGED", "INCONCLUSIVE", "DISPUTED"):
                self.assertEqual(self.c.get_attestation(did), {}, where)
            if d["state"] in ("ATTESTED", "REVOKED"):
                record = self.c.get_attestation(did)["record"]
                self.assertGreaterEqual(record["attested_at"], record["review_deadline"], where)
                self.assertEqual(len(record["rows"]), len(d["cite_ids"]), where)
            if d["state"] == "ATTESTED":
                self.assertEqual(d["revoked_at"], 0, where)
            if d["state"] == "FLAGGED":
                results = [self.c.get_audit(did, c).get("result") for c in d["cite_ids"]]
                self.assertIn("BLOCK", results, where)
            for cid in d["cite_ids"]:
                audit = self.c.get_audit(did, cid)
                if not audit:
                    continue
                self.assertLessEqual(audit["attempt"], self.mod.MAX_ATTEMPTS, where)
                key = (did, cid)
                if key in seen_results and seen_results[key][0] == "BLOCK":
                    self.assertEqual((audit["result"], audit["audit_digest"]), seen_results[key], where + ": block was replaced")
                seen_results[key] = (audit["result"], audit["audit_digest"])
            for challenge_id in range(1, d["challenge_count"] + 1):
                record = self.c.get_challenge(did, challenge_id)
                self.assertEqual(record["resolved"], challenge_id != d["open_challenge"], where)

    def test_random_sequences(self):
        count = int(os.environ.get("QUOTESTONE_FUZZ_RUNS", "120"))
        for seed in range(count):
            self.run_sequence(seed)


if __name__ == "__main__":
    unittest.main()
