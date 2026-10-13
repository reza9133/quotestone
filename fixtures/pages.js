"use strict";
const crypto = require("crypto");

const DOCUMENT = {
  path: "/review.html",
  body: '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Library Annual Review 2025</title></head><body><main>' +
    "<h1>Library Annual Review 2025</h1>" +
    "<p>Public library visits rose by 12 percent in 2025 compared with 2024.</p>" +
    "<p>The city opened four new branch locations during 2025.</p>" +
    "<p>Opening hours are listed on each branch page.</p></main></body></html>",
};

const CLAIMS = [
  { id: "visits", claim: "Public library visits rose by 12 percent in 2025 compared with 2024.",
    path: "/sources/visits.html", quote: "visits rose by 12 percent in 2025 compared with 2024" },
  { id: "branches", claim: "The city opened four new branch locations during 2025.",
    path: "/sources/branches.html", quote: "opened four new branch locations during 2025" },
];

const EVIDENCE = {
  path: "/corrections/visits.html",
  quote: "the 12 percent visit figure applied to the central branch only",
  body: '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Correction notice</title></head><body><main>' +
    "<h1>Correction notice</h1><p>After an audit of the counting method, the library clarified that " +
    "the 12 percent visit figure applied to the central branch only and not to the whole system.</p></main></body></html>",
};

function source(title, paragraphs) {
  return '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>' + title + "</title></head><body><main><h1>" +
    title + "</h1>" + paragraphs.map((p) => "<p>" + p + "</p>").join("") + "</main></body></html>";
}

// One page set per mode. "sound": sources back the claims. "overstated": same quotes, but the surrounding text
// narrows what they cover. "rotted": the quoted sentences were removed after publication.
const MODES = {
  sound: {
    "/sources/visits.html": source("Circulation and visits", [
      "Counts were collected by door sensors at every branch throughout the year.",
      "Across the whole system, total visits rose by 12 percent in 2025 compared with 2024, based on the sensor logs.",
    ]),
    "/sources/branches.html": source("Branch expansion", [
      "Council minutes record that the city opened four new branch locations during 2025 as part of the expansion plan.",
      "Each branch follows the standard opening hours.",
    ]),
  },
  overstated: {
    "/sources/visits.html": source("Circulation and visits", [
      "These are provisional numbers for the central branch alone; other branches have not reported yet.",
      "At the central branch, visits rose by 12 percent in 2025 compared with 2024, subject to revision.",
    ]),
    "/sources/branches.html": source("Branch expansion", [
      "Council minutes record that the city opened four new branch locations during 2025 as part of the expansion plan.",
      "Each branch follows the standard opening hours.",
    ]),
  },
  rotted: {
    "/sources/visits.html": source("Circulation and visits", ["This page was reorganized and the earlier figures were archived."]),
    "/sources/branches.html": source("Branch expansion", ["Council minutes record the expansion plan and its budget."]),
  },
};

function sha256(text) {
  return crypto.createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
}

function lookup(mode, path) {
  if (path === DOCUMENT.path) return DOCUMENT.body;
  if (path === EVIDENCE.path) return EVIDENCE.body;
  const set = MODES[mode] || MODES.sound;
  return Object.prototype.hasOwnProperty.call(set, path) ? set[path] : null;
}

function digests(mode) {
  const out = { document: sha256(DOCUMENT.body), evidence: sha256(EVIDENCE.body), sources: {} };
  for (const item of CLAIMS) out.sources[item.id] = sha256(lookup(mode, item.path));
  return out;
}

module.exports = { DOCUMENT, CLAIMS, EVIDENCE, MODES, lookup, digests, sha256 };
