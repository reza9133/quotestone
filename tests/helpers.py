"""Shared fixtures for the behavioral tests: contract loader, scripted web and model, scenario builders."""
import hashlib
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "sim"))

import genlayer as sim  # noqa: E402  (simulator registered under the SDK module name)

RT = sim.RT
CONTRACT_PATH = os.path.join(ROOT, "contracts", "quotestone.py")
OWNER = "0x" + "a1" * 20
OTHER = "0x" + "b2" * 20
THIRD = "0x" + "c3" * 20

DOC_URL = "https://reports.example/transit-review.html"
SRC_A = "https://archive.example/county/response-times-2024.html"
SRC_B = "https://archive.example/county/pilot-enrollment.html"
EVIDENCE = "https://news.example/corrections/response-times.html"

CLAIM_A = "The county cut average emergency response time by 18 percent between 2022 and 2024."
CLAIM_B = "The pilot program enrolled more than 4,000 residents in its first year."
QUOTE_A = "average emergency response time fell by 18 percent between 2022 and 2024 across the county"
QUOTE_B = "the pilot program enrolled 4,120 residents during its first twelve months of operation"


def load_contract():
    spec = importlib.util.spec_from_file_location("quotestone_under_test", CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def page(*paragraphs, title="Page"):
    body = "".join("<p>" + p + "</p>" for p in paragraphs)
    return ("<!doctype html><html><head><title>" + title + "</title><style>p{margin:0}</style>"
            "<script>var tracker = 'ignore this';</script></head><body><main>" + body + "</main></body></html>").encode()


def sha(body):
    return hashlib.sha256(body).hexdigest()


DOC_BODY = page(CLAIM_A, CLAIM_B, "Methodology notes follow in the appendix.", title="Transit review")
SRC_A_BODY = page("Annual operations summary.", "In the audited period, " + QUOTE_A + ", according to dispatch logs.",
                  "Appendix tables are published separately.")
SRC_B_BODY = page("Enrollment figures were reconciled in March.", "Records show " + QUOTE_B + ".", "Closing remarks.")
EVIDENCE_BODY = page("Correction notice published on the county site.",
                     "The dispatch figure for 2024 was recalculated and the reported improvement was overstated by half.")
EVIDENCE_QUOTE = "the reported improvement was overstated by half"


class Base(unittest.TestCase):
    def setUp(self):
        RT.reset()
        self.mod = load_contract()
        self.c = self.mod.Quotestone()
        self.set_pages(DOC_BODY, SRC_A_BODY, SRC_B_BODY)
        RT.pages[EVIDENCE] = (200, EVIDENCE_BODY)
        self.verdicts = {}
        self.challenge_answer = "REJECTED"
        RT.llm = self.llm

    # --- scripted model -------------------------------------------------------------
    def llm(self, prompt):
        has_challenge = "CHALLENGE_KIND" in prompt
        verdict = "SUPPORTS"
        for needle, wanted in self.verdicts.items():
            if needle in prompt:
                verdict = wanted
        answer = self.challenge_answer if has_challenge else "NONE"
        if isinstance(verdict, Exception):
            return verdict
        return {"verdict": verdict, "challenge": answer, "reason": "scripted"}

    # --- world helpers ----------------------------------------------------------------
    def set_pages(self, doc, a, b):
        RT.pages[DOC_URL] = (200, doc)
        RT.pages[SRC_A] = (200, a)
        RT.pages[SRC_B] = (200, b)

    def call(self, name, *args, sender=OWNER):
        RT.sender = sender
        return getattr(self.c, name)(*args)

    def fails(self, name, *args, sender=OWNER, msg=""):
        RT.sender = sender
        with self.assertRaises(sim.UserError) as ctx:
            getattr(self.c, name)(*args)
        self.assertIn(msg, ctx.exception.message)

    def tick(self, seconds):
        RT.time += seconds

    # --- scenario builders ------------------------------------------------------------
    def draft(self, review=600):
        did = self.call("open_dossier", "Transit review", DOC_URL, review)
        self.call("pin_document", did, sha(DOC_BODY))
        return did

    def sealed(self, review=600, second=True):
        did = self.draft(review)
        self.call("add_citation", did, "resp-time", CLAIM_A, SRC_A, QUOTE_A)
        self.call("anchor_citation", did, "resp-time", sha(SRC_A_BODY))
        if second:
            self.call("add_citation", did, "enrollment", CLAIM_B, SRC_B, QUOTE_B)
            self.call("anchor_citation", did, "enrollment", sha(SRC_B_BODY))
        self.call("seal_dossier", did)
        return did

    def audited(self, review=600):
        did = self.sealed(review)
        for cid in self.c.get_dossier(did)["cite_ids"]:
            self.call("audit_citation", did, cid)
        return did

    def cleared(self, review=600):
        did = self.audited(review)
        self.assertEqual(self.call("derive_verdict", did), "CLEARED")
        return did

    def attested(self, review=600):
        did = self.cleared(review)
        self.tick(review)
        self.call("attest", did, sender=THIRD)
        return did

    def state(self, did):
        return self.c.get_dossier(did)["state"]
