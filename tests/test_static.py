"""Static checks on the contract source: structure, API surface, determinism and non-deterministic-block hygiene."""
import ast
import os
import unittest

from helpers import ROOT

SOURCE = os.path.join(ROOT, "contracts", "quotestone.py")


def read(mode="r"):
    with open(SOURCE, mode, **({"encoding": "utf-8"} if mode == "r" else {})) as handle:
        return handle.read()


TREE = ast.parse(read())
CLASS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "Quotestone")
METHODS = {n.name: n for n in CLASS.body if isinstance(n, ast.FunctionDef)}
FUNCTIONS = {n.name: n for n in TREE.body if isinstance(n, ast.FunctionDef)}

WRITES = ["open_dossier", "pin_document", "add_citation", "anchor_citation", "seal_dossier", "audit_citation",
          "derive_verdict", "open_challenge", "attest", "recheck"]
VIEWS = ["get_protocol_identity", "get_dossier", "get_document", "get_citation", "get_audit", "get_challenge",
         "get_attestation", "list_dossiers", "get_events"]
PURE_HELPERS = ["_load", "_audit_source", "_recheck_all", "_audit_prompt", "_classify", "_find", "_excerpt", "_plain",
                "_strip_blocks", "_labels_ok", "_fold_audit", "_norm", "_fence", "_same", "_text_digest", "_digest", "_dumps", "_entity"]


def decorator_name(node):
    target = node.decorator_list[0] if node.decorator_list else None
    return ast.unparse(target) if target is not None else ""


def names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


class StructureTests(unittest.TestCase):
    def test_dependency_header_is_first_line(self):
        first = read().splitlines()[0]
        self.assertTrue(first.startswith('# { "Depends": "py-genlayer:'))

    def test_storage_layout(self):
        fields = {n.target.id: ast.unparse(n.annotation) for n in CLASS.body if isinstance(n, ast.AnnAssign)}
        self.assertEqual(fields, {
            "dossier_count": "u256", "event_count": "u256", "dossiers": "TreeMap[str, str]",
            "documents": "TreeMap[str, str]", "citations": "TreeMap[str, str]", "audits": "TreeMap[str, str]",
            "challenges": "TreeMap[str, str]", "attestations": "TreeMap[str, str]", "events": "TreeMap[str, str]"})

    def test_public_surface_is_exactly_the_documented_one(self):
        public = {n for n, f in METHODS.items() if f.decorator_list}
        self.assertEqual(public, set(WRITES + VIEWS))
        for name in WRITES:
            self.assertEqual(decorator_name(METHODS[name]), "gl.public.write", name)
        for name in VIEWS:
            self.assertEqual(decorator_name(METHODS[name]), "gl.public.view", name)

    def test_every_public_method_is_fully_annotated(self):
        for name in WRITES + VIEWS:
            fn = METHODS[name]
            self.assertIsNotNone(fn.returns, name)
            for arg in fn.args.args[1:]:
                self.assertIsNotNone(arg.annotation, name + "." + arg.arg)

    def test_views_never_assign_storage(self):
        for name in VIEWS:
            for node in ast.walk(METHODS[name]):
                if isinstance(node, (ast.Assign, ast.AugAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        self.assertFalse(ast.unparse(target).startswith("self."), name)
            calls = {ast.unparse(n.func) for n in ast.walk(METHODS[name]) if isinstance(n, ast.Call)}
            self.assertFalse({"self._put", "self._emit", "self._put_citation"} & calls, name)

    def test_imports_are_limited(self):
        imported = set()
        for node in TREE.body:
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(imported, {"genlayer", "json", "re", "hashlib"})


class DeterminismTests(unittest.TestCase):
    def test_no_wall_clock_randomness_or_floats(self):
        text = read()
        for banned in ("datetime", "time.time", "random", "uuid", "os.", "sys."):
            self.assertNotIn(banned, text.replace('"datetime"', ""), banned)
        for node in ast.walk(TREE):
            if isinstance(node, ast.Constant):
                self.assertNotIsInstance(node.value, float)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ("float", "frozenset", "open", "print", "input", "eval", "exec"))

    def test_clock_comes_from_the_message_only(self):
        text = read()
        self.assertEqual(text.count('gl.message_raw["datetime"]'), 1)

    def test_nondeterministic_blocks_do_not_touch_storage_or_message(self):
        for fn in METHODS.values():
            for node in ast.walk(fn):
                if isinstance(node, ast.FunctionDef) and node.name == "leader":
                    self.assertNotIn("self", names_in(node), fn.name)
                    self.assertFalse({"_now", "_caller"} & names_in(node), fn.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_agree":
                    for arg in node.args:
                        if isinstance(arg, ast.Lambda):
                            self.assertNotIn("self", names_in(arg), fn.name)
                            self.assertFalse({"_now", "_caller"} & names_in(arg), fn.name)

    def test_pure_helpers_never_reach_storage_or_message(self):
        for name in PURE_HELPERS:
            body = FUNCTIONS[name]
            self.assertNotIn("self", names_in(body), name)
            self.assertFalse({"_now", "_caller"} & names_in(body), name)
            for node in ast.walk(body):
                if isinstance(node, ast.Attribute) and ast.unparse(node).startswith("gl.message"):
                    self.fail(name + " reads message context")

    def test_every_consensus_call_goes_through_the_validator_wrapper(self):
        text = read()
        self.assertEqual(text.count("gl.vm.run_nondet_unsafe("), 1)
        agree_calls = sum(1 for n in ast.walk(TREE) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_agree")
        self.assertEqual(agree_calls, 6)
        self.assertIn("isinstance(result, gl.vm.Return)", text)

    def test_web_and_model_access_only_in_pure_helpers(self):
        for name, fn in list(FUNCTIONS.items()) + list(METHODS.items()):
            uses = {ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.Attribute) and ast.unparse(n).startswith("gl.nondet")}
            if uses:
                self.assertIn(name, ("_load", "_audit_source"), name)


class HygieneTests(unittest.TestCase):
    ARABIC_SCRIPT = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))

    def test_repository_text_is_free_of_arabic_script(self):
        skipped = {".git", "__pycache__", "node_modules"}
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in skipped]
            for name in files:
                if name.endswith((".pyc", ".zip")):
                    continue
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    for number, line in enumerate(handle, 1):
                        for char in line:
                            code = ord(char)
                            self.assertFalse(any(lo <= code <= hi for lo, hi in self.ARABIC_SCRIPT),
                                             "%s:%d contains Arabic-script text" % (name, number))

    def test_contract_source_is_ascii(self):
        raw = read("rb")
        raw.decode("ascii")


if __name__ == "__main__":
    unittest.main()
