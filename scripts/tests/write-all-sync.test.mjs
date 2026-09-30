// The gate scripts' report writer: the helper's behaviour, and the rule that every gate uses it.
//
// The bug is in scripts/write-all-sync.mjs's header. What is here is the guard, in two halves,
// because each is worthless alone: a behavioural test proves the helper delivers every byte,
// and a structural test proves the reporters still CALL it. `check-docs.mjs` had the helper and
// was one edit away from not using it.
//
// SCOPE IS DERIVED, FROM TWO SOURCES, UNIONED. The structural half takes every
// `scripts/check-*.mjs` AND every `scripts/*.mjs` that a `check:`/`test:` npm script invokes,
// because neither derivation alone covers the class. The glob alone missed `check:manifest`
// and `check:scripts`, which are gates that report per-finding in a loop and then exit -- the
// exact shape -- but are implemented in `write-payload-manifest.mjs` and
// `sync-shared-scripts.mjs`, so a pattern over filenames never saw them. The npm side alone
// would miss `check-module-view.mjs`, which `smoke-install.sh` invokes rather than npm. A
// hand-written list would have to be updated by exactly the person who did not know the rule.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { writeAllSync } from "../write-all-sync.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const HELPER = path.join(REPO, "scripts", "write-all-sync.mjs");
const PREFIX = `${path.basename(REPO)}-write-all-sync-`;

// Named like a gate.
function gatesByName() {
  return fs.readdirSync(path.join(REPO, "scripts")).filter((f) => /^check-.*\.mjs$/.test(f));
}

// Invoked like a gate. `scripts/tests/*.test.mjs` does not match: the capture rejects a `/`,
// so `test:scripts` contributes nothing, which is right -- the suites are not reporters.
function gatesByInvocation() {
  const pkg = JSON.parse(fs.readFileSync(path.join(REPO, "package.json"), "utf8"));
  const found = new Set();
  for (const [name, cmd] of Object.entries(pkg.scripts ?? {})) {
    if (!/^(check|test):/.test(name)) continue;
    for (const m of cmd.matchAll(/scripts\/([^\s/]+\.mjs)/g)) {
      if (fs.existsSync(path.join(REPO, "scripts", m[1]))) found.add(m[1]);
    }
  }
  return [...found];
}

function gateScripts() {
  return [...new Set([...gatesByName(), ...gatesByInvocation()])].sort();
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

// The window a `process.exit` is judged against: line i itself, plus the six LOGICAL lines
// above it, where a run of physical lines held open by an unbalanced bracket counts as one.
//
// Both refinements are there because a physical-line window called correct code a violation.
// `writeAllSync(...); process.exit(2)` on ONE line failed a window of the lines strictly
// above (found downstream, which split the line to appease the check -- making a check pass by
// rewriting correct code is the check being wrong). And a writeAllSync call spanning eight
// lines failed a six-line window here, because the identifier is at the TOP of a call whose
// closing paren is what sits next to the exit.
//
// Bracket counting is a heuristic -- it does not know a bracket inside a string literal -- so
// it can overshoot and judge a slightly larger window than intended. That direction is safe
// only because the test above bans every asynchronous writer outright, which leaves this one
// with a single job: catch an exit with no write before it at all.
function precedingWindow(lines, i, logicalLines = 6) {
  const out = [lines[i]];
  for (let j = i - 1, counted = 0; j >= 0 && counted < logicalLines; j--) {
    out.unshift(lines[j]);
    const text = out.join("\n");
    if ((text.match(/[([{]/g) ?? []).length >= (text.match(/[)\]}]/g) ?? []).length) counted++;
  }
  return out.join("\n");
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

test("every gate reports through writeAllSync, not an asynchronous writer", () => {
  // Both halves are anchored, not just the union: a union stays plausibly-sized while one of
  // its two derivations has silently gone to zero, and a derivation that contributes nothing
  // is exactly the drift this scope was widened to prevent.
  assert.ok(gatesByName().length >= 5,
    `expected at least 5 check-*.mjs gates, found ${gatesByName().length}`);
  assert.ok(gatesByInvocation().length >= 5,
    `expected at least 5 gates invoked by a check:/test: npm script, found ` +
    `${gatesByInvocation().length}: if this derivation stops matching, the scope silently ` +
    `narrows back to the filename glob that missed check:manifest and check:scripts`);

  for (const file of gateScripts()) {
    const code = codeOf(file);
    // Two spellings of one bug. `console.error` is the obvious one; `process.stderr.write` is
    // the stream API, also asynchronous over a pipe, and reads as deliberate enough that a
    // ban naming only console.* looks like it covers it. It does not -- writeSync is the only
    // synchronous writer here, and the ban has to say so or it teaches the wrong rule. (Found
    // downstream, in a gate that spelled it that way; there is no such gate here, so this half
    // of the pattern is guarding a hole rather than closing one.)
    //
    // `console.log` IS DELIBERATELY NOT BANNED, and the asymmetry is the rule, not an
    // oversight. What truncates is output still queued when process.exit() tears the process
    // down. A success line on a path that FALLS THROUGH -- sets process.exitCode, or sets
    // nothing -- is flushed by the normal shutdown, because the event loop runs to completion.
    // So the ban covers where reports go (stderr) and test 3 covers the actual hazard (exit
    // with anything queued); banning console.log as well would rewrite ~38 harmless call sites
    // and teach that the payload size matters, which the measured curve says it does not.
    assert.doesNotMatch(code, /console\.(error|warn)|process\.(stdout|stderr)\.write/,
      `${file} reports through an asynchronous writer (console.error/warn or a stream ` +
      `.write). Both queue over a pipe and lose whatever is still queued when the process ` +
      `exits. Build one string and call writeAllSync instead.`);
    assert.match(code, /writeAllSync/,
      `${file} never calls writeAllSync -- if it has nothing to report it is not a gate, and ` +
      `if it does, it must report through the helper.`);
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
      assert.match(precedingWindow(lines, i), /writeAllSync/,
        `${file}:${i + 1} calls process.exit() with no writeAllSync on it or in the six ` +
        `lines above. Anything still queued on stdout/stderr is discarded there, silently.`);
    }
  }
});

test("the helper retries EAGAIN rather than treating it as a short write", (t) => {
  // A non-blocking fd can refuse a write outright. Dropping the retry makes writeAllSync
  // truncate exactly as silently as the race it replaces, and no output test would catch it,
  // because EAGAIN does not reproduce on demand.
  const code = fs.readFileSync(HELPER, "utf8");
  assert.match(code, /EAGAIN/);
  assert.match(code, /while \(off < buf\.length\)/,
    "writeAllSync no longer loops; a single fs.writeSync can write fewer bytes than asked");

  // And the retry sleeps rather than spinning. A bare `continue` on EAGAIN is a busy-wait for
  // a reader to drain a pipe, which on a loaded box competes with that reader for the CPU it
  // needs to do the draining. Structural, because EAGAIN does not reproduce on demand: the
  // sleep must be Atomics.wait (the only synchronous one) and the delay must be bounded.
  assert.match(code, /Atomics\.wait/,
    "the EAGAIN path no longer sleeps -- a bare retry is a tight spin against the reader");
  assert.match(code, /Math\.min\(/,
    "the EAGAIN backoff is no longer capped; an unbounded doubling stalls a report for seconds");

  // Behavioural half: the sleep must not have cost the guarantee. An EAGAIN-free write still
  // has to deliver every byte, and the backoff sits in the same loop as the short-write retry.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), PREFIX));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const out = path.join(dir, "out.txt");
  const fd = fs.openSync(out, "w");
  const payload = "y".repeat(300_000);
  writeAllSync(fd, payload);
  fs.closeSync(fd);
  assert.equal(fs.readFileSync(out, "utf8"), payload);
});
