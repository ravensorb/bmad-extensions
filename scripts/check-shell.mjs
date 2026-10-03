#!/usr/bin/env node
// Lint every shell script this repo tracks: `bash -n` for syntax, ShellCheck for the rest.
//
// Why this gate exists
// --------------------
// `standards-shell.md` — a reference THIS PACKAGE ships to consuming projects — requires
// "ShellCheck clean in CI, not just locally". The repo shipped shell scripts and had no such
// gate, so the package was publishing a standard it did not meet. That is the same shape as
// the Python gap: nothing linted ~12,000 lines of Python until `check:lint:py` existed.
//
// Scope is DERIVED from `git ls-files`, never a list. A hand-kept set of paths would miss the
// next script somebody adds, and a gate that silently examines fewer files than exist reports
// success over a set that no longer contains what matters (CLAUDE.md §4).
//
// A MISSING ShellCheck IS A FAILURE, not a skip. This is the trap `check:bmb` already fell
// into: bmb's `scan-scripts.py` shells out to `uv run ruff`, which fails to spawn when ruff is
// absent, and the failure was swallowed — so the scan reported clean over Python it had never
// read. A linter that cannot run has told you nothing, and reporting that as a pass is worse
// than reporting nothing, because CI goes green.
//
// An EMPTY discovery is also a failure, for the same reason `run-python-suites.mjs` refuses
// one: zero files examined is indistinguishable from zero problems found.
import { execFileSync, spawnSync } from "node:child_process";
import process from "node:process";
import { writeAllSync } from "./write-all-sync.mjs";

const repoRoot = process.env.CHECK_SHELL_ROOT || process.cwd();
const verbose = process.argv.includes("-v") || process.argv.includes("--verbose");

function tracked() {
  // git is the source of truth for "a script this repo ships". An untracked scratch file in
  // the working tree is not this gate's business; a tracked one always is.
  const out = execFileSync("git", ["-C", repoRoot, "ls-files", "*.sh", "**/*.sh"], {
    encoding: "utf8",
  });
  return [...new Set(out.split("\n").map((s) => s.trim()).filter(Boolean))].sort();
}

function have(cmd) {
  const r = spawnSync(cmd, ["--version"], { encoding: "utf8" });
  return r.status === 0;
}

const files = tracked();
const failures = [];

if (files.length === 0) {
  writeAllSync(2,
    "check:shell: no tracked *.sh files found.\n" +
    "  Either the glob broke or the scripts moved. Refusing rather than reporting\n" +
    "  success over nothing — zero files examined is not zero problems found.\n");
  process.exitCode = 2;
} else if (!have("shellcheck")) {
  writeAllSync(2,
    "check:shell: shellcheck is not on PATH, so nothing was linted.\n" +
    `  ${files.length} tracked script(s) went unexamined: ${files.join(", ")}\n` +
    "  This is a FAILURE, not a skip. A linter that cannot run has told you nothing,\n" +
    "  and standards-shell.md — which this package ships to consumers — requires\n" +
    "  ShellCheck clean in CI. Install it (apt: shellcheck, brew: shellcheck) or, in\n" +
    "  CI, add the install step before this gate.\n");
  process.exitCode = 2;
} else {
  for (const rel of files) {
    const syntax = spawnSync("bash", ["-n", rel], { cwd: repoRoot, encoding: "utf8" });
    if (syntax.status !== 0) {
      failures.push(`${rel}: bash -n failed\n${(syntax.stderr || "").trim()}`);
      continue; // ShellCheck on a file bash cannot parse adds noise, not information
    }
    const sc = spawnSync("shellcheck", ["--format=gcc", rel], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    if (sc.status !== 0) {
      failures.push(`${rel}:\n${(sc.stdout || sc.stderr || "").trim()}`);
    }
  }

  if (verbose) {
    const v = spawnSync("shellcheck", ["--version"], { encoding: "utf8" });
    const ver = (v.stdout || "").split("\n").find((l) => l.startsWith("version:")) || "";
    console.log(`  shell: ${files.length} script(s), ${ver.trim()}`);
  }

  if (failures.length > 0) {
    writeAllSync(2,
      `\n${failures.length} shell problem(s) across ${files.length} script(s):\n\n` +
      failures.map((f) => `  ✗ ${f}\n\n`).join("") +
      "Every suppression carries a comment saying why (standards-shell.md).\n");
    process.exitCode = 1;
  } else {
    console.log(
      `Shell checks passed: ${files.length} script(s), bash -n and ShellCheck clean.`);
  }
}
