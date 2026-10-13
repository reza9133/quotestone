"use strict";
const { CLAIMS, DOCUMENT, EVIDENCE, MODES, lookup, digests } = require("./pages");

// Usage: node fixtures/digests.js [--json]
// Prints the SHA-256 commitments needed by pin_document and anchor_citation for each scenario.
if (process.argv.includes("--json")) {
  const dump = { document: { path: DOCUMENT.path, body: DOCUMENT.body }, evidence: EVIDENCE, claims: CLAIMS, modes: {} };
  for (const mode of Object.keys(MODES)) {
    dump.modes[mode] = { digests: digests(mode), bodies: Object.fromEntries(CLAIMS.map((c) => [c.id, lookup(mode, c.path)])) };
  }
  process.stdout.write(JSON.stringify(dump));
} else {
  for (const mode of Object.keys(MODES)) {
    const d = digests(mode);
    console.log("[" + mode + "]");
    console.log("  document  " + d.document);
    for (const item of CLAIMS) console.log("  " + item.id.padEnd(9) + " " + d.sources[item.id]);
  }
  console.log("[evidence]\n  correction " + digests("sound").evidence);
}
