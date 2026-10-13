"use strict";
const { lookup, digests } = require("../pages");

// Deploy the same function once per scenario and set MODE to sound, overstated or rotted.
module.exports = (req, res) => {
  const mode = process.env.MODE || "sound";
  const path = (req.url || "/").split("?")[0];
  res.setHeader("cache-control", "public, max-age=0, must-revalidate");
  if (path === "/digests.json") {
    res.setHeader("content-type", "application/json; charset=utf-8");
    return res.status(200).send(JSON.stringify({ mode, ...digests(mode) }));
  }
  const body = lookup(mode, path);
  if (body === null) {
    res.setHeader("content-type", "text/plain; charset=utf-8");
    return res.status(404).send("not found");
  }
  res.setHeader("content-type", "text/html; charset=utf-8");
  return res.status(200).send(body);
};
