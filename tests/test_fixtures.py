"""End-to-end scenarios driven by the exact bytes the public fixture serves (skipped when Node is unavailable)."""
import json
import os
import shutil
import subprocess
import unittest

from helpers import Base, OTHER, OWNER, RT, THIRD, ROOT

BASE = "https://fixture.example"
DOC_URL = BASE + "/review.html"
EVIDENCE_URL = BASE + "/corrections/visits.html"


def dump():
    node = shutil.which("node")
    if node is None:
        return None
    out = subprocess.run([node, os.path.join(ROOT, "fixtures", "digests.js"), "--json"], check=True, capture_output=True)
    return json.loads(out.stdout)


DATA = dump()


@unittest.skipIf(DATA is None, "node is not installed")
class FixtureScenarioTests(Base):
    def serve(self, mode):
        RT.pages.clear()
        RT.pages[DOC_URL] = (200, DATA["document"]["body"].encode())
        RT.pages[EVIDENCE_URL] = (200, DATA["evidence"]["body"].encode())
        for item in DATA["claims"]:
            RT.pages[BASE + item["path"]] = (200, DATA["modes"][mode]["bodies"][item["id"]].encode())

    def build(self, mode="sound", review=300):
        self.serve("sound")
        digests = DATA["modes"]["sound"]["digests"]
        did = self.call("open_dossier", "Library review", DOC_URL, review)
        self.call("pin_document", did, digests["document"])
        for item in DATA["claims"]:
            self.call("add_citation", did, item["id"], item["claim"], BASE + item["path"], item["quote"])
            self.call("anchor_citation", did, item["id"], digests["sources"][item["id"]])
        self.call("seal_dossier", did)
        self.serve(mode)
        return did

    def test_published_digests_match_the_served_bytes(self):
        import hashlib
        for mode, info in DATA["modes"].items():
            for item in DATA["claims"]:
                body = info["bodies"][item["id"]].encode()
                self.assertEqual(hashlib.sha256(body).hexdigest(), info["digests"]["sources"][item["id"]], mode)

    def test_sound_release_reaches_attestation_and_stays_intact(self):
        did = self.build("sound")
        for item in DATA["claims"]:
            self.assertEqual(self.call("audit_citation", did, item["id"], sender=THIRD), "PASS")
            self.assertTrue(self.c.get_audit(did, item["id"])["anchor_match"])
        self.assertEqual(self.call("derive_verdict", did), "CLEARED")
        self.tick(300)
        self.call("attest", did, sender=THIRD)
        self.tick(3600)
        self.assertEqual(self.call("recheck", did), "INTACT")

    def test_overstated_mode_is_flagged_by_a_model_that_reads_the_context(self):
        did = self.build("overstated")

        def reader(prompt):
            narrowed = "central branch alone" in prompt
            return {"verdict": "OVERSTATES" if narrowed else "SUPPORTS", "challenge": "NONE", "reason": "scope check"}

        RT.llm = reader
        for item in DATA["claims"]:
            self.call("audit_citation", did, item["id"])
        self.assertEqual(self.c.get_audit(did, "visits")["result"], "BLOCK")
        self.assertFalse(self.c.get_audit(did, "visits")["anchor_match"])
        self.assertEqual(self.c.get_audit(did, "branches")["result"], "PASS")
        self.assertEqual(self.call("derive_verdict", did), "FLAGGED")

    def test_rotted_mode_blocks_without_calling_the_model(self):
        did = self.build("rotted")
        for item in DATA["claims"]:
            self.assertEqual(self.call("audit_citation", did, item["id"]), "BLOCK")
        self.assertEqual(RT.prompts, [])
        self.assertEqual(self.call("derive_verdict", did), "FLAGGED")

    def test_rot_after_attestation_revokes(self):
        did = self.build("sound")
        for item in DATA["claims"]:
            self.call("audit_citation", did, item["id"])
        self.call("derive_verdict", did)
        self.tick(300)
        self.call("attest", did)
        self.serve("rotted")
        self.tick(3600)
        self.assertEqual(self.call("recheck", did, sender=OTHER), "REVOKED")
        self.assertEqual(self.c.get_dossier(did)["last_check"]["missing"], ["visits", "branches"])

    def test_correction_notice_can_overturn_a_cleared_citation(self):
        did = self.build("sound")
        for item in DATA["claims"]:
            self.call("audit_citation", did, item["id"])
        self.call("derive_verdict", did)
        self.call("open_challenge", did, "visits", "SOURCE_CORRECTED", EVIDENCE_URL, DATA["evidence"]["quote"], sender=OTHER)
        RT.llm = lambda p: {"verdict": "SUPPORTS", "challenge": "UPHELD" if "central branch only" in p else "REJECTED", "reason": "x"}
        self.assertEqual(self.call("audit_citation", did, "visits", sender=THIRD), "BLOCK")
        self.assertEqual(self.call("derive_verdict", did), "FLAGGED")


if __name__ == "__main__":
    unittest.main()
