// Tests for scripts/check-types.mjs.
// Run: npm run test:scripts
//
// Each test runs the REAL checker (via CHECK_TYPES_ROOT) against a fixture holding a COPY of
// the real pm-status.py, mutated. Copying the real file rather than writing a toy one is
// load-bearing: an annotated property DOES flag the bad call in five lines of Python and does
// NOT in pm-status.py, because that file imports ruamel lazily and the annotation degrades to
// `Any`. A fixture without the lazy import would pass while the real gate was blind.
//
// These spawn mypy through uv and so are slower than the rest of the suite. That is the cost
// of testing the gate rather than a model of it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHECK = path.join(REPO, "scripts", "check-types.mjs");
const PKG_REL = path.join("skills", "_shared", "pm_status");
const REL = path.join(PKG_REL, "__main__.py");
const PKG = path.join(REPO, PKG_REL);

const ACCESSOR_LOOP = "for lst in (store.backlog, store.resolved):";
const TC_IMPORT = "if TYPE_CHECKING:\n    from ruamel.yaml.comments import CommentedSeq\n";

function fixture(t, mutate = (s) => s) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-types-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  // The WHOLE package, not `__main__.py` alone. `__main__.py` imports its own submodules
  // relatively, and mypy refuses a relative import whose parent package is not on disk
  // beside it ("No parent module -- cannot perform relative import"), which is an exit-2
  // broken-gate state rather than a finding. Copying one file worked only while the package
  // was one file. __pycache__ is skipped: it is not source and mypy would not read it.
  const dest = path.join(dir, PKG_REL);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.cpSync(PKG, dest, { recursive: true, filter: (s) => !s.includes("__pycache__") });
  const main = path.join(dir, REL);
  fs.writeFileSync(main, mutate(fs.readFileSync(main, "utf8")));
  return dir;
}

function run(root, args = []) {
  return spawnSync(process.execPath, [CHECK, ...args], {
    cwd: REPO,
    env: { ...process.env, CHECK_TYPES_ROOT: root },
    encoding: "utf8",
  });
}

test("the real file passes", (t) => {
  const r = run(fixture(t));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /Type checks passed/);
});

test("a @property read as a method fails", (t) => {
  const root = fixture(t, (s) => {
    const n = s.replaceAll(ACCESSOR_LOOP, "for lst in (store.backlog(), store.resolved()):");
    assert.notEqual(n, s, "the accessor loop moved; update ACCESSOR_LOOP");
    return n;
  });
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /"CommentedSeq" not callable/);
  assert.match(r.stderr, /runtime TypeError/);
});

test("BOTH accessor call sites are reported, not just the first", (t) => {
  // A checker that sees one of two is one you will trust past the one it cannot see. The
  // two sites are _normalize_keys and _rewrite_references.
  const root = fixture(t, (s) =>
    s.replaceAll(ACCESSOR_LOOP, "for lst in (store.backlog(), store.resolved()):"));
  const r = run(root);
  assert.equal((r.stderr.match(/not callable/g) || []).length, 2, r.stderr);
});

test("deleting the TYPE_CHECKING import fails instead of going quietly blind", (t) => {
  // THE LOAD-BEARING TEST. Without that import the annotations resolve to `Any`, calling
  // `Any` is permitted, and this gate reports success over the very bug it exists for. A
  // no-op that still prints a pass is the most dangerous shape a check can have.
  const root = fixture(t, (s) => {
    assert.ok(s.includes(TC_IMPORT), "the TYPE_CHECKING import moved; update TC_IMPORT");
    return s.replace(TC_IMPORT, "");
  });
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /Name "CommentedSeq" is not defined/);
});

test("the inert-annotation state does NOT report the bug — why the second class is gated", (t) => {
  // The proof the two gated classes are not redundant. With the import gone AND the bug
  // present, mypy never says "not callable" at all; the only thing standing between that and
  // a silent pass is the [name-defined] arm.
  const root = fixture(t, (s) =>
    s.replace(TC_IMPORT, "")
      .replaceAll(ACCESSOR_LOOP, "for lst in (store.backlog(), store.resolved()):"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.doesNotMatch(r.stderr, /not callable/,
    "if mypy now reports this with the lazy import, the gate's rationale has changed");
  assert.match(r.stderr, /Name "CommentedSeq" is not defined/);
});

test("the package's other findings are NOT gated, and the count is reported not asserted", (t) => {
  // Scope is the whole design: gating on a clean file would mean a large unrelated cleanup
  // first, and until it landed there would be no gate at all. If this starts failing, the
  // gate was widened — decide that deliberately rather than discovering it in CI.
  //
  // The name deliberately carries NO number. It said "the file's other 65 findings" while the
  // gate reported 69, then 68 — stale through three tasks, because a number in a test name is
  // read by nobody and checked by nothing, which is this repo's most reliable place for prose
  // to rot. The assertions below are properties (a tally is printed, a breakdown is printed),
  // so they cannot go stale; `npm run check:types -v` is where the current number lives.
  const r = run(fixture(t), ["-v"]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /ungated finding\(s\) not checked/);
  assert.match(r.stdout, /ungated findings by code:/);
});

test("a pre-existing [operator] finding is not enough to fail — the cut is the message", (t) => {
  // The obvious narrow cut, "fail on any [operator] finding", fails on an unmodified file:
  // it carries 4 of them (`Unsupported operand types for + ("object" and "int")`).
  const r = run(fixture(t), ["-v"]);
  assert.equal(r.status, 0);
  assert.match(r.stdout, /operator=\d+/, "the ungated tally should still show operator findings");
});

test("a defect in a SECOND file of the package is caught, not just __main__.py", (t) => {
  // Code leaves __main__.py as it is extracted; a gate scoped to the one file would go blind.
  const root = fixture(t);
  const sub = path.join(root, path.dirname(REL), "sub");
  fs.mkdirSync(sub);
  fs.writeFileSync(path.join(sub, "probe.py"),
    "class A:\n    @property\n    def p(self) -> int:\n        return 1\n\n\n"
    + "def f() -> None:\n    A().p()\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stderr);
  assert.match(r.stderr, /sub\/probe\.py:8 "int" not callable/);
});

test("a missing target fails rather than passing over nothing", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-types-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const r = run(dir);
  assert.equal(r.status, 2);
  assert.match(r.stderr, /no \.py files/);
});
