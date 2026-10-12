#!/usr/bin/env node
// A SCOPED type check over skills/_shared/pm-status.py: two error classes, not a clean file.
//
// WHY THIS EXISTS. `store.backlog()` -- reading an @property as a method -- shipped in 3.3.0
// and crashed every `reparent-story` on any project with a backlog, mid-write, leaving a
// story moved with every backlog reference still naming its old key. Fifteen other call
// sites in the same file read the same accessors correctly; this was the only one.
//
// Nothing we run could have caught it. ruff passes clean on a minimal repro of the pattern,
// measured -- it is a type error, not a lint. `check:bmb` shells to ruff and so sees the
// same nothing. The tests could not reach it: the branch sat behind
// `if os.path.exists(issues.yaml)` and no fixture created one.
//
// WHY IT IS NOT "run mypy and require zero errors". mypy reports 65 findings over this file
// today, mostly `str | None` flowing into os.path calls. Gating on a clean file would mean a
// large unrelated cleanup first, and until that landed there would be no gate at all. A
// scoped gate that works today beats a total one that is always one refactor away.
//
// WHY NOT "fail on any [operator] finding", which is the obvious narrow cut. That class is
// NOT clean: the file carries 4 pre-existing `[operator]` errors (`Unsupported operand types
// for + ("object" and "int")`). Gating on the code would fail on an unmodified file. The cut
// has to be the MESSAGE -- "not callable" -- which is clean today and is the exact shape that
// shipped the crash.
//
// THE SECOND CLASS, [name-defined], IS WHAT MAKES THE FIRST ONE REAL. pm-status.py imports
// ruamel lazily, inside each function, so a missing dependency prints a readable message
// instead of a traceback. That leaves `CommentedSeq` out of scope at module level, and an
// annotation naming an unresolvable type silently degrades to `Any` -- `reveal_type` prints
// `Any`, calling `Any` is allowed, and the annotation checks nothing. Measured, all three
// states:
//
//   lazy import only, accessors annotated, bug present -> 0 "not callable"  (gate blind)
//   TYPE_CHECKING import, annotated, bug present       -> 2 "not callable"  (both call sites)
//   TYPE_CHECKING import, annotated, code correct      -> 0 "not callable"  (no false positive)
//
// So the `if TYPE_CHECKING: from ruamel.yaml.comments import CommentedSeq` at the top of
// pm-status.py is load-bearing, and deleting it turns this gate into a no-op that still
// reports success -- the single most dangerous shape a check can have, and one this repo has
// already shipped twice (a payload manifest covering 38% of the payload, a bmb scan passing
// because ruff could not spawn). Removing that import is exactly a `[name-defined]` error on
// the annotation lines, so the gate fails rather than going quietly blind. It guards the
// mechanism that makes it work.
//
// This was found by the downstream package, which did the annotation follow-up we had both
// deferred, hit the inert-annotation state, and sent back the TYPE_CHECKING fix. Their report
// read mypy's behaviour as silence; it is not silent -- it says `Name "CommentedSeq" is not
// defined` on the annotation lines, which is what the second class below keys on.
//
// Usage: node scripts/check-types.mjs [-v]
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { writeAllSync } from "./write-all-sync.mjs";

// CHECK_TYPES_ROOT points the checker at another tree, for scripts/tests/check-types.test.mjs.
const repoRoot = process.env.CHECK_TYPES_ROOT ? path.resolve(process.env.CHECK_TYPES_ROOT) : process.cwd();
const verbose = process.argv.includes("-v");

const MYPY_PIN = "mypy==1.18.2";
const RUAMEL = "ruamel.yaml>=0.18";
const TARGET = path.join("skills", "_shared", "pm-status.py");

// Each gated class names the defect it exists for, so a failure explains itself without
// sending the reader here. `match` is applied to mypy's message text, `code` to its error
// code; a finding is gated when BOTH match.
const GATED = [
  {
    code: "operator",
    match: /not callable/,
    why: "a @property read as a method -- the 3.4.2 reparent-story crash",
  },
  {
    code: "name-defined",
    match: /./,
    why: "an annotation naming a type mypy cannot resolve degrades to `Any` and checks "
       + "nothing; this is what deleting the TYPE_CHECKING import at the top of "
       + "pm-status.py looks like",
  },
];

const target = path.join(repoRoot, TARGET);
if (!fs.existsSync(target)) {
  writeAllSync(2, `check-types: ${TARGET} not found under ${repoRoot}\n`);
  process.exitCode = 2;
} else {
  const run = spawnSync(
    "uv",
    ["run", "--quiet", "--with", MYPY_PIN, "--with", RUAMEL,
      "mypy", "--ignore-missing-imports", "--no-error-summary", "--output", "json", target],
    { encoding: "utf8", cwd: repoRoot },
  );

  if (run.error) {
    // A gate that cannot run must FAIL, never pass quietly. check:bmb reported clean over
    // ~12,000 unlinted lines for exactly this reason: its scanner shelled to a tool that
    // could not spawn, and the failure was swallowed.
    writeAllSync(2, `check-types: could not run uv (${run.error.message}).\n`
      + "Install uv (https://docs.astral.sh/uv/) -- it provisions mypy and ruamel itself.\n");
    process.exitCode = 2;
  } else {
    // --output json emits one JSON object per line. Parsed, never regex-scraped: a message
    // containing a newline or a bracket would defeat line-shape matching.
    const findings = [];
    const unparsed = [];
    for (const line of run.stdout.split("\n")) {
      if (!line.trim()) continue;
      try {
        findings.push(JSON.parse(line));
      } catch {
        unparsed.push(line);
      }
    }

    // mypy exits 1 when it reports findings and 2 when it could not run at all (a bad flag,
    // an unreadable file). Distinguishing them matters: exit 2 with no parseable output is a
    // broken gate, not a clean file.
    if (findings.length === 0 && run.status === 2) {
      writeAllSync(2, "check-types: mypy exited 2 without reporting findings -- the check did "
        + `not run.\n${run.stderr || unparsed.join("\n")}\n`);
      process.exitCode = 2;
    } else {
      const gated = [];
      for (const f of findings) {
        const rule = GATED.find((g) => g.code === f.code && g.match.test(f.message || ""));
        if (rule) gated.push({ ...f, why: rule.why });
      }

      if (gated.length) {
        const lines = [`\n${gated.length} type error(s) in ${TARGET}:\n`];
        for (const f of gated) {
          lines.push(`  ✗ ${TARGET}:${f.line} ${f.message}  [${f.code}]`);
          lines.push(`      ${f.why}\n`);
        }
        lines.push("This gate gates two classes only; the file's other findings are not "
          + "checked.\nSee scripts/check-types.mjs's header for why, and why these two.\n");
        writeAllSync(2, lines.join("\n"));
        process.exitCode = 1;
      } else {
        const tally = {};
        for (const f of findings) tally[f.code] = (tally[f.code] || 0) + 1;
        const detail = verbose
          ? `\nungated findings by code: ${Object.entries(tally)
            .sort((a, b) => b[1] - a[1]).map(([c, n]) => `${c}=${n}`).join(", ") || "none"}\n`
          : "";
        writeAllSync(1, `Type checks passed: no "not callable" and no unresolved annotation `
          + `in ${TARGET} (${findings.length} ungated finding(s) not checked).\n${detail}`);
      }
    }
  }
}
