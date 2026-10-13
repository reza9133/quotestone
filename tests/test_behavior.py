"""Lifecycle behavior of the contract on the runtime simulator."""
import unittest

from helpers import (Base, CLAIM_A, CLAIM_B, DOC_BODY, DOC_URL, OTHER, OWNER, QUOTE_A, QUOTE_B, RT, SRC_A, SRC_A_BODY,
                     SRC_B, SRC_B_BODY, THIRD, page, sha, sim)


class DraftingTests(Base):
    def test_identity_view(self):
        ident = self.c.get_protocol_identity()
        self.assertEqual(ident["protocol_id"], "quotestone.citation-ledger.v1")
        self.assertEqual(ident["network"], "studionet")

    def test_open_dossier_validation(self):
        self.fails("open_dossier", "", DOC_URL, 600, msg="title")
        self.fails("open_dossier", "x" * 121, DOC_URL, 600, msg="title")
        self.fails("open_dossier", "ok", "ftp://nope.example/a", 600, msg="document url")
        self.fails("open_dossier", "ok", DOC_URL, 299, msg="review window")
        self.fails("open_dossier", "ok", DOC_URL, 1209601, msg="review window")
        self.assertEqual(self.call("open_dossier", "  spaced   title ", DOC_URL, 300), 1)
        self.assertEqual(self.call("open_dossier", "ok", DOC_URL, 1209600), 2)
        self.assertEqual(self.c.get_dossier(1)["title"], "spaced title")
        self.assertEqual(self.c.get_dossier(1)["owner"], OWNER)

    def test_argument_types_are_enforced(self):
        with self.assertRaises(TypeError):
            self.c.open_dossier("t", DOC_URL, True)
        with self.assertRaises(TypeError):
            self.c.open_dossier("t", DOC_URL, "600")
        with self.assertRaises(TypeError):
            self.c.get_dossier("1")

    def test_pin_document_happy_path(self):
        did = self.call("open_dossier", "t", DOC_URL, 600)
        self.assertEqual(self.call("pin_document", did, sha(DOC_BODY)), sha(DOC_BODY))
        dossier = self.c.get_dossier(did)
        doc = self.c.get_document(did)
        self.assertEqual(dossier["doc_sha256"], sha(DOC_BODY))
        self.assertEqual(dossier["doc_chars"], len(doc["text"]))
        self.assertIn("cut average emergency response time", doc["text"])
        self.assertNotIn("tracker", doc["text"])

    def test_pin_document_rejections(self):
        did = self.call("open_dossier", "t", DOC_URL, 600)
        self.fails("pin_document", did, "0" * 64, msg="verification")
        self.fails("pin_document", did, "xyz", msg="not allowed")
        self.fails("pin_document", did, sha(DOC_BODY), sender=OTHER, msg="owner only")
        self.fails("pin_document", 99, sha(DOC_BODY), msg="not found")
        self.call("pin_document", did, sha(DOC_BODY))
        self.fails("pin_document", did, sha(DOC_BODY), msg="not allowed")

    def test_pin_document_unreachable_and_oversized(self):
        did = self.call("open_dossier", "t", DOC_URL, 600)
        RT.pages[DOC_URL] = (500, b"boom")
        self.fails("pin_document", did, sha(b"boom"), msg="verification")
        RT.pages[DOC_URL] = (200, b"")
        self.fails("pin_document", did, sha(b""), msg="verification")
        big = page("word " * 5000)
        RT.pages[DOC_URL] = (200, big)
        self.fails("pin_document", did, sha(big), msg="verification")
        huge = b"a" * 200001
        RT.pages[DOC_URL] = (200, huge)
        self.fails("pin_document", did, sha(huge), msg="verification")
        del RT.pages[DOC_URL]
        self.fails("pin_document", did, sha(DOC_BODY), msg="verification")
        self.assertEqual(self.c.get_dossier(did)["doc_sha256"], "")
        self.assertEqual(self.c.get_document(did)["text"], "")

    def test_add_citation_rules(self):
        did = self.draft()
        self.fails("add_citation", did, "a", "The sky is green and the grass is blue today.", SRC_A, QUOTE_A, msg="claim not found")
        self.fails("add_citation", did, "a", CLAIM_A, SRC_A, "too short here", msg="quote")
        self.fails("add_citation", did, "a", CLAIM_A, SRC_A, "supercalifragilistic expialidocious", msg="quote too short")
        self.fails("add_citation", did, "a", CLAIM_A, DOC_URL, QUOTE_A, msg="source url")
        self.fails("add_citation", did, "a", CLAIM_A, "mailto:x@y.z", QUOTE_A, msg="source url")
        self.fails("add_citation", did, "A", CLAIM_A, SRC_A, QUOTE_A, msg="citation id")
        self.fails("add_citation", did, "a:b", CLAIM_A, SRC_A, QUOTE_A, msg="citation id")
        self.fails("add_citation", did, "", CLAIM_A, SRC_A, QUOTE_A, msg="citation id")
        self.fails("add_citation", did, "a", "short", SRC_A, QUOTE_A, msg="claim")
        self.fails("add_citation", did, "a", CLAIM_A, SRC_A, QUOTE_A, sender=OTHER, msg="owner only")
        self.call("add_citation", did, "a", CLAIM_A.upper().replace("  ", " "), SRC_A, QUOTE_A)
        self.fails("add_citation", did, "a", CLAIM_B, SRC_B, QUOTE_B, msg="citation id")
        self.assertEqual(self.c.get_dossier(did)["cite_ids"], ["a"])
        self.assertEqual(self.c.get_citation(did, "a")["anchored"], False)

    def test_add_citation_requires_pinned_document_and_draft(self):
        did = self.call("open_dossier", "t", DOC_URL, 600)
        self.fails("add_citation", did, "a", CLAIM_A, SRC_A, QUOTE_A, msg="closed")
        did = self.sealed()
        self.fails("add_citation", did, "z", CLAIM_A, SRC_A, QUOTE_A, msg="closed")

    def test_claim_matching_survives_markup_and_typography(self):
        doc = page("The county said: <em>\u201cresponse times</em> improved <b>greatly</b>\u201d&mdash;officials reported.")
        RT.pages[DOC_URL] = (200, doc)
        did = self.call("open_dossier", "t", DOC_URL, 600)
        self.call("pin_document", did, sha(doc))
        self.call("add_citation", did, "x", '"Response times improved greatly"', SRC_A, QUOTE_A)
        self.fails("add_citation", did, "y", "response times improve greatly", SRC_A, QUOTE_A, msg="claim not found")

    def test_citation_limit(self):
        paragraphs = ["Claim number %d is made with enough words here." % i for i in range(25)]
        doc = page(*paragraphs)
        RT.pages[DOC_URL] = (200, doc)
        did = self.call("open_dossier", "t", DOC_URL, 600)
        self.call("pin_document", did, sha(doc))
        for i in range(24):
            self.call("add_citation", did, "c%d" % i, paragraphs[i], SRC_A, QUOTE_A)
        self.fails("add_citation", did, "c24", paragraphs[24], SRC_A, QUOTE_A, msg="limit")

    def test_anchor_rules(self):
        did = self.draft()
        self.call("add_citation", did, "a", CLAIM_A, SRC_A, QUOTE_A)
        self.fails("anchor_citation", did, "a", "0" * 64, msg="anchoring failed")
        self.fails("anchor_citation", did, "a", sha(SRC_A_BODY), sender=OTHER, msg="owner only")
        self.fails("anchor_citation", did, "nope", sha(SRC_A_BODY), msg="not found")
        self.fails("anchor_citation", did, "a", "bad", msg="not allowed")
        RT.pages[SRC_A] = (200, page("Different text that omits the sentence entirely."))
        self.fails("anchor_citation", did, "a", sha(RT.pages[SRC_A][1]), msg="anchoring failed")
        RT.pages[SRC_A] = (200, SRC_A_BODY)
        self.call("anchor_citation", did, "a", sha(SRC_A_BODY))
        anchor = self.c.get_citation(did, "a")["anchor"]
        self.assertTrue(self.c.get_citation(did, "a")["anchored"])
        self.assertEqual(anchor["source_sha256"], sha(SRC_A_BODY))
        self.assertIn(QUOTE_A, anchor["excerpt"])
        self.assertLessEqual(len(anchor["excerpt"]), 280 * 2 + len(QUOTE_A))
        self.fails("anchor_citation", did, "a", sha(SRC_A_BODY), msg="not allowed")

    def test_anchor_requires_quote_even_when_digest_matches(self):
        did = self.draft()
        self.call("add_citation", did, "a", CLAIM_A, SRC_A, QUOTE_A)
        other = page("A page whose digest the owner committed to but that lacks the quoted sentence.")
        RT.pages[SRC_A] = (200, other)
        self.fails("anchor_citation", did, "a", sha(other), msg="anchoring failed")

    def test_seal_rules(self):
        did = self.draft()
        self.fails("seal_dossier", did, msg="not allowed")
        self.call("add_citation", did, "a", CLAIM_A, SRC_A, QUOTE_A)
        self.fails("seal_dossier", did, msg="anchored")
        self.call("anchor_citation", did, "a", sha(SRC_A_BODY))
        self.fails("seal_dossier", did, sender=OTHER, msg="owner only")
        self.call("seal_dossier", did)
        self.assertEqual(self.state(did), "SEALED")
        self.fails("seal_dossier", did, msg="not allowed")


class AuditTests(Base):
    def test_audit_requires_sealed(self):
        did = self.draft()
        self.fails("audit_citation", did, "x", msg="citation not found")
        self.call("add_citation", did, "a", CLAIM_A, SRC_A, QUOTE_A)
        self.fails("audit_citation", did, "a", msg="audit not allowed")

    def test_supports_everywhere_is_sound(self):
        did = self.sealed()
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=THIRD), "PASS")
        audit = self.c.get_audit(did, "resp-time")
        self.assertEqual(audit["verdict"], "SUPPORTS")
        self.assertTrue(audit["anchor_match"])
        self.assertEqual(audit["attempt"], 1)
        self.assertEqual(audit["source_sha256"], sha(SRC_A_BODY))
        self.call("audit_citation", did, "enrollment", sender=THIRD)
        self.assertEqual(self.call("derive_verdict", did, sender=THIRD), "CLEARED")
        dossier = self.c.get_dossier(did)
        self.assertEqual(dossier["grade"], "SOUND")
        self.assertEqual(dossier["review_deadline"], dossier["clear_at"] + 600)

    def test_partial_is_qualified(self):
        self.verdicts["4,120 residents"] = "PARTIAL"
        did = self.audited()
        self.assertEqual(self.c.get_audit(did, "enrollment")["result"], "WEAK")
        self.assertEqual(self.call("derive_verdict", did), "CLEARED")
        self.assertEqual(self.c.get_dossier(did)["grade"], "QUALIFIED")

    def test_blocking_verdicts_flag_and_lock(self):
        for verdict in ("OVERSTATES", "CONTRADICTS", "UNRELATED"):
            self.setUp()
            self.verdicts["18 percent"] = verdict
            did = self.audited()
            self.assertEqual(self.c.get_audit(did, "resp-time")["result"], "BLOCK")
            self.assertEqual(self.call("derive_verdict", did), "FLAGGED")
            self.fails("audit_citation", did, "resp-time", msg="audit not allowed")
            self.fails("derive_verdict", did, msg="not allowed")

    def test_blocking_result_locks_citation_before_derive(self):
        self.verdicts["18 percent"] = "OVERSTATES"
        did = self.sealed()
        self.call("audit_citation", did, "resp-time")
        self.tick(61)
        self.verdicts.clear()
        self.fails("audit_citation", did, "resp-time", msg="locked")
        self.fails("audit_citation", did, "resp-time", sender=OWNER, msg="locked")

    def test_derive_needs_every_audit(self):
        did = self.sealed()
        self.call("audit_citation", did, "resp-time")
        self.fails("derive_verdict", did, msg="needs an audit")
        self.call("audit_citation", did, "enrollment")
        self.assertEqual(self.call("derive_verdict", did), "CLEARED")
        self.fails("derive_verdict", did, msg="not allowed")

    def test_quote_missing_is_deterministic_and_skips_the_model(self):
        did = self.sealed()
        RT.pages[SRC_A] = (200, page("The page was rewritten and no longer carries the sentence."))
        before = len(RT.prompts)
        self.assertEqual(self.call("audit_citation", did, "resp-time"), "BLOCK")
        self.assertEqual(len(RT.prompts), before)
        self.assertEqual(self.c.get_audit(did, "resp-time")["verdict"], "QUOTE_MISSING")

    def test_unreachable_source_is_unknown_and_retryable(self):
        did = self.sealed()
        RT.pages[SRC_A] = (503, b"down")
        self.assertEqual(self.call("audit_citation", did, "resp-time"), "UNKNOWN")
        self.call("audit_citation", did, "enrollment")
        self.assertEqual(self.call("derive_verdict", did), "INCONCLUSIVE")
        self.fails("audit_citation", did, "resp-time", msg="cooldown")
        self.tick(60)
        RT.pages[SRC_A] = (200, SRC_A_BODY)
        self.fails("audit_citation", did, "resp-time", sender=THIRD, msg="cooldown")
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=OWNER), "PASS")
        self.assertEqual(self.call("derive_verdict", did), "CLEARED")

    def test_third_party_may_retry_unknown_only_after_the_long_gap(self):
        did = self.sealed(second=False)
        RT.pages[SRC_A] = (503, b"down")
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=THIRD), "UNKNOWN")
        self.tick(3599)
        self.fails("audit_citation", did, "resp-time", sender=OTHER, msg="cooldown")
        self.tick(1)
        RT.pages[SRC_A] = (200, SRC_A_BODY)
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=OTHER), "PASS")

    def test_strangers_cannot_exhaust_attempts_during_an_outage(self):
        did = self.sealed(second=False)
        RT.pages[SRC_A] = (503, b"down")
        self.call("audit_citation", did, "resp-time", sender=THIRD)
        for _ in range(10):
            self.tick(61)
            self.fails("audit_citation", did, "resp-time", sender=THIRD, msg="cooldown")
        self.assertEqual(self.c.get_audit(did, "resp-time")["attempt"], 1)

    def test_model_failures_fail_closed(self):
        bad_outputs = [
            {"verdict": "SUPPORTS", "challenge": "NONE"},
            {"verdict": "GREAT", "challenge": "NONE", "reason": "x"},
            {"verdict": "SUPPORTS", "challenge": "UPHELD", "reason": "x"},
            {"verdict": "SUPPORTS", "challenge": "NONE", "reason": 5},
            {"verdict": "SUPPORTS", "challenge": "NONE", "reason": "x", "extra": 1},
            ValueError("model offline"),
        ]
        for bad in bad_outputs:
            self.setUp()
            self.verdicts["18 percent"] = bad if isinstance(bad, Exception) else None
            RT.llm = (lambda p, b=bad: b)
            did = self.sealed(second=False)
            self.assertEqual(self.call("audit_citation", did, "resp-time"), "UNKNOWN", bad)
            self.assertEqual(self.call("derive_verdict", did), "INCONCLUSIVE")

    def test_model_reason_is_bounded_and_cleaned(self):
        RT.llm = lambda p: {"verdict": "SUPPORTS", "challenge": "NONE", "reason": "  long\n" + "z" * 900}
        did = self.sealed(second=False)
        self.call("audit_citation", did, "resp-time")
        reason = self.c.get_audit(did, "resp-time")["reason"]
        self.assertLessEqual(len(reason), 200)
        self.assertNotIn("\n", reason)

    def test_attempt_limit_and_cooldown(self):
        did = self.sealed(second=False)
        RT.pages[SRC_A] = (503, b"down")
        for attempt in range(5):
            self.assertEqual(self.call("audit_citation", did, "resp-time"), "UNKNOWN")
            self.assertEqual(self.c.get_audit(did, "resp-time")["attempt"], attempt + 1)
            if attempt < 4:
                self.fails("audit_citation", did, "resp-time", msg="cooldown")
                self.tick(60)
        self.tick(600)
        self.fails("audit_citation", did, "resp-time", msg="attempt limit")
        self.assertEqual(self.call("derive_verdict", did), "INCONCLUSIVE")
        self.assertEqual(self.state(did), "INCONCLUSIVE")

    def test_third_parties_cannot_reaudit_favorable_results(self):
        did = self.sealed()
        self.call("audit_citation", did, "resp-time", sender=THIRD)
        self.tick(61)
        self.fails("audit_citation", did, "resp-time", sender=THIRD, msg="owner only")
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=OWNER), "PASS")
        self.assertEqual(self.c.get_audit(did, "resp-time")["attempt"], 2)

    def test_owner_reaudit_in_cleared_restarts_review(self):
        did = self.cleared()
        first = self.c.get_dossier(did)
        self.tick(300)
        self.fails("audit_citation", did, "resp-time", sender=THIRD, msg="owner only")
        self.call("audit_citation", did, "resp-time")
        dossier = self.c.get_dossier(did)
        self.assertEqual((dossier["state"], dossier["grade"], dossier["clear_at"], dossier["review_deadline"]), ("SEALED", "", 0, 0))
        self.fails("attest", did, msg="not allowed")
        self.call("derive_verdict", did)
        again = self.c.get_dossier(did)
        self.assertEqual(again["review_deadline"], again["clear_at"] + 600)
        self.assertGreater(again["clear_at"], first["clear_at"])

    def test_derive_is_permissionless_and_pure_function_of_audits(self):
        did = self.audited()
        self.assertEqual(self.call("derive_verdict", did, sender=OTHER), "CLEARED")


class ChallengeTests(Base):
    def challenge(self, did, cid="resp-time", sender=OTHER, kind="SOURCE_CORRECTED"):
        from helpers import EVIDENCE, EVIDENCE_QUOTE
        return self.call("open_challenge", did, cid, kind, EVIDENCE, EVIDENCE_QUOTE, sender=sender)

    def test_open_challenge_rules(self):
        from helpers import EVIDENCE, EVIDENCE_QUOTE
        did = self.audited()
        self.fails("open_challenge", did, "resp-time", "SOURCE_CORRECTED", EVIDENCE, EVIDENCE_QUOTE, msg="not allowed")
        self.call("derive_verdict", did)
        self.fails("open_challenge", did, "resp-time", "SOURCE_CORRECTED", EVIDENCE, EVIDENCE_QUOTE, sender=OWNER, msg="not allowed")
        self.fails("open_challenge", did, "resp-time", "BAD_KIND", EVIDENCE, EVIDENCE_QUOTE, sender=OTHER, msg="invalid")
        self.fails("open_challenge", did, "resp-time", "MISQUOTED", "ftp://x.example/e", EVIDENCE_QUOTE, sender=OTHER, msg="invalid")
        self.fails("open_challenge", did, "resp-time", "MISQUOTED", EVIDENCE, "quote that is nowhere in the page", sender=OTHER, msg="not found")
        self.fails("open_challenge", did, "resp-time", "MISQUOTED", EVIDENCE, "short", sender=OTHER, msg="evidence quote")
        self.fails("open_challenge", did, "resp-time", "MISQUOTED", EVIDENCE, "Correction_notice_published_on_the_county_site.", sender=OTHER, msg="too short")
        self.fails("open_challenge", did, "missing", "MISQUOTED", EVIDENCE, EVIDENCE_QUOTE, sender=OTHER, msg="not found")
        self.assertEqual(self.challenge(did), 1)
        record = self.c.get_challenge(did, 1)
        self.assertEqual((record["cite_id"], record["challenger"], record["resolved"]), ("resp-time", OTHER, False))
        self.assertIn(EVIDENCE_QUOTE, record["excerpt"])
        self.assertEqual(self.state(did), "DISPUTED")
        self.fails("open_challenge", did, "enrollment", "MISQUOTED", EVIDENCE, EVIDENCE_QUOTE, sender=THIRD, msg="not allowed")

    def test_challenge_window_boundary(self):
        did = self.cleared(review=600)
        deadline = self.c.get_dossier(did)["review_deadline"]
        RT.time = deadline
        self.fails("open_challenge", did, "resp-time", "MISQUOTED", "https://news.example/corrections/response-times.html",
                   "the reported improvement was overstated by half", sender=OTHER, msg="not allowed")
        RT.time = deadline - 1
        self.assertEqual(self.challenge(did), 1)

    def test_rejected_challenge_restarts_a_full_window(self):
        did = self.cleared()
        self.tick(590)
        self.challenge(did)
        self.tick(1000)
        self.fails("attest", did, sender=THIRD, msg="not allowed")
        self.fails("audit_citation", did, "enrollment", msg="only the challenged")
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=THIRD), "PASS")
        self.assertEqual(self.state(did), "SEALED")
        self.assertEqual(self.c.get_challenge(did, 1)["resolution"], "REJECTED")
        self.assertEqual(self.call("derive_verdict", did), "CLEARED")
        dossier = self.c.get_dossier(did)
        self.assertEqual(dossier["review_deadline"] - dossier["clear_at"], 600)
        self.assertEqual(dossier["open_challenge"], 0)
        self.fails("attest", did, sender=THIRD, msg="not allowed")
        self.assertEqual(self.challenge(did, sender=THIRD), 2)

    def test_upheld_challenge_flags_dossier(self):
        self.challenge_answer = "UPHELD"
        did = self.cleared()
        self.challenge(did)
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=THIRD), "BLOCK")
        self.assertEqual(self.call("derive_verdict", did), "FLAGGED")
        self.assertEqual(self.c.get_challenge(did, 1)["resolution"], "UPHELD")
        self.assertEqual(self.c.get_audit(did, "resp-time")["challenge_id"], 1)
        self.fails("attest", did, msg="not allowed")

    def test_unresolved_challenge_stays_open_until_attempts_run_out(self):
        self.challenge_answer = "UNRESOLVED"
        did = self.cleared()
        self.challenge(did)
        for _ in range(4):
            self.assertEqual(self.call("audit_citation", did, "resp-time", sender=THIRD), "UNKNOWN")
            self.assertEqual(self.state(did), "DISPUTED")
            self.assertFalse(self.c.get_challenge(did, 1)["resolved"])
            self.fails("audit_citation", did, "resp-time", sender=OWNER, msg="cooldown")
            self.tick(3600)
        self.assertEqual(self.call("audit_citation", did, "resp-time", sender=THIRD), "UNKNOWN")
        self.assertTrue(self.c.get_challenge(did, 1)["resolved"])
        self.assertEqual(self.c.get_challenge(did, 1)["tries"], 5)
        self.assertEqual(self.call("derive_verdict", did), "INCONCLUSIVE")
        self.assertEqual(self.c.get_audit(did, "resp-time")["attempt"], 1)

    def test_many_challenges_on_one_citation_never_exhaust_its_audit_budget(self):
        did = self.cleared()
        for n in range(1, 6):
            self.assertEqual(self.challenge(did, sender=THIRD), n)
            self.assertEqual(self.call("audit_citation", did, "resp-time", sender=OTHER), "PASS")
            self.assertEqual(self.call("derive_verdict", did), "CLEARED")
            self.tick(60)
        self.assertEqual(self.c.get_audit(did, "resp-time")["attempt"], 1)
        self.assertEqual(self.state(did), "CLEARED")
        self.tick(600)
        self.call("attest", did, sender=THIRD)

    def test_unreadable_source_leaves_challenge_open(self):
        did = self.cleared()
        self.challenge(did)
        RT.pages[SRC_A] = (503, b"down")
        self.assertEqual(self.call("audit_citation", did, "resp-time"), "UNKNOWN")
        self.assertEqual(self.state(did), "DISPUTED")
        self.assertFalse(self.c.get_challenge(did, 1)["resolved"])

    def test_missing_quote_during_challenge_is_moot_and_blocking(self):
        did = self.cleared()
        self.challenge(did)
        RT.pages[SRC_A] = (200, page("Rewritten page without the original sentence at all."))
        self.assertEqual(self.call("audit_citation", did, "resp-time"), "BLOCK")
        self.assertEqual(self.c.get_challenge(did, 1)["resolution"], "MOOT")
        self.assertEqual(self.call("derive_verdict", did), "FLAGGED")

    def test_challenge_limit(self):
        did = self.cleared()
        for n in (1, 2, 3, 4, 5):
            self.assertEqual(self.challenge(did, sender=THIRD), n)
            self.tick(60)
            self.call("audit_citation", did, "resp-time", sender=THIRD)
            self.call("derive_verdict", did)
        from helpers import EVIDENCE, EVIDENCE_QUOTE
        self.fails("open_challenge", did, "resp-time", "MISQUOTED", EVIDENCE, EVIDENCE_QUOTE, sender=OTHER, msg="limit")

    def test_challenge_prompt_carries_evidence_and_kind(self):
        did = self.cleared()
        self.challenge(did, kind="CONTEXT_OMITTED")
        self.call("audit_citation", did, "resp-time")
        prompt = RT.prompts[-1]
        self.assertIn("CHALLENGE_KIND: CONTEXT_OMITTED", prompt)
        self.assertIn("overstated by half", prompt)


class AttestationTests(Base):
    def test_attest_timing_and_record(self):
        did = self.cleared(review=600)
        self.fails("attest", did, sender=THIRD, msg="not allowed")
        self.tick(599)
        self.fails("attest", did, sender=THIRD, msg="not allowed")
        self.tick(1)
        digest = self.call("attest", did, sender=THIRD)
        record = self.c.get_attestation(did)["record"]
        self.assertEqual(record["attestation_digest"], digest)
        self.assertEqual(record["grade"], "SOUND")
        self.assertEqual(record["document_sha256"], sha(DOC_BODY))
        self.assertEqual([r["cite_id"] for r in record["rows"]], ["resp-time", "enrollment"])
        self.assertEqual(record["rows"][0]["source_sha256"], sha(SRC_A_BODY))
        self.assertEqual(record["rows"][0]["audit_digest"], self.c.get_audit(did, "resp-time")["audit_digest"])
        self.assertEqual(self.state(did), "ATTESTED")
        self.assertEqual(self.c.get_attestation(did)["status"], "ATTESTED")
        self.fails("attest", did, msg="not allowed")

    def test_attest_fails_when_document_changes(self):
        did = self.cleared()
        self.tick(600)
        RT.pages[DOC_URL] = (200, DOC_BODY + b"<!-- trailing edit -->x")
        self.fails("attest", did, msg="freshness")
        RT.pages[DOC_URL] = (200, page("The claims were removed from the document."))
        self.fails("attest", did, msg="freshness")
        RT.pages[DOC_URL] = (200, DOC_BODY)
        self.call("attest", did)

    def test_attest_fails_when_source_context_changes(self):
        did = self.cleared()
        self.tick(600)
        RT.pages[SRC_A] = (200, page("Correction: it was later found that, " + QUOTE_A + ", was based on a faulty export."))
        self.fails("attest", did, msg="freshness")
        self.assertEqual(self.state(did), "CLEARED")

    def test_attest_fails_when_quote_disappears_or_source_down(self):
        did = self.cleared()
        self.tick(600)
        RT.pages[SRC_B] = (200, page("Entirely different content now."))
        self.fails("attest", did, msg="freshness")
        RT.pages[SRC_B] = (404, b"gone")
        self.fails("attest", did, msg="freshness")

    def test_attest_requires_cleared(self):
        did = self.audited()
        self.fails("attest", did, msg="not allowed")
        self.fails("attest", 12345, msg="not found")

    def test_no_attestation_view_before_attest(self):
        did = self.cleared()
        self.assertEqual(self.c.get_attestation(did), {})


class RecheckTests(Base):
    def test_gap_and_intact(self):
        did = self.attested()
        self.fails("recheck", did, msg="not allowed")
        self.tick(3599)
        self.fails("recheck", did, msg="not allowed")
        self.tick(1)
        self.assertEqual(self.call("recheck", did, sender=THIRD), "INTACT")
        dossier = self.c.get_dossier(did)
        self.assertEqual((dossier["check_count"], dossier["state"]), (1, "ATTESTED"))
        self.assertEqual(dossier["last_check"]["outcome"], "INTACT")
        self.fails("recheck", did, msg="not allowed")

    def test_quote_removed_revokes(self):
        did = self.attested()
        self.tick(3600)
        RT.pages[SRC_B] = (200, page("The sentence was quietly deleted from this page."))
        self.assertEqual(self.call("recheck", did, sender=THIRD), "REVOKED")
        dossier = self.c.get_dossier(did)
        self.assertEqual((dossier["state"], dossier["last_check"]["missing"]), ("REVOKED", ["enrollment"]))
        self.assertGreater(dossier["revoked_at"], 0)
        self.assertEqual(self.c.get_attestation(did)["status"], "REVOKED")
        self.tick(3600)
        self.fails("recheck", did, msg="not allowed")
        self.fails("attest", did, msg="not allowed")

    def test_claim_removed_from_document_revokes(self):
        did = self.attested()
        self.tick(3600)
        RT.pages[DOC_URL] = (200, page(CLAIM_A, "The second statement was withdrawn."))
        self.assertEqual(self.call("recheck", did), "REVOKED")
        self.assertEqual(self.c.get_dossier(did)["last_check"]["document_state"], "MISSING")

    def test_outage_is_unverified_not_revoked(self):
        did = self.attested()
        self.tick(3600)
        RT.pages[SRC_A] = (503, b"down")
        self.assertEqual(self.call("recheck", did), "UNVERIFIED")
        self.assertEqual(self.state(did), "ATTESTED")
        self.assertEqual(self.c.get_dossier(did)["last_check"]["unreachable"], ["resp-time"])
        self.tick(3600)
        RT.pages[SRC_A] = (200, SRC_A_BODY)
        RT.pages[DOC_URL] = (500, b"down")
        self.assertEqual(self.call("recheck", did), "UNVERIFIED")
        self.tick(3600)
        RT.pages[DOC_URL] = (200, DOC_BODY)
        self.assertEqual(self.call("recheck", did), "INTACT")

    def test_missing_wins_over_outage(self):
        did = self.attested()
        self.tick(3600)
        RT.pages[SRC_A] = (503, b"down")
        RT.pages[SRC_B] = (200, page("Quote deleted."))
        self.assertEqual(self.call("recheck", did), "REVOKED")

    def test_context_drift_is_reported_without_revocation(self):
        did = self.attested()
        self.tick(3600)
        RT.pages[SRC_A] = (200, page("New preface paragraph.", "Also " + QUOTE_A + " but with new surrounding context."))
        self.assertEqual(self.call("recheck", did), "DRIFTED")
        self.assertEqual(self.c.get_dossier(did)["last_check"]["drifted"], ["resp-time"])
        self.assertEqual(self.state(did), "ATTESTED")
        self.tick(3600)
        RT.pages[SRC_A] = (200, SRC_A_BODY)
        RT.pages[DOC_URL] = (200, DOC_BODY + b" ")
        self.assertEqual(self.call("recheck", did), "DRIFTED")
        self.assertFalse(self.c.get_dossier(did)["last_check"]["document_unchanged"])

    def test_recheck_requires_attested(self):
        did = self.cleared()
        self.fails("recheck", did, msg="not allowed")


class ViewTests(Base):
    def test_unknown_ids(self):
        self.fails("get_dossier", 1, msg="not found")
        self.fails("get_dossier", 0, msg="not found")
        self.fails("get_dossier", -3, msg="not found")
        did = self.draft()
        self.fails("get_citation", did, "nope", msg="not found")
        self.assertEqual(self.c.get_audit(did, "nope"), {})
        self.assertEqual(self.c.get_challenge(did, 9), {})

    def test_list_dossiers_paging(self):
        for i in range(5):
            self.call("open_dossier", "t%d" % i, DOC_URL, 600)
        self.assertEqual([d["id"] for d in self.c.list_dossiers(0, 3)], [1, 2, 3])
        self.assertEqual([d["id"] for d in self.c.list_dossiers(3, 10)], [4, 5])
        self.assertEqual(self.c.list_dossiers(9, 3), [])
        self.assertEqual(self.c.list_dossiers(-4, 2)[0]["id"], 1)
        self.assertEqual(self.c.list_dossiers(0, 0), [])
        self.assertEqual(self.c.list_dossiers(0, -1), [])
        self.assertLessEqual(len(self.c.list_dossiers(0, 1000)), 40)

    def test_event_log_is_ordered_and_wraps(self):
        did = self.attested()
        kinds = [e["kind"] for e in self.c.get_events(0, 40)]
        self.assertEqual(kinds[:3], ["DOSSIER_OPENED", "DOCUMENT_PINNED", "CITATION_ADDED"])
        self.assertEqual(kinds[-1], "ATTESTED")
        for _ in range(300):
            self.call("open_dossier", "filler", DOC_URL, 600)
        total = int(self.c.event_count) if hasattr(self.c, "event_count") else None
        events = self.c.get_events(0, 40)
        self.assertEqual(len(events), 40)
        self.assertEqual(events[0]["index"], total - 256)
        self.assertEqual([e["index"] for e in events], list(range(total - 256, total - 216)))
        tail = self.c.get_events(total - 5, 40)
        self.assertEqual([e["index"] for e in tail], list(range(total - 5, total)))
        self.assertEqual(self.c.get_events(total + 10, 5), [])

    def test_views_cannot_write(self):
        did = self.draft()
        before = self.c.get_dossier(did)
        self.c.list_dossiers(0, 5)
        self.assertEqual(self.c.get_dossier(did), before)


if __name__ == "__main__":
    unittest.main()
