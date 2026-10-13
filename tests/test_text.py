"""Unit tests for the pure helpers: clock parsing, text folding, quote matching."""
import datetime
import unittest

from helpers import RT, load_contract, sim


class ClockTests(unittest.TestCase):
    def setUp(self):
        RT.reset()
        self.mod = load_contract()

    def check(self, formatter, epoch):
        RT.time = epoch
        RT.time_format = formatter
        self.assertEqual(self.mod._now(), epoch)

    def test_matches_python_for_many_instants(self):
        for epoch in (0, 951782400, 1709164799, 1709164800, 1780000000, 1800000000, 4102444799, 4102444800):
            iso = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.check(iso, epoch)

    def test_fraction_digits_and_space_separator(self):
        stamp = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + ".123456789Z"
        self.check(stamp, 1780000123)

    def test_numeric_offsets(self):
        base = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        self.check(lambda t: (base(t) + datetime.timedelta(hours=3, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S") + "+03:30", 1780000000)
        self.check(lambda t: (base(t) - datetime.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S") + "-0500", 1780000000)

    def test_leap_day_and_year_boundaries(self):
        for text, epoch in (("2024-02-29T23:59:59Z", 1709251199), ("2024-03-01T00:00:00Z", 1709251200),
                            ("2025-12-31T23:59:59Z", 1767225599), ("2026-01-01T00:00:00Z", 1767225600),
                            ("2000-02-29T12:00:00Z", 951825600), ("1970-01-01T00:00:00Z", 0)):
            RT.time_format = lambda t, text=text: text
            self.assertEqual(self.mod._now(), epoch, text)

    def test_garbage_clock_is_rejected(self):
        RT.time_format = lambda t: "not a time"
        with self.assertRaises(sim.UserError):
            self.mod._now()


class TextTests(unittest.TestCase):
    def setUp(self):
        RT.reset()
        self.m = load_contract()

    def test_markup_is_reduced_to_visible_text(self):
        html = ("<html><head><title>T</title><style>.x{color:red}</style><script>alert('hi <b>')</script></head>"
                "<body><!-- hidden note --><h1>Big   Title</h1><p>Un<b>believ</b>able &amp; true&nbsp;facts</p>"
                "<noscript>enable js</noscript></body></html>")
        text = self.m._plain(html)
        self.assertEqual(text, "t big title unbelievable & true facts")
        self.assertNotIn("alert", text)
        self.assertNotIn("hidden", text)
        self.assertNotIn("enable js", text)

    def test_entities_numeric_named_and_hostile(self):
        self.assertEqual(self.m._plain("a&#65;&#x42;c &lt;i&gt; &unknown; &#0; &#xD800; &#99999999;"),
                         "aabc <i> &unknown; &#99999999;")
        self.assertEqual(self.m._plain("&#xD800;&#0;x"), "x")

    def test_typography_folding(self):
        self.assertEqual(self.m._norm("\u201cIt\u2019s\u201d \u2013 a\u200b b\u00a0c\u2026"), '"it\'s" - a b c...')
        self.assertEqual(self.m._norm("  Mixed\tCASE \n text "), "mixed case text")

    def test_plain_text_with_less_than_is_not_mangled(self):
        self.assertEqual(self.m._plain("if a < b and c > d then stop"), "if a < b and c > d then stop")

    def test_hostile_markup_is_processed_in_bounded_time(self):
        import time
        for body in ("<script>" * 20000, "<script " * 20000, "<a " * 60000, "<b " * 60000, "<!--" * 50000,
                     "<style>" * 20000 + "</style>" * 20000, "&#65;" * 30000):
            started = time.time()
            self.m._plain(body[:200000])
            self.assertLess(time.time() - started, 5, body[:12])

    def test_blocks_and_comments_are_removed_cleanly(self):
        html = "a<SCRIPT type='x'>1</SCRIPT >b<style>x</style>c<!-- gone -->d<template><p>t</p></template>e<!-- open"
        self.assertEqual(self.m._plain(html), "a b c d e")

    def test_unclosed_script_hides_the_rest_like_a_browser_would(self):
        self.assertEqual(self.m._plain("before<script>var a = 1;<p>hidden</p>"), "before")

    def test_find_requires_whole_words(self):
        find = self.m._find
        self.assertEqual(find("the drug is safe only for adults", "drug is safe"), 4)
        self.assertEqual(find("they decrease it", "increase it"), -1)
        self.assertEqual(find("a decrease it is", "crease it"), -1)
        self.assertEqual(find("x increase it. y", "increase it"), 2)
        self.assertEqual(find("abc", ""), -1)
        self.assertEqual(find("misfire fire engine", "fire engine"), 8)

    def test_find_with_punctuation_edges(self):
        self.assertEqual(self.m._find('he said "stop right there" loudly', '"stop right there"'), 8)
        self.assertEqual(self.m._find("rates rose 3.5%", "rose 3.5%"), 6)

    def test_excerpt_window_is_bounded(self):
        text = "x" * 1000 + " needle words here " + "y" * 1000
        index = self.m._find(text, "needle words here")
        self.assertEqual(index, 1001)
        excerpt = self.m._excerpt(text, index, 17)
        self.assertEqual(len(excerpt), 280 + 17 + 280)
        self.assertEqual(self.m._excerpt("short needle", 6, 6), "short needle")

    def test_same_ignores_only_named_keys(self):
        same = self.m._same
        self.assertTrue(same({"a": 1, "r": "x"}, {"a": 1, "r": "y"}, ("r",)))
        self.assertFalse(same({"a": 1, "r": "x"}, {"a": 2, "r": "x"}, ("r",)))
        self.assertFalse(same({"a": 1}, {"a": 1, "b": 2}))
        self.assertFalse(same([1], [1]))

    def test_digest_is_canonical(self):
        self.assertEqual(self.m._digest({"b": 1, "a": [1, 2]}), self.m._digest({"a": [1, 2], "b": 1}))
        self.assertNotEqual(self.m._digest({"a": 1}), self.m._digest({"a": "1"}))

    def test_url_validation(self):
        ok, bad = self.m._url_ok, [
            "ftp://x.example/a", "https://user@x.example/a", "https://", "http:/x.example", "https://x.example/a b",
            "https://x.example/" + "a" * 1100, "", 5, None, "javascript:alert(1)", "https://x.example/<script>"]
        self.assertTrue(ok("https://x.example/a?b=1#c"))
        self.assertTrue(ok("http://x.example"))
        for value in bad:
            self.assertFalse(ok(value), value)


if __name__ == "__main__":
    unittest.main()
