import assert from "node:assert/strict";
import { test } from "node:test";

import { apiBase, DEFAULT_API_URL } from "../lib/apiBase.ts";

test("empty or missing value falls back to the local dev API", () => {
  assert.equal(apiBase(undefined), DEFAULT_API_URL);
  assert.equal(apiBase(""), DEFAULT_API_URL);
  assert.equal(apiBase("   "), DEFAULT_API_URL);
});

test("an origin is kept as is", () => {
  assert.equal(apiBase("http://localhost:8000"), "http://localhost:8000");
  assert.equal(apiBase("https://passefiltre.local.cronix.fr"), "https://passefiltre.local.cronix.fr");
});

test("trailing slashes are removed", () => {
  assert.equal(apiBase("https://passefiltre.local.cronix.fr/"), "https://passefiltre.local.cronix.fr");
  assert.equal(apiBase(" https://passefiltre.local.cronix.fr// "), "https://passefiltre.local.cronix.fr");
});

test("a trailing /api is removed so routes never become /api/api/", () => {
  for (const raw of [
    "https://passefiltre.local.cronix.fr/api",
    "https://passefiltre.local.cronix.fr/api/",
    "https://passefiltre.local.cronix.fr/API",
    "https://passefiltre.local.cronix.fr/api/api/",
  ]) {
    const url = apiBase(raw) + "/api/health";
    assert.equal(url, "https://passefiltre.local.cronix.fr/api/health", raw);
    assert.ok(!url.includes("/api/api/"), raw);
  }
});

test("a sub-path deployment is preserved", () => {
  assert.equal(apiBase("https://example.com/passefiltre/api"), "https://example.com/passefiltre");
  assert.equal(apiBase("https://example.com/apiary"), "https://example.com/apiary");
});
