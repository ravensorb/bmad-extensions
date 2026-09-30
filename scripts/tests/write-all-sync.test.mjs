// The gate scripts' report writer: the helper's behaviour, and the rule that every gate uses it.
//
// The bug is in scripts/write-all-sync.mjs's header. What is here is the guard, in two halves,
// because each is worthless alone: a behavioural test proves the helper delivers every byte,
// and a structural test proves the reporters still CALL it. `check-docs.mjs` had the helper and
// was one edit away from not using it.
//
// SCOPE IS DERIVED. The structural half globs `scripts/check-*.mjs` rather than listing the
// five that exist today, because the file this exists to protect is the sixth one -- written
// later, by someone reaching for `console.error` because that is what printing looks like. A
// list would have to be updated by exactly the person who did not know the rule.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const HELPER = path.join(REPO, "scripts", "write-all-sync.mjs");
const PREFIX = `${path.basename(REPO)}-write-all-sync-`;

function gateScripts() {
  return fs.readdirSync(path.join(REPO, "scripts"))
    .filter((f) => /^check-.*\.mjs$/.test(f))
    .sort();
}

// A line is code if it is not a `//` comment. Every structural assertion below runs over code
// only: these files DOCUMENT the banned pattern in prose ("never a console.error loop"), and a
// naive scan reads the warning as the violation. That is not hypothetical -- the equivalent
// assertion in check-docs.test.mjs failed on the commit that introduced it, for this reason.
function codeOf(file) {
  return fs.readFileSync(path.join(REPO, "scripts", file), "utf8")
    .split("\n")
    .filter((l) => !/^\s*\/\//.test(l))
    .join("\n");
}

const PROBE = `
import { writeAllSync } from ${JSON.stringify(HELPER)};
const line = "x".repeat(99) + "\\n";
const n = Number(process.argv[2]);
if (process.argv[3] === "console") { for (let i = 0; i < n; i++) console.error(line); }
else writeAllSync(2, line.repeat(n));
process.exit(1);
`;

function probe(t, lines, mode) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), PREFIX));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const p = path.join(dir, "probe.mjs");
  fs.writeFileSync(p, PROBE);
  return spawnSync(process.execPath, [p, String(lines), mode],
                   { cwd: REPO, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
}

test("writeAllSync delivers every byte where a console.error loop loses most of them", (t) => {
  // 5000 lines x 100 B = 488 KB. Chosen from the measured curve in the helper's header: the
  // console loop truncated 20/20 at this size with as little as 3% delivered, so the canary
  // below is deterministic rather than a coin flip. At 100 lines NEITHER shape truncates, and
  // a test written there would pass against the bug.
  const LINES = 5000;
  const want = LINES * 100;

  const canary = probe(t, LINES, "console");
  assert.notEqual(Buffer.byteLength(canary.stderr, "utf8"), want,
    "console.error + process.exit() delivered all 488 KB, so this machine cannot show the " +
    "truncation this test exists to rule out -- the assertion below would prove nothing here");

  // Twenty runs, not one. The failure guarded against is a race, and one green run of a race is
  // not evidence.
  for (let i = 0; i < 20; i++) {
    assert.equal(Buffer.byteLength(probe(t, LINES, "writeAll").stderr, "utf8"), want,
                 `writeAllSync lost bytes on run ${i}`);
  }
});

test("every check-*.mjs gate reports through writeAllSync, not console.error", () => {
  const scripts = gateScripts();
  // Anchored outside the glob: if the glob ever matches nothing -- a rename, a move to a
  // subdirectory -- this suite would pass over an empty set and report success having checked
  // nothing, which is the failure mode these gates exist to catch.
  assert.ok(scripts.length >= 5,
    `expected at least 5 check-*.mjs gates, found ${scripts.length}: a glob that matches ` +
    `nothing makes every assertion below vacuous`);

  for (const file of scripts) {
    const code = codeOf(file);
    assert.doesNotMatch(code, /console\.error/,
      `${file} reports through console.error, which is asynchronous over a pipe and loses ` +
      `output when the process exits. Build one string and call writeAllSync instead.`);
    assert.match(code, /writeAllSync/,
      `${file} never calls writeAllSync -- if it has nothing to report it does not belong ` +
      `in scripts/check-*.mjs, and if it does, it must report through the helper.`);
  }
});

test("a gate that calls process.exit does so only after a completed writeAllSync", () => {
  // `process.exit()` is not banned outright: it is safe once every byte is already on the fd,
  // and two gates need it because they exit from inside control flow whose callers would
  // otherwise fall through into code assuming the check passed. What IS banned is reaching it
  // with output still queued. So: any process.exit must be preceded by a writeAllSync.
  for (const file of gateScripts()) {
    const lines = codeOf(file).split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (!/process\.exit\(/.test(lines[i])) continue;
      const before = lines.slice(Math.max(0, i - 6), i).join("\n");
      assert.match(before, /writeAllSync/,
        `${file}:${i + 1} calls process.exit() with no writeAllSync in the six lines above ` +
        `it. Anything still queued on stdout/stderr is discarded there, silently.`);
    }
  }
});

test("the helper retries EAGAIN rather than treating it as a short write", () => {
  // A non-blocking fd can refuse a write outright. Dropping the retry makes writeAllSync
  // truncate exactly as silently as the race it replaces, and no output test would catch it,
  // because EAGAIN does not reproduce on demand.
  const code = fs.readFileSync(HELPER, "utf8");
  assert.match(code, /EAGAIN/);
  assert.match(code, /while \(off < buf\.length\)/,
    "writeAllSync no longer loops; a single fs.writeSync can write fewer bytes than asked");
});
