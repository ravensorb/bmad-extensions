#!/usr/bin/env node
// Validate documentation against the code it describes.
//
// Why: this repo states the same fact in several files by design — README evaluates,
// getting-started onboards, the references look up, architecture explains, CLAUDE.md
// instructs. That is the right shape for the readers, but nothing stopped the copies
// drifting apart, and they did: a gating table stale in five places, a fix-loop cap in six,
// four skills documented that had not existed for two minor versions, an agent sanctum
// path wrong in three files, and a routing table pointing at a section that had moved.
// Every one was found by a human reading carefully. These checks find them for free.
//
// Deliberately narrow. Each check asserts a fact that is mechanically decidable and has
// already drifted at least once in this repo's history. Checks that would need judgement
// belong in review, not here — a checker that cries wolf gets switched off.
//
//   1. skill-names   every l3io-* skill named in docs resolves to a real skills/ directory
//   2. gating-tables every mirrored phase table matches the authoritative matrix, cell for cell
//   3. section-refs  every "<file>.md §N" cross-reference resolves to a section bearing that number
//   4. cli-surface   documented pm-status.py and spec-align.py subcommands and the real CLIs
//                    agree, both ways -- across the live docs AND every runtime directive
//                    under skills/, where an invocation's long flags are checked too
//   5. config-values values quoted in prose match the defaults customize.toml ships
//   6. status-values --status filters named in skill phrase tables are real state folders
//   7. metric-list   metrics-contract.md documents exactly the metrics in METRIC_FIELDS
//   8. digest-size   the activation digest stays inside its byte budget
//   9. authoring-paths no runtime directive tells an agent to read skills/_shared/ (not
//                    installed) instead of the installed references/assets/steps path
//  10. cli-docstring pm-status.py's and spec-align.py's own module docstrings name every
//                    subcommand each parser defines
//  11. append-issue-pointer every append-issue invocation in skills/ (logical lines, `\`-
//                    continued lines joined, fenced or not) passes --source and --description
//  12. pm-status-size skills/_shared/pm-status.py stays within the 8,000-line limit
//                    ADR-0001 sets
//  13. spec-align-contract spec-align.py's spec kinds match layout-cleanup.md heuristic 5, and
//                    its six DIMENSIONS match the enrichment prompt's layout block
//  14. adr-home      no runtime directive names the old per-epic ADR home (epic-*/arch/adr-*)
//  15. doctor-mode-count  the doctor's stated mode count equals the modes it actually has
//  16. bmad-dependency-inventory  every bmad-* name a runtime directive under skills/ uses is
//                    declared in skills/l3io-util-doctor/assets/bmad-dependencies.json, and no
//                    directive dispatches a removed one without same-line historical evidence
//  17. pep723-invocation  no runtime directive under skills/, and no CI step under
//                    .github/workflows/, invokes a PEP-723 script ({pm_status}, {spec_align},
//                    or a *.py path) with python3, which bypasses the header's declared deps
//                    in favor of whatever sits in the ambient interpreter
//  18. docs-check-count  the numbered checks in this header agree in count with the check
//                    functions invoked below, and CLAUDE.md / scripts/CLAUDE.md's stated
//                    check count agrees with both
//  19. derived-counts  the skill count, module count, and l3io-pm skill count claimed in
//                    prose match what skills/ actually has, derived from the directory and
//                    each skill's module.yaml `code:` field — never typed
//  20. shared-files-table  every skills/_shared/* source a sync group in
//                    sync-shared-scripts.mjs references has a row in CLAUDE.md's Shared
//                    Files table, and every table row names a source that actually exists
//  21. skill-frontmatter  every skills/*/SKILL.md frontmatter strict-YAML-parses and its
//                    `name:` equals the directory name -- what BMad's installer requires
//                    before a skill reaches skill-manifest.csv and .claude/skills/ at all;
//                    a skill that fails either test is dropped from a real install with no
//                    warning (Task 11A fix round 1, H-1/H-2)
//  22. readme-repo-layout  README's "## Repo Layout" block lists, for every l3io-* skill, the
//                    subdirectories that skill actually has -- both directions, with both
//                    sides derived (the skill set from skills/, the claims from the block,
//                    the real directories from disk)
//
// Usage:
//   node scripts/check-docs.mjs        # report and exit nonzero on any failure (CI)
//   node scripts/check-docs.mjs -v     # also print what passed
import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";
import sh from "mvdan-sh";

// CHECK_DOCS_ROOT points the checker at another tree -- scripts/tests/check-docs.test.mjs
// runs it against a temp copy with a planted violation.
const repoRoot = process.env.CHECK_DOCS_ROOT ? path.resolve(process.env.CHECK_DOCS_ROOT) : process.cwd();
const verbose = process.argv.includes("-v") || process.argv.includes("--verbose");
const failures = [];
const notes = [];

const read = (p) => fs.readFileSync(path.join(repoRoot, p), "utf8");
const exists = (p) => fs.existsSync(path.join(repoRoot, p));

// Files a reader is told are current. Historical records are excluded on purpose: CHANGELOG
// and docs/superpowers/** describe what was true when written, and rewriting them to match
// today would falsify the record.
const LIVE_DOCS = [
  "README.md",
  "CLAUDE.md",
  ...fs.readdirSync(path.join(repoRoot, "docs"))
    .filter((f) => f.endsWith(".md"))
    .map((f) => path.join("docs", f)),
];

// ---------------------------------------------------------------------------
// 1. Every l3io-* skill named in live docs resolves to a real skill directory.
//
// Caught in practice: README documented l3io-pm-plan-execution, l3io-pm-sprint-execute,
// l3io-pm-epic-execute and l3io-sec-agent-redteam long after the 2.0 rename merged them
// away, and three docs pointed at _bmad/memory/l3io-sec-agent-redteam/ — a path that does
// not exist, so anyone following them looked in the wrong directory.
// ---------------------------------------------------------------------------
function checkSkillNames() {
  const real = new Set(
    fs.readdirSync(path.join(repoRoot, "skills")).filter((d) => d.startsWith("l3io-")),
  );
  // Names ending in -reference are doc filenames (docs/l3io-pm-reference.md), not skills.
  const isDocName = (n) => n.endsWith("-reference");
  let checked = 0;

  for (const doc of LIVE_DOCS) {
    const text = read(doc);
    const seen = new Set(text.match(/l3io-(?:pm|sec|util|arch)-[a-z-]+/g) || []);
    for (const name of seen) {
      if (isDocName(name)) continue;
      checked += 1;
      if (real.has(name)) continue;

      // Naming a removed skill is legitimate in two shapes, and both must pass or this
      // check gets switched off for crying wolf:
      //   a migration table mapping the old name to the new one on the same line, and
      //   prose explaining that the name changed.
      const lines = text.split("\n");
      const idx = lines.findIndex((l) => l.includes(name));
      const line = lines[idx] ?? "";
      const sameLineMapsToRealSkill = [...real].some((r) => line.includes(r));
      // Prose can put the replacement a sentence or two away, so widen to a small window.
      const window = lines.slice(Math.max(0, idx - 4), idx + 5).join("\n");
      const explainsTheChange =
        /renam|deprecat|remov|previously|no longer|was listed|are now|superseded|merged|historical|when the note/i.test(
          window,
        );

      if (sameLineMapsToRealSkill || explainsTheChange) {
        notes.push(`${doc}: names absent skill '${name}' as history or a mapping — allowed`);
        continue;
      }
      failures.push(
        `${doc}: names skill '${name}', which is not a directory under skills/\n` +
          `      context: ${line.trim().slice(0, 110)}`,
      );
    }
  }
  if (verbose) console.log(`  skill-names:    ${checked} reference(s) checked`);
}

// ---------------------------------------------------------------------------
// 2. Mirrored phase tables match the authoritative matrix.
//
// The matrix in steps/shared/step-01-classify-work.md §4 is the single source of truth for
// which review phases run per work type. Two docs mirror it for readability and say so.
// Caught in practice: five copies disagreed, and turning UX review off for DOCS updated
// three of them.
//
// Compared by the leading phase-name word so cosmetic labelling differs freely —
// "Red team (l3io-sec)" and "Red team (`l3io-sec-redteam`)" are the same row.
// ---------------------------------------------------------------------------
const MATRIX_SOURCE = "skills/_shared/steps/shared/step-01-classify-work.md";
const MATRIX_MIRRORS = ["docs/architecture.md", "docs/l3io-pm-reference.md"];

function phaseRows(text) {
  const rows = new Map();
  for (const line of text.split("\n")) {
    const m = line.match(
      /^\|\s*([A-Z][^|]*?)\s*\|\s*(run|skip)\s*\|\s*(run|skip)\s*\|\s*(run|skip)\s*\|\s*(run|skip)\s*\|/,
    );
    if (m) rows.set(normalisePhase(m[1]), [m[2], m[3], m[4], m[5]]);
  }
  return rows;
}

// "Red team (`l3io-sec`)" -> "red team";  "Sprint architectural drift" -> "sprint architectural drift"
const normalisePhase = (label) =>
  label.replace(/\(.*?\)/g, "").replace(/`/g, "").trim().toLowerCase();

function checkGatingTables() {
  const source = phaseRows(read(MATRIX_SOURCE));
  if (source.size === 0) {
    failures.push(`${MATRIX_SOURCE}: no phase matrix found — has the matrix moved?`);
    return;
  }
  let compared = 0;
  for (const mirror of MATRIX_MIRRORS) {
    if (!exists(mirror)) continue;
    for (const [phase, cells] of phaseRows(read(mirror))) {
      if (!source.has(phase)) continue; // mirrors may omit rows; they must not contradict
      compared += 1;
      const want = source.get(phase);
      if (cells.join() === want.join()) continue;
      failures.push(
        `${mirror}: phase '${phase}' is [${cells.join(", ")}] but the matrix in\n` +
          `      ${MATRIX_SOURCE} says [${want.join(", ")}] (CODE, DOCS, CONFIG, MIXED)`,
      );
    }
  }
  if (verbose) console.log(`  gating-tables:  ${compared} mirrored row(s) compared against the matrix`);
}

// ---------------------------------------------------------------------------
// 3. "<file>.md §N" cross-references resolve to a section bearing that number.
//
// Caught in practice: the activation digest's routing table is the only thing telling a
// subagent which section of a 400-line reference to open, and a fix wave pointed one row at
// the wrong section. A pointer that resolves to nothing is worse than no pointer.
//
// Only fully-qualified references are checked. A bare "§8" is contextual — it usually means
// a section of the file you are already reading — and resolving it would need judgement.
// ---------------------------------------------------------------------------
const REF_SCAN_ROOTS = ["skills/_shared", "docs", "CLAUDE.md", "README.md"];

function* walkMarkdown(rel) {
  const abs = path.join(repoRoot, rel);
  if (!fs.existsSync(abs)) return;
  if (fs.statSync(abs).isFile()) {
    if (abs.endsWith(".md")) yield rel;
    return;
  }
  for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
    if (entry.name === "superpowers") continue; // dated specs and plans are historical
    yield* walkMarkdown(path.join(rel, entry.name));
  }
}

function sectionNumbers(absPath) {
  const nums = new Set();
  for (const line of fs.readFileSync(absPath, "utf8").split("\n")) {
    const m = line.match(/^#{2,3}\s+(\d+)\.\s/);
    if (m) nums.add(Number(m[1]));
  }
  return nums;
}

// Resolve a referenced basename to a real file, preferring the canonical shared copy.
function resolveTarget(basename) {
  for (const candidate of [
    path.join("skills", "_shared", basename),
    path.join("skills", "_shared", "steps", "shared", basename),
    path.join("docs", basename),
  ]) {
    if (exists(candidate)) return candidate;
  }
  const hit = fs
    .readdirSync(path.join(repoRoot, "skills", "_shared", "steps"), { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => path.join("skills", "_shared", "steps", d.name, basename))
    .find(exists);
  return hit || null;
}

function checkSectionRefs() {
  const cache = new Map();
  let checked = 0;
  for (const root of REF_SCAN_ROOTS) {
    for (const rel of walkMarkdown(root)) {
      const text = read(rel);
      const re = /([a-z0-9-]+\.md)`?\s*§(\d+)/g;
      let m;
      while ((m = re.exec(text)) !== null) {
        const [, basename, num] = m;
        const target = resolveTarget(basename);
        if (!target) continue; // referenced file is outside the checkable set
        if (!cache.has(target)) cache.set(target, sectionNumbers(path.join(repoRoot, target)));
        const nums = cache.get(target);
        if (nums.size === 0) continue; // target has no numbered sections at all
        checked += 1;
        if (nums.has(Number(num))) continue;
        failures.push(
          `${rel}: references ${basename} §${num}, but that file has no section ${num}\n` +
            `      (it has: ${[...nums].sort((a, b) => a - b).join(", ")})`,
        );
      }
    }
  }
  if (verbose) console.log(`  section-refs:   ${checked} cross-reference(s) resolved`);
}

// ---------------------------------------------------------------------------
// 4. The documented pm-status.py CLI surface matches the real one, both ways.
//
// Docs list subcommands in four places by design — the script's own docstring, the
// addressing table in status-files.md §7, the reference doc's table, and the activation
// digest, which exists precisely so a subagent has the signatures inline. Those mirrors are
// fine; silently disagreeing with the CLI is not.
//
// Caught in practice: removing the unused `progress` subcommand meant editing three separate
// docs, and adding `report` meant remembering to document it. Either could have been missed.
//
// Checked both directions:
//   forward  a subcommand a doc names must exist in the CLI  (stale doc)
//   reverse  a subcommand the CLI has must appear in the reference  (undocumented feature)
// ---------------------------------------------------------------------------
const PM_STATUS = "skills/_shared/pm-status.py";
const CLI_REFERENCE_DOC = "docs/l3io-pm-reference.md";
// Words that follow "pm-status.py" in prose rather than naming a subcommand.
const PROSE_AFTER_CMD = new Set(["only", "is", "are", "and", "or", "the", "for", "with",
  "to", "from", "in", "on", "at", "by", "not", "itself", "runs", "writes", "reads"]);

function cliSubcommands() {
  // argparse registrations are the authoritative surface: sub.add_parser("name", ...)
  const src = read(PM_STATUS);
  return new Set([...src.matchAll(/sub\.add_parser\(\s*"([a-z-]+)"/g)].map((m) => m[1]));
}

const SPEC_ALIGN = "skills/_shared/spec-align.py";
const SPEC_ALIGN_HEADING = "### `spec-align.py` subcommands";

function specAlignSubcommands() {
  // Top-level registrations only: `\bsub.` excludes nested parsers such as lease_sub.
  if (!exists(SPEC_ALIGN)) return new Set();
  return new Set([...read(SPEC_ALIGN).matchAll(/\bsub\.add_parser\(\s*"([a-z-]+)"/g)]
    .map((m) => m[1]));
}

// The text of a markdown section: from its heading to the next ##/### heading.
function docSection(text, heading) {
  const i = text.indexOf(heading);
  if (i < 0) return "";
  const rest = text.slice(i + heading.length);
  const end = rest.search(/\n#{2,3} /);
  return end < 0 ? rest : rest.slice(0, end);
}

function checkCliSurface() {
  const real = cliSubcommands();
  const saReal = specAlignSubcommands();
  if (real.size === 0) {
    failures.push(`${PM_STATUS}: no sub.add_parser() calls found — has the CLI been restructured?`);
    return;
  }
  let checked = 0;

  // Forward. Hyphenated names are unambiguous wherever they appear in backticks. Single-word
  // names (show, report, verify) are ordinary English, so only trust the explicit
  // "pm-status.py <cmd>" form for those — a checker that flags the word "report" in prose is
  // a checker nobody keeps.
  for (const rel of [...LIVE_DOCS, "skills/_shared/status-files.md",
                     "skills/_shared/steps/shared/step-00-activate.md"]) {
    if (!exists(rel)) continue;
    const text = read(rel);
    const named = new Set([
      ...[...text.matchAll(/`([a-z]+(?:-[a-z]+)+)`/g)].map((m) => m[1]),
      ...[...text.matchAll(/pm-status\.py\s+([a-z-]+)/g)].map((m) => m[1]),
    ]);
    for (const name of named) {
      // "pm-status.py" is followed by prose as often as by a subcommand ("written by
      // pm-status.py only", "see pm-status.py --help"), so filter both shapes out. Flags are
      // never subcommands; the stopword list stays tiny and covers what actually occurs.
      if (name.startsWith("-")) continue;
      if (PROSE_AFTER_CMD.has(name)) continue;
      // Only judge tokens that look like they are claiming to be subcommands: either the CLI
      // has one by that name, or the doc used the explicit pm-status.py form.
      const explicit = new RegExp(`pm-status\\.py\\s+${name}\\b`).test(text);
      // spec-align.py has check-* subcommands of its own; they are not pm-status claims.
      if (!explicit && saReal.has(name)) continue;
      if (!explicit && !/^(set|estimate|move|archive|append|list|check|clear|self)-/.test(name)) continue;
      checked += 1;
      if (real.has(name)) continue;
      const line = text.split("\n").find((l) => l.includes(name)) || "";
      if (/remov|deprecat|no longer|replaced|used to/i.test(line)) {
        notes.push(`${rel}: names absent subcommand '${name}' while describing its removal — allowed`);
        continue;
      }
      failures.push(
        `${rel}: documents pm-status.py subcommand '${name}', which the CLI does not have\n` +
          `      CLI has: ${[...real].sort().join(", ")}`,
      );
    }
  }

  // Reverse. The reference doc is where a reader looks for the complete surface.
  //
  // Caught in practice: `dispatch` (added while this branch was in flight) sat undocumented
  // for eleven tasks while this very check stayed green, because it matched on
  // `\b${name}\b` against the whole file — and "epics dispatch concurrently up to
  // max_parallel_subagents" in unrelated prose about dispatching subagents is a real,
  // whole-word "dispatch" that satisfies a word-boundary test without naming the
  // subcommand at all. Any subcommand whose name is a common English word could skip
  // documentation entirely and this check would never notice.
  //
  // Tightened to require a real documented entry: a markdown table row whose first cell
  // backtick-quotes the name, e.g. `| \`dispatch\` | ... |` or a comma-separated
  // `| \`set-lock\`, \`clear-lock\`, \`check-lock\` | ... |`. A namespaced doc entry like
  // `| \`calibration show\` | ... |` also counts — its first word is the real subcommand.
  // Prose mentioning the word, however emphatic, no longer counts.
  const refText = exists(CLI_REFERENCE_DOC) ? read(CLI_REFERENCE_DOC) : "";
  const documented = tableRowSubcommands(refText);
  for (const name of real) {
    if (name === "self-install") continue; // internal plumbing, deliberately not user-facing
    checked += 1;
    if (documented.has(name)) continue;
    failures.push(
      `${CLI_REFERENCE_DOC}: does not document pm-status.py subcommand '${name}' as a table row\n` +
        `      every CLI subcommand should appear as a '| \`${name}\` | ... |' row in the subcommand table`,
    );
  }
  if (verbose) console.log(`  cli-surface:    ${checked} subcommand claim(s) checked both ways`);

  // Check 4 spans two scripts (pm-status.py above, spec-align.py below) and three scopes
  // (live docs above, skills/ below), implemented as separate functions for readability, but
  // it is ONE numbered check -- called from here rather than as its own top-level statement
  // so check 18's derived count (one invocation per header entry) doesn't have to
  // special-case them.
  checkPmStatusInvocations();
  checkSpecAlignSurface();
}

// 4 (continued). Every pm-status.py invocation in a runtime directive under skills/.
//
// Why this exists. The forward arm above reads LIVE_DOCS (README, CLAUDE.md, docs/*.md) plus
// two _shared files, and judges subcommand NAMES only -- never flags. So the commands agents
// actually execute, which live in skills/**/*.md, were checked by nothing at all. Task 12
// inlined `uv run {pm_status} clear-lock --state-root ... --epic ...` into
// skills/l3io-pm-help/steps/mode-list-plan.md, Task 13 put a second copy in
// skills/l3io-util-doctor/steps/stats.md, and the two are cross-linked in prose only: renaming
// the subcommand or dropping a flag would leave both copies green and both runs broken.
//
// Scope, derived. allSkillDocs() walks skills/ for *.md -- the same set checks 9, 11 and 17
// use -- so a directive added in a new file or a new skill is covered on arrival.
//
// What counts as an invocation. A logical line (physical lines joined on a trailing `\`) is
// scanned for `uv run`; from each such anchor the fragment up to the next backtick (a markdown
// code span closes there, and so does a table cell's `…` wrapper) is handed to mvdan-sh, the
// same real shell parser check 17 uses. A command whose argv contains {pm_status} or a
// pm-status.py path is judged: the token after it is the subcommand, and every later `--flag`
// is a flag claim. Nothing is decided by regex over text.
//
// Anchoring on `uv run` is not a convenience -- it is the package's own rule. check 17 already
// forbids reaching a PEP-723 script any other way, so an invocation that is not `uv run`-shaped
// is a check 17 failure, not a gap here. It also makes prose unreachable by construction:
// "later pm-status.py write on that node fail" (migrate-state.md, inside a fenced BLOCKED
// message) is a sentence, not a command, and no stopword list is needed to say so.
//
// Flags are checked for EXISTENCE IN THE CLI, not for belonging to that subcommand. The
// authoritative per-subcommand surface lives in argparse objects that only python can build,
// and reaching it means one `uv run` subprocess per checker run -- multiplied by the 100+
// fixture runs in scripts/tests/check-docs.test.mjs. So the rule here is the union of every
// long option the CLI registers anywhere. Measured against the real thing before shipping:
// building build_parser() under uv and unioning every subparser's option_strings yields 82
// flags; PY_LONG_OPTION_RE yields those same 82 plus the top-level --version, with nothing
// missing in either direction. What this does NOT catch: a real flag used with the wrong
// subcommand (`set-status --scope story`). That is stated here rather than implied.
//
// Not detected, measured on this tree: 8 fragments (2 distinct synopsis lines x 4 synced
// copies, metrics-contract.md:442 and :547) do not parse as shell, because a usage synopsis
// writes alternation as `(--story KEY | --epic ID)`. They are skipped and counted; -v prints
// the number. Making them failures would turn CI red on correct documentation.
const PM_STATUS_TOKEN_RE = /^(?:.*\/)?(?:\{pm_status\}|pm-status\.py)$/;
// All long option strings of one add_argument(...) call, including aliases: --elapsed-hours
// and --time-hours are registered in one call, and matching only the first would have missed
// three flags.
const PY_LONG_OPTION_RE = /add_argument\(\s*((?:"--[a-z0-9-]+"\s*,\s*)*"--[a-z0-9-]+")/g;

function pmStatusLongOptions() {
  const flags = new Set(["--help"]); // argparse adds it to every parser; no add_argument call
  for (const call of read(PM_STATUS).matchAll(PY_LONG_OPTION_RE)) {
    for (const opt of call[1].matchAll(/"(--[a-z0-9-]+)"/g)) flags.add(opt[1]);
  }
  return flags;
}

// The logical lines of a markdown file, each paired with the 1-based number of the physical
// line it started on. Two things continue a line:
//   - a trailing `\`, which is a shell continuation (check 11 joins these too);
//   - an unclosed `…` code span, which is a markdown SOFT WRAP. Without it the second copy of
//     the duplicated clear-lock remedy escapes its own flag check:
//     l3io-util-doctor/steps/stats.md writes the command across two source lines inside one
//     span, so `--state-root`/`--epic` sit on the line after the subcommand. The l3io-pm-help
//     copy is one table-cell line and was already covered -- checking one copy of a
//     duplication and not the other is the failure this arm exists to prevent.
// A ``` fence line has three backticks and is never treated as an open span, and the join is
// capped so a stray backtick cannot swallow a file.
const MAX_LINE_JOINS = 3;

function logicalLines(text) {
  const lines = text.split("\n");
  const out = [];
  const spanLeftOpen = (s) => !/^\s*```/.test(s) && ((s.match(/`/g) || []).length % 2 === 1);
  for (let i = 0; i < lines.length; i++) {
    let joined = lines[i];
    let j = i;
    for (let joins = 0; joins < MAX_LINE_JOINS && j + 1 < lines.length; joins += 1) {
      const shellContinuation = /\\\s*$/.test(joined);
      if (!shellContinuation && !spanLeftOpen(joined)) break;
      if (shellContinuation) joined = joined.replace(/\\\s*$/, "");
      j += 1;
      joined += " " + lines[j];
    }
    out.push({ text: joined, line: i + 1 });
    i = j;
  }
  return out;
}

function checkPmStatusInvocations() {
  const real = cliSubcommands();
  const flags = pmStatusLongOptions();
  let checked = 0;
  let unreadable = 0;
  const offenders = [];

  for (const rel of allSkillDocs()) {
    for (const { text, line } of logicalLines(read(rel))) {
      for (const anchor of text.matchAll(/\buv\s+run\b/g)) {
        let fragment = text.slice(anchor.index);
        const closingBacktick = fragment.indexOf("`");
        if (closingBacktick >= 0) fragment = fragment.slice(0, closingBacktick);
        if (!/\{pm_status\}|pm-status\.py/.test(fragment)) continue;

        const commands = shellCommands(fragment);
        if (commands === null) { unreadable += 1; continue; }
        for (const { argv } of commands) {
          const at = argv.findIndex((t) => typeof t === "string" && PM_STATUS_TOKEN_RE.test(t));
          if (at < 0) continue;
          const sub = argv[at + 1];
          if (typeof sub !== "string" || !/^[a-z][a-z-]*$/.test(sub)) continue;
          checked += 1;
          if (!real.has(sub)) {
            // Same tolerance the live-docs arm gives: a line that is describing the removal
            // is allowed to name what was removed.
            if (/remov|deprecat|no longer|replaced|used to/i.test(text)) {
              notes.push(`${rel}:${line}: names absent subcommand '${sub}' while describing ` +
                `its removal — allowed`);
              continue;
            }
            offenders.push(`${rel}:${line}: invokes pm-status.py subcommand '${sub}', which ` +
              `the CLI does not have\n      CLI has: ${[...real].sort().join(", ")}`);
            continue;
          }
          for (const token of argv.slice(at + 2)) {
            if (typeof token !== "string" || !token.startsWith("--")) continue;
            const flag = token.split("=")[0];
            if (flag === "--") continue;
            if (flags.has(flag)) continue;
            offenders.push(`${rel}:${line}: invokes '${sub} ${flag}', but pm-status.py ` +
              `registers no such option anywhere in its CLI`);
          }
        }
      }
    }
  }

  if (offenders.length) {
    failures.push(`runtime directives under skills/ invoke pm-status.py surface that does ` +
      `not exist:\n      ${offenders.join("\n      ")}`);
  }
  if (verbose) {
    console.log(`  pm-status-invocations: ${checked} invocation(s) in skills/ checked ` +
      `(${unreadable} fragment(s) not readable as shell, skipped)`);
  }
}

// Subcommand names documented as real table-row entries: the first cell of a markdown
// table row that backtick-quotes one or more names, comma-separated, optionally
// namespaced ("calibration show" documents "calibration"). Prose anywhere else in the
// file does not count, however word-boundary-clean the match would be.
function tableRowSubcommands(text) {
  const names = new Set();
  for (const line of text.split("\n")) {
    const trimmed = line.trimStart();
    if (!trimmed.startsWith("|")) continue;
    const firstCell = trimmed.slice(1).split("|")[0];
    for (const m of firstCell.matchAll(/`([^`]+)`/g)) {
      names.add(m[1].trim().split(/\s+/)[0]);
    }
  }
  return names;
}

// 4 (continued). The spec-align.py CLI surface, both ways. Step files invoke it through the
// `{spec_align}` binding, so forward reads `{spec_align} <sub>` anywhere, and the explicit
// `spec-align.py <sub>` form only inside code (a fence or a backtick span) -- prose such as
// "spec-align.py stays one file" is not a claim. Scope: every live doc and every skill doc.
function checkSpecAlignSurface() {
  const real = specAlignSubcommands();
  if (real.size === 0) {
    failures.push(`${SPEC_ALIGN}: no sub.add_parser() calls found — has the CLI moved?`);
    return;
  }
  let checked = 0;
  for (const rel of [...LIVE_DOCS, ...walkMarkdown("skills")]) {
    let inFence = false;
    read(rel).split("\n").forEach((line, i) => {
      if (/^\s*```/.test(line)) inFence = !inFence;
      const spans = [...line.matchAll(/`[^`]*`/g)].map((m) => [m.index, m.index + m[0].length]);
      const inCode = (at) => inFence || spans.some(([a, b]) => at > a && at < b);
      for (const m of line.matchAll(/\{spec_align\}\s+([a-z][a-z-]*)/g)) {
        checked += 1;
        if (!real.has(m[1])) {
          failures.push(`${rel}:${i + 1}: names spec-align.py subcommand '${m[1]}', which ` +
            `the CLI does not have\n      CLI has: ${[...real].sort().join(", ")}`);
        }
      }
      for (const m of line.matchAll(/spec-align\.py\s+([a-z][a-z-]*)/g)) {
        if (!inCode(m.index) || PROSE_AFTER_CMD.has(m[1])) continue;
        checked += 1;
        if (!real.has(m[1])) {
          failures.push(`${rel}:${i + 1}: names spec-align.py subcommand '${m[1]}', which ` +
            `the CLI does not have\n      CLI has: ${[...real].sort().join(", ")}`);
        }
      }
    });
  }
  const section = docSection(exists(CLI_REFERENCE_DOC) ? read(CLI_REFERENCE_DOC) : "",
                             SPEC_ALIGN_HEADING);
  const documented = tableRowSubcommands(section);
  for (const name of real) {
    checked += 1;
    if (documented.has(name)) continue;
    failures.push(`${CLI_REFERENCE_DOC}: does not document spec-align.py subcommand '${name}' ` +
      `as a table row under "${SPEC_ALIGN_HEADING}"`);
  }
  if (verbose) console.log(`  spec-align-surface: ${checked} claim(s) checked both ways`);
}

// ---------------------------------------------------------------------------
// 5. Config values restated in prose match the shipped defaults.
//
// Docs quote the fix-loop cap inline because a reader wants the number without a click.
// That is the right call for the reader and the wrong one for consistency — unless the
// quote is checked. Caught in practice: the cap was stated as a flat 10 in six places and
// went stale in all of them the moment it became configurable.
// ---------------------------------------------------------------------------
const PM_SKILLS = ["l3io-pm-execute", "l3io-pm-plan", "l3io-pm-sync", "l3io-pm-help"];

function tomlInt(text, key) {
  const m = text.match(new RegExp(`^${key}\\s*=\\s*(\\d+)`, "m"));
  return m ? Number(m[1]) : null;
}

function checkConfigValues() {
  // The four PM skills must agree with each other first — a doc cannot match all of them
  // if they disagree, and a per-skill divergence is itself a defect.
  const defaults = {};
  for (const key of ["max_fix_iterations", "max_fix_iterations_non_code"]) {
    const seen = new Map();
    for (const skill of PM_SKILLS) {
      const p = `skills/${skill}/customize.toml`;
      if (!exists(p)) continue;
      const v = tomlInt(read(p), key);
      if (v !== null) seen.set(skill, v);
    }
    const values = new Set(seen.values());
    if (values.size > 1) {
      failures.push(
        `customize.toml: '${key}' disagrees across PM skills — ` +
          [...seen].map(([s, v]) => `${s}=${v}`).join(", "),
      );
    }
    if (values.size === 1) defaults[key] = [...values][0];
  }
  if (defaults.max_fix_iterations === undefined) return; // key absent; nothing to verify against

  const code = defaults.max_fix_iterations;
  const nonCode = defaults.max_fix_iterations_non_code;
  let checked = 0;

  for (const doc of LIVE_DOCS) {
    // Scope to lines naming the knob. A bare "default 4" elsewhere in the file belongs to
    // max_parallel_subagents, "default 30" to the lock TTL, and "default 1.25" to the fix
    // reserve — matching those was the first draft's bug.
    const text = read(doc)
      .split("\n")
      .filter((l) => l.includes("max_fix_iterations"))
      .join("\n");
    if (!text) continue;
    // Phrasings in use: "10 for CODE/MIXED", "3 for DOCS/CONFIG", "default 10".
    for (const [re, want, label] of [
      [/(\d+)\s+for\s+CODE\/MIXED/g, code, "CODE/MIXED"],
      [/(\d+)\s+for\s+DOCS\/CONFIG/g, nonCode, "DOCS/CONFIG"],
      [/default\s+(\d+)/g, code, "default"],
    ]) {
      if (want === undefined || want === null) continue;
      for (const m of text.matchAll(re)) {
        checked += 1;
        if (Number(m[1]) === want) continue;
        failures.push(
          `${doc}: states the ${label} fix-loop cap is ${m[1]}, but customize.toml ships ${want}\n` +
            `      context: ${m[0]}`,
        );
      }
    }
  }
  // max_turns_per_story — only in pm-execute, pm-plan, pm-sync (pm-help omitted by design)
  {
    const seen = new Map();
    for (const skill of ["l3io-pm-execute", "l3io-pm-plan", "l3io-pm-sync"]) {
      const p = `skills/${skill}/customize.toml`;
      if (!exists(p)) continue;
      const v = tomlInt(read(p), "max_turns_per_story");
      if (v !== null) seen.set(skill, v);
    }
    const values = new Set(seen.values());
    if (values.size > 1) {
      failures.push(
        `customize.toml: 'max_turns_per_story' disagrees across PM skills — ` +
          [...seen].map(([s, v]) => `${s}=${v}`).join(", "),
      );
    }
    if (values.size === 1) {
      const cap = [...values][0];
      for (const doc of LIVE_DOCS) {
        const text = read(doc)
          .split("\n")
          .filter((l) => l.includes("max_turns_per_story"))
          .join("\n");
        if (!text) continue;
        for (const m of text.matchAll(/`(\d+)`/g)) {
          checked += 1;
          if (Number(m[1]) === cap) continue;
          failures.push(
            `${doc}: states max_turns_per_story default is ${m[1]}, ` +
              `but customize.toml ships ${cap}\n      context: ${m[0]}`,
          );
        }
      }
    }
  }

  if (verbose) console.log(`  config-values:  ${checked} restated value(s) checked against customize.toml`);
}


// ---------------------------------------------------------------------------
// 6. --status values named in skill phrase tables are real state folders.
//
// The skills translate what a user says ("what's active", "everything") into a --status
// filter. Those values are folder names, so a typo or a renamed folder silently produces a
// usage error at the moment someone asks for a narrowed view — the least convenient time.
// ---------------------------------------------------------------------------
const STATUS_FOLDERS = ["planned", "active", "archived"];
const PHRASE_TABLE_FILES = [
  "skills/l3io-pm-help/SKILL.md",
  "skills/l3io-util-doctor/SKILL.md",
];

function checkStatusValues() {
  let checked = 0;
  for (const rel of PHRASE_TABLE_FILES) {
    if (!exists(rel)) continue;
    // Only phrase-table rows. `--status` is also how set-status takes a VALUE
    // ("set-status --status done"), and `done` is a legitimate status but not a folder —
    // matching that was this check's first bug.
    const rows = read(rel).split("\n").filter((l) => l.trimStart().startsWith("|"));
    for (const m of rows.join("\n").matchAll(/--status\s+([a-z,\s-]+?)`/g)) {
      for (const value of m[1].split(",").map((v) => v.trim()).filter(Boolean)) {
        checked += 1;
        if (STATUS_FOLDERS.includes(value)) continue;
        failures.push(
          `${rel}: phrase table maps to '--status ${value}', which is not a state folder\n` +
            `      valid: ${STATUS_FOLDERS.join(", ")}`,
        );
      }
    }
  }
  // The folders the checker trusts must match the ones the CLI accepts.
  const declared = read(PM_STATUS).match(/^STATUS_DIRS\s*=\s*\(([^)]*)\)/m);
  if (declared) {
    const real = [...declared[1].matchAll(/"([a-z]+)"/g)].map((x) => x[1]).sort();
    if (real.join() !== [...STATUS_FOLDERS].sort().join()) {
      failures.push(
        `scripts/check-docs.mjs: STATUS_FOLDERS is [${STATUS_FOLDERS}] but ${PM_STATUS} ` +
          `declares STATUS_DIRS as [${real}] — update this checker`,
      );
    }
  }
  if (verbose) console.log(`  status-values:  ${checked} phrase-table filter value(s) checked`);
}

// ---------------------------------------------------------------------------
// 7. metrics-contract.md documents exactly the metrics in METRIC_FIELDS.
//
// The metric list has drifted before: the wall-clock name was renamed from a "time hours"
// spelling to elapsed_hours, and the old name survives in the file only as history (the
// migration's description of what it renames) and as the deprecated `--time-hours` CLI
// alias — never as a current metric. Checked both directions: a code metric the docs never
// mention as current, and the removed name resurfacing as if it were still live.
//
// The historical-vs-current line is drawn on the backtick: the metric table and prose
// throughout §2 name every current metric in backticks (`elapsed_hours`, `man_hours`, ...);
// the retired name is deliberately never given that treatment, appearing only as bare prose
// ("a differently-spelled wall-clock key ... a 'time hours' name") or inside the
// `--time-hours` flag name. So "does `` `time_hours` `` appear" cleanly separates "documented
// as a live metric" from "mentioned while explaining history" without forcing anyone to
// scrub accurate prose about the rename.
// ---------------------------------------------------------------------------
const METRICS_CONTRACT = "skills/_shared/metrics-contract.md";

function metricFields() {
  const src = read(PM_STATUS);
  const m = src.match(/^METRIC_FIELDS\s*=\s*\(([^)]*)\)/m);
  if (!m) return null;
  return m[1]
    .split(",")
    .map((s) => s.trim().replace(/^["']|["']$/g, ""))
    .filter(Boolean);
}

function checkMetricList() {
  const code = metricFields();
  if (!code || code.length === 0) {
    failures.push(`${PM_STATUS}: METRIC_FIELDS not found — has the metric tuple moved or been renamed?`);
    return;
  }

  const doc = read(METRICS_CONTRACT);
  const missing = code.filter((name) => !new RegExp("`" + name + "`").test(doc));
  if (missing.length) {
    failures.push(
      `${METRICS_CONTRACT}: does not document metric(s): ${missing.join(", ")}\n` +
        `      ${PM_STATUS} METRIC_FIELDS has: ${code.join(", ")} — add the missing metric(s) to §2, ` +
        `or if the code renamed/dropped one, update METRIC_FIELDS to match`,
    );
  }

  // time_hours is the retired wall-clock name (superseded by elapsed_hours). It may
  // legitimately appear un-backticked in historical prose or as the deprecated
  // --time-hours CLI alias; it must never reappear backticked as a live metric name.
  if (/`time_hours`/.test(doc)) {
    failures.push(
      `${METRICS_CONTRACT}: documents \`time_hours\` as a current metric, but it was renamed ` +
        `to elapsed_hours — ${PM_STATUS} METRIC_FIELDS is: ${code.join(", ")} (no time_hours)`,
    );
  }
  if (verbose) {
    console.log(`  metric-list:    ${code.length} metric(s) checked against ${METRICS_CONTRACT}`);
  }
}

// ---------------------------------------------------------------------------
// 8. The activation digest stays inside its byte budget.
//
// Why a byte count is worth gating: step-00-activate.md §8 exists BECAUSE the two deep
// references were too expensive to load per subagent (59,398 B -> 4,960 B at commit 7b9c0ca).
// Every subagent re-pays this section, and the orchestrator re-pays it on every prompt-cache
// re-creation, so growth here is multiplied by invocation count. It has already crept back to
// 8,580 B once, absorbing the five-metric model one reasonable-looking paragraph at a time.
//
// This is a RATCHET, not a target. Raising DIGEST_BUDGET is a deliberate act with a reason in
// the commit message; lowering it as content moves out is free and encouraged. The check says
// nothing about whether the content is good — only that adding to it is a decision someone
// made on purpose.
const DIGEST_FILE = "skills/_shared/steps/shared/step-00-digest.md";
// Raised 9,600 -> 10,400 on 2026-08-19 for the never-poll clause. Deliberate, per this
// check's own rule: the addition is measured at roughly $250 per run (one story spent ~130
// of its 263 turns on one-line status polls), which is worth far more than the ~650 B it
// costs every agent. The supporting evidence was pushed out to
// steps/execute/step-05-epic-loop.md §5 first, so what remains resident is the operative
// rule and a citation -- raising the number was the last resort, not the first.
//
// Raised 10,400 -> 12,400 on 2026-08-25 for the clauses and the read-cost section
// the production report (docs/superpowers/specs/2026-08-25-l3io-production-findings.md,
// findings 8 and 9) showed were missing: ending a turn on a question, arming a wait
// after the final line, and what a read actually costs. Each was observed live; two
// of them stranded a run.
//
// Sized ONCE for both this task's contract clauses (~750 B) and Task 6's "What a read
// costs" section (~900 B) against a 10,396 B baseline, rather than raised twice. A
// budget that yields once per commit is not a budget. Deliberate, per the
// raise-and-say-why instruction in the failure message below.
const DIGEST_BUDGET = 12600; // raised 200 B: agent_contract gains one turn-cap rule (159 B), load-bearing for subagents that cannot separately load references

function checkDigestSize() {
  if (!exists(DIGEST_FILE)) {
    failures.push(`${DIGEST_FILE}: not found — has the activation step moved?`);
    return;
  }
  const bytes = Buffer.byteLength(read(DIGEST_FILE), "utf8");
  if (bytes > DIGEST_BUDGET) {
    failures.push(
      `${DIGEST_FILE}: activation digest is ${bytes} B, over its ${DIGEST_BUDGET} B budget ` +
        `by ${bytes - DIGEST_BUDGET} B\n` +
        `      Every subagent re-pays this section and the orchestrator re-pays it on every\n` +
        `      prompt-cache re-creation. Either move the addition to a reference and cite it\n` +
        `      from the routing table, or raise DIGEST_BUDGET in scripts/check-docs.mjs and\n` +
        `      say why in the commit message.`,
    );
  }
  if (verbose) {
    console.log(`  digest-size:    ${bytes} B / ${DIGEST_BUDGET} B budget`);
  }
}

// ---------------------------------------------------------------------------
// 9. No runtime directive points at an authoring path.
//
// skills/_shared/ is where shared files are authored; it does not exist in an
// installed skill. A header note saying "source: skills/_shared/x.md" is fine and
// is how provenance is recorded. A directive telling an agent to GO READ
// skills/_shared/x.md sends it to a path that is not there. Ten of these shipped.
//
// The file set is derived by walking skills/ for *.md (reusing walkMarkdown, the same
// walker checkSectionRefs uses) rather than by a hand-kept list, so a new skill or a new
// doc file is covered automatically instead of silently sitting outside the check's view.
//
// "canonical" was dropped from the provenance keyword list: skills/l3io-util-doctor/SKILL.md
// said "see `skills/_shared/status-files.md` §10, the canonical contract)" — a directive
// (it tells the agent to go read the path) that calls the *target* canonical, not a note
// naming skills/_shared/ as *this file's own source*. Every real provenance line in the repo
// ("**Canonical source: `skills/_shared/x.md`.**", "(source: `skills/_shared/x.md`; ...)")
// already contains the word "source" on its own, so dropping "canonical" loses no coverage.
// ---------------------------------------------------------------------------
function allSkillDocs() {
  return walkMarkdown("skills");
}

function checkAuthoringPathDirectives() {
  const offenders = [];
  for (const file of allSkillDocs()) {
    const text = read(file);
    text.split("\n").forEach((line, i) => {
      if (!/skills\/_shared\//.test(line)) return;
      // Provenance notes name the source explicitly; directives do not.
      if (/\b(source|authored|generated from|synced from)\b/i.test(line)) return;
      offenders.push(`${file}:${i + 1}: ${line.trim()}`);
    });
  }
  if (offenders.length) {
    failures.push(
      `runtime directives point at authoring paths (skills/_shared/ does not exist ` +
        `in an installed skill):\n      ${offenders.join("\n      ")}\n` +
        `      Use the installed path (references/…, assets/…, steps/…), or mark the ` +
        `line as provenance by naming it as the source.`,
    );
  }
  if (verbose) {
    console.log(`  authoring-paths: ${offenders.length} offending directive(s)`);
  }
}

// ---------------------------------------------------------------------------
// 10. Every parser subcommand also appears in the script's own module docstring.
//
// Check 4 (cli-surface) compares docs/l3io-pm-reference.md against the parser; nothing
// compared the script's OWN docstring against itself. Six subcommands (dispatch,
// estimate-rollup, estimate-story, rates, sync-story-doc, usage) existed in the parser
// but were never added there, so the signature reference a reader opens first was
// missing a quarter of the CLI surface. Reuses cliSubcommands()/specAlignSubcommands() —
// the parser stays the only source of truth — rather than a hand-kept list, so a future
// subcommand is caught automatically instead of silently sitting outside this check's view.
//
// Runs once per script (pm-status.py, spec-align.py): each names its subcommands in its own
// module docstring, but in a different shape, so each gets its own matcher below --
// checkCliDocstringFor() is the one shared piece: look the subcommand set up, report what's
// missing, same message shape either way.
// ---------------------------------------------------------------------------
function scriptDocstring(path) {
  const src = read(path);
  const m = src.match(/"""([\s\S]*?)"""/);
  return m ? m[1] : "";
}

// pm-status.py lists one subcommand per line, each starting the line (after only
// indentation) with the bare name, e.g. "  verify        --state-root S ...". Anchoring to
// line-start is what keeps a prose mention elsewhere in the docstring from masking a
// genuinely removed entry: pm-status.py's own "Why this exists" section says "`verify` is a
// hard read-back gate" well before the formal list, but that line's first non-whitespace
// character is "*", not "verify", so it never matches.
function pmStatusHasSubcommand(doc, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|\\n)[ \\t]*${escaped}\\b`).test(doc);
}

// spec-align.py instead names every subcommand inline, in one run-on "Subcommands: a, b,
// c." sentence -- pm-status.py's line-start anchor would only ever match that sentence's
// first name. Isolate the sentence first (spec-align.py's own "Exit codes" paragraph
// mentions "lease" too, so matching the whole docstring could mask a removed entry the same
// way), then a plain word-boundary match inside just that sentence is safe.
function specAlignHasSubcommand(doc, name) {
  const m = doc.match(/Subcommands:[\s\S]*?\n[ \t]*\n/);
  const section = m ? m[0] : doc;
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`).test(section);
}

function checkCliDocstringFor(path, subcommands, hasSubcommand) {
  const doc = scriptDocstring(path);
  if (!doc) {
    failures.push(`${path}: no module docstring found — has it moved or been removed?`);
    return;
  }
  const missing = [...subcommands].filter((name) => !hasSubcommand(doc, name));
  if (missing.length) {
    failures.push(
      `${path}: module docstring's Subcommands list is missing ${missing.length} ` +
        `subcommand(s) the parser defines: ${missing.sort().join(", ")}\n` +
        `      Add a Subcommands entry for each, matching the existing terse style — ` +
        `real flags, required vs optional, a parenthetical note for non-obvious behaviour.`,
    );
  }
  if (verbose) {
    console.log(`  cli-docstring:  ${subcommands.size} subcommand(s) checked against ${path}'s module docstring`);
  }
}

function checkCliDocstring() {
  checkCliDocstringFor(PM_STATUS, cliSubcommands(), pmStatusHasSubcommand);
  checkCliDocstringFor(SPEC_ALIGN, specAlignSubcommands(), specAlignHasSubcommand);
}

// ---------------------------------------------------------------------------
// 11. Every append-issue invocation records where its finding lives.
//
// Caught in practice: five of seven producers appended backlog items with no --description,
// and epic closure told the agent to append in prose with no --source at all -- so most items
// pointed nowhere, and nothing could later tell whether one was already fixed. The file set is
// walked from skills/ (allSkillDocs), never listed by hand, so a producer added in a new file or
// directory is covered on arrival.
//
// Covered. An invocation is any logical line (physical lines joined on a trailing `\`), fenced
// or not, in which a pm-status token (`{pm_status}` or `pm-status.py`) is followed by
// `append-issue` and at least one `--` flag.
//
// Fences. Fence state is deliberately not tracked: a stray or four-backtick fence inverts a
// naive open/close toggle and hides every invocation after it (skills/l3io-util-doctor/SKILL.md
// carries one).
//
// Not detected.
//   - A prose instruction that names the verb without flags (issue-lifecycle spec §7 records
//     that gap).
//   - An invocation whose flags start on a following line without a trailing `\`. That isn't
//     valid shell.
// ---------------------------------------------------------------------------
function checkAppendIssuePointer() {
  const offenders = [];
  let checked = 0;
  for (const file of allSkillDocs()) {
    const lines = read(file).split("\n");
    for (let i = 0; i < lines.length; i++) {
      // Join physical lines continued with a trailing `\` into one logical line before
      // matching, so a token and its verb split across a continuation cannot escape the check.
      let text = lines[i];
      let j = i;
      while (/\\\s*$/.test(text) && j + 1 < lines.length) {
        text = text.replace(/\\\s*$/, "");
        j += 1;
        text += " " + lines[j];
      }
      if (!/(pm_status\}|pm-status\.py)\S*\s+append-issue\s+--/.test(text)) {
        continue;
      }
      checked += 1;
      const missing = ["--source", "--description"].filter((flag) => !text.includes(flag));
      if (missing.length) {
        offenders.push(`${file}:${i + 1}: append-issue without ${missing.join(" and ")}`);
      }
      i = j;
    }
  }
  if (offenders.length) {
    failures.push(
      `backlog producers must record where each finding lives:\n      ` +
        `${offenders.join("\n      ")}\n` +
        `      Pass --source "<phase> (<finding id>)" and --description "See <report path>".`,
    );
  }
  if (verbose) console.log(`  append-issue-pointer: ${checked} invocation(s) checked`);
}

// ---------------------------------------------------------------------------
// 12. pm-status.py stays within the size limit ADR-0001 sets.
//
// The number, and the check itself, are owned by docs/adr/0001-pm-status-single-self-installed-
// file.md's Amendment (2026-09-11): the ~6,000-line prose trigger fired unnoticed, so the
// revisit point is now a hard, mechanically enforced line count instead of a number that only
// lives in an ADR's prose. Raising PM_STATUS_LINE_LIMIT is a decision for that ADR, not a
// number to move here on its own.
const PM_STATUS_LINE_LIMIT = 8000;

function checkPmStatusSize() {
  // Newline count, matching `wc -l` -- not split("\n").length, which overcounts by one on
  // any file (all of them) that ends with a trailing newline.
  const lines = (read(PM_STATUS).match(/\n/g) || []).length;
  if (lines > PM_STATUS_LINE_LIMIT) {
    failures.push(
      `${PM_STATUS}: ${lines} lines, over the ${PM_STATUS_LINE_LIMIT}-line limit ` +
        `docs/adr/0001-pm-status-single-self-installed-file.md sets by ${lines - PM_STATUS_LINE_LIMIT}\n` +
        `      Revisit the ADR's options (Option C, a bundler, is the first candidate) before\n` +
        `      raising PM_STATUS_LINE_LIMIT in scripts/check-docs.mjs.`,
    );
  }
  if (verbose) console.log(`  pm-status-size: ${lines} / ${PM_STATUS_LINE_LIMIT} line limit`);
}

// ---------------------------------------------------------------------------
// 13. spec-align.py's contract with the docs it mirrors.
//
// Its spec kinds are copied from doctor's layout-cleanup heuristic 5 (the spec says one source
// of truth), and its DIMENSIONS must be the six headings the enrichment prompt tells the agent
// to write -- check-pointers rejects any other name, so a drift here blocks every story.
// ---------------------------------------------------------------------------
const LAYOUT_CLEANUP = "skills/l3io-util-doctor/steps/layout-cleanup.md";
const STORY_PREP = "skills/_shared/steps/sprint/step-02-story-prep.md";
const KIND_LABELS = { architecture: "Architecture", prd: "Requirements / PRD", ux: "UX spec" };

function pyTuple(src, name) {
  const m = src.match(new RegExp(`^${name} = \\(([\\s\\S]*?)^\\)`, "m"));
  return m ? m[1] : null;
}

function checkSpecAlignContract() {
  if (!exists(SPEC_ALIGN)) return;
  const src = read(SPEC_ALIGN);
  const kindsBlock = pyTuple(src, "KINDS");
  const dimsBlock = pyTuple(src, "DIMENSIONS");
  if (!kindsBlock || !dimsBlock) {
    failures.push(`${SPEC_ALIGN}: KINDS or DIMENSIONS is no longer a literal tuple`);
    return;
  }
  const kinds = {};
  for (const m of kindsBlock.matchAll(/\(\s*"([a-z]+)",\s*\(([^)]*)\)\s*\)/g)) {
    kinds[m[1]] = [...m[2].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort();
  }
  const doctor = read(LAYOUT_CLEANUP).split("\n");
  for (const [kind, label] of Object.entries(KIND_LABELS)) {
    const line = doctor.find((l) => l.includes(`**${label}**:`));
    const theirs = line ? [...line.matchAll(/`([^`]+)`/g)].map((m) => m[1]).sort() : [];
    const ours = kinds[kind] || [];
    if (JSON.stringify(theirs) !== JSON.stringify(ours)) {
      failures.push(`${kind} patterns differ: ${SPEC_ALIGN} has [${ours.join(", ")}], ` +
        `${LAYOUT_CLEANUP} heuristic 5 has [${theirs.join(", ")}]`);
    }
  }
  const dims = [...dimsBlock.matchAll(/"([^"]+)"/g)].map((x) => x[1]);
  const lines = read(STORY_PREP).split("\n");
  const at = lines.findIndex((l) => /^\s*## Technical acceptance criteria\s*$/.test(l));
  if (at < 0) {
    failures.push(`${STORY_PREP}: no '## Technical acceptance criteria' layout block in the ` +
      `enrichment prompt — ${SPEC_ALIGN} check-pointers requires it`);
    return;
  }
  const prompt = [];
  for (const l of lines.slice(at + 1)) {
    if (/^\s*## /.test(l) || /^\s*```/.test(l) || prompt.length === dims.length) break;
    const m = l.match(/^\s*### (.+?)\s*$/);
    if (m) prompt.push(m[1]);
  }
  if (JSON.stringify(prompt) !== JSON.stringify(dims)) {
    failures.push(`dimensions differ: ${SPEC_ALIGN} DIMENSIONS is [${dims.join(", ")}], the ` +
      `enrichment prompt in ${STORY_PREP} lays out [${prompt.join(", ")}]`);
  }
  if (verbose) console.log(`  spec-align-contract: ${Object.keys(KIND_LABELS).length} kinds, ${dims.length} dimensions`);
}

// ---------------------------------------------------------------------------
// 14. No runtime directive names the old per-epic ADR home.
//
// ADR-0005 makes docs/adr/ the one home; spec-align.py adrs lists an epic's ADRs. A step file
// still globbing epic-*/arch/*.md would hand a reviewer only the ADRs nobody has migrated.
// Scope is every markdown file under skills/ (walked, not listed). Allowed: the migration mode
// and the health check that detects the old home, plus any line that calls it legacy/old.
// arch/arch-gate-review.md is a review, not an ADR, and stays legal.
// ---------------------------------------------------------------------------
const ADR_OLD_HOME = /arch\/adr-|arch\/\*\.md/;
const ADR_OLD_HOME_ALLOWED = new Set([
  "skills/l3io-util-doctor/steps/migrate-adrs.md",
  "skills/l3io-util-doctor/steps/health-check.md",
]);
const ADR_OLD_HOME_QUALIFIER = /\b(old home|old per-epic home|legacy|migrat\w*)\b/i;

function checkAdrHome() {
  const offenders = [];
  for (const rel of walkMarkdown("skills")) {
    if (ADR_OLD_HOME_ALLOWED.has(rel.split(path.sep).join("/"))) continue;
    read(rel).split("\n").forEach((line, i) => {
      const m = ADR_OLD_HOME.exec(line);
      if (!m) return;
      // The qualifier must introduce the path within the SAME SENTENCE. A sentence break is a
      // period followed by whitespace and a capital, so "e.g." and a filename such as
      // `adr-0001-x.md` do not end the sentence. An earlier `[^.]{0,60}$` form treated every
      // period as a break and wrongly flagged legitimate prose.
      const sentences = line.split(/(?<=\.)\s+(?=[A-Z])/);
      let off = 0;
      for (const s of sentences) {
        const start = line.indexOf(s, off);
        off = start + s.length;
        if (m.index >= start && m.index < start + s.length) {
          if (ADR_OLD_HOME_QUALIFIER.test(s.slice(0, m.index - start))) return;
          break;
        }
      }
      offenders.push(`${rel}:${i + 1}: ${line.trim()}`);
    });
  }
  if (offenders.length) {
    failures.push(`runtime directives name the old per-epic ADR home:\n      ` +
      `${offenders.join("\n      ")}\n      ADRs live in {project-root}/docs/adr/ ` +
      `(docs/adr/0005-one-adr-home.md); list an epic's with \`{spec_align} adrs --epic\`.`);
  }
  if (verbose) console.log(`  adr-home:       ${offenders.length} offending directive(s)`);
}

// ---------------------------------------------------------------------------
// 15. The doctor's stated mode count equals the number of modes it actually has.
//
// The count is DERIVED three ways from the source of truth -- the steps/ directory, the
// routing table, and the Modes list -- and those three must agree; a disagreement means a
// mode file with no routing row, or a row with no file. Only the two *claim sites* are named
// here, because "is this sentence a live claim or frozen history?" cannot be derived
// mechanically: docs/upgrading.md and the decision log deliberately keep stale counts as
// release history, and CLAUDE.md's "fifteen procedures" is tied to a past measurement.
//
// Caught in practice: the count was bumped seventeen->eighteen when it should have gone
// eighteen->nineteen, and stayed wrong because nothing compared it to anything.
// ---------------------------------------------------------------------------
const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
  "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
  "seventeen", "eighteen", "nineteen", "twenty", "twenty-one", "twenty-two", "twenty-three",
  "twenty-four", "twenty-five"];
const DOCTOR_DIR = "skills/l3io-util-doctor";

function checkDoctorModeCount() {
  const steps = fs.readdirSync(path.join(repoRoot, DOCTOR_DIR, "steps"))
    .filter((f) => f.endsWith(".md"));
  const skill = read(`${DOCTOR_DIR}/SKILL.md`);
  const rows = [...skill.matchAll(/^\| `[^|]+` \| `steps\/[a-z-]+\.md`/gm)].length;
  const referenced = new Set([...skill.matchAll(/steps\/([a-z-]+)\.md/g)].map((m) => m[1]));
  if (new Set([steps.length, rows, referenced.size]).size !== 1) {
    failures.push(`${DOCTOR_DIR}: mode count derivations disagree — ${steps.length} steps/ ` +
      `file(s), ${rows} routing row(s), ${referenced.size} file(s) referenced by SKILL.md; ` +
      `a mode is a file plus a table row`);
    return;
  }
  const n = steps.length;
  const flat = (s) => s.replace(/\s+/g, " ");
  const claims = [
    ["CLAUDE.md", /each of its ([a-z-]+) modes lives in its own `steps\/` file/,
      flat(read("CLAUDE.md")), n, "modes"],
    [`${DOCTOR_DIR}/SKILL.md`, /carries ([a-z-]+) procedures and a run needs one/,
      flat(skill), n, "procedures"],
    [`${DOCTOR_DIR}/SKILL.md`, /invocation for ([a-z-]+) it would not execute/,
      flat(skill), n - 1, "procedures not executed"],
  ];
  for (const [file, re, text, expect, what] of claims) {
    const m = text.match(re);
    if (!m) {
      failures.push(`${file}: the ${what} claim was not found — has the sentence been ` +
        `reworded? check 15 must be updated with it`);
      continue;
    }
    const got = NUMBER_WORDS.indexOf(m[1].toLowerCase());
    if (got !== expect) {
      failures.push(`${file}: says "${m[1]}" ${what}, but the doctor has ${n} mode(s) ` +
        `(${expect} expected here) — counted from ${DOCTOR_DIR}/steps/ and the routing table`);
    }
  }
  if (verbose) console.log(`  doctor-mode-count: ${n} mode(s), ${claims.length} claim(s)`);
}

// ---------------------------------------------------------------------------
// 16. Every bmad-* name a runtime directive uses is declared in one inventory.
//
// Three BMad releases renamed or removed skills this package dispatches and nothing noticed:
// bmad-create-story and bmad-dev-story became shims, bmad-review-adversarial-general merged
// into bmad-review, and bmad-check-implementation-readiness was removed. A clean v6.12.0
// install could not run the dev loop, and the failure was invisible until someone installed
// BMad by hand and looked.
//
// A removed name may still appear where the mention is self-evidently historical, but the
// evidence must be on the SAME LINE. Check 1 widens to a ±4-line window; dry-run here, that
// window excused l3io-util-doctor/SKILL.md:84 because an unrelated routing row nearby said
// "remove migration backup files". An accidental pass is how a guard starts crying wolf.
//
// Scope is derived by walking skills/ markdown and every skills/<dir>/assets/module.yaml, never
// a list.
// ---------------------------------------------------------------------------
const DEP_INVENTORY = "skills/l3io-util-doctor/assets/bmad-dependencies.json";
const BMAD_TOKEN_RE = /(?<![\w-])bmad-[a-z0-9-]+/g;
const DEP_STATUSES = ["required", "optional", "deprecated", "removed", "not-a-skill"];

// A line that BINDS a name as the chosen agent, as opposed to merely probing for it.
// Three independent signals, each observed on its own — a line needs only one to count as a
// preference:
//   (1) PREFERENCE_RE   — the binding verbs the step files actually use (bind/prefer/spawn/
//       invoke/dispatch).
//   (2) BINDING_ASSIGNMENT_RE — a `{placeholder}` = value assignment (`` `{enrich_agent}` = the
//       legacy `bmad-create-story` ``), which carries no binding verb at all.
//   (3) HEADING_RE      — a Markdown heading naming the deprecated skill, which scopes an
//       entire section to it (`## Overlay for the story enricher — legacy `bmad-create-story``).
// This is NOT exhaustive: a sentence that names a deprecated skill as the thing in use without
// any verb, assignment, or heading (e.g. a plain declarative "the enricher is `bmad-create-
// story`" with no `=`) still escapes all three and is not observed by this check.
const PREFERENCE_RE = /\b(?:bind|prefer(?:red|s)?|spawn|invoke|dispatch)\b/i;
const BINDING_ASSIGNMENT_RE = /`\{[\w-]+\}`\s*=/;
const HEADING_RE = /^#{1,6}\s/;

function checkBmadDependencyInventory() {
  if (!exists(DEP_INVENTORY)) {
    failures.push(`${DEP_INVENTORY}: missing — it is the one place every bmad-* name is declared`);
    return;
  }
  let inv;
  try {
    inv = JSON.parse(read(DEP_INVENTORY));
  } catch (e) {
    failures.push(`${DEP_INVENTORY}: not valid JSON — ${e.message}`);
    return;
  }
  const byName = new Map();
  for (const e of inv.skills ?? []) {
    if (!e.name) { failures.push(`${DEP_INVENTORY}: an entry has no name`); continue; }
    if (byName.has(e.name)) { failures.push(`${DEP_INVENTORY}: duplicate entry '${e.name}'`); continue; }
    byName.set(e.name, e);
    if (!DEP_STATUSES.includes(e.status)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' has unknown status '${e.status}'`);
    } else if ((e.status === "required" || e.status === "optional") && !e.module) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is ${e.status} but names no module`);
    } else if (e.status === "deprecated" && !(e.replaced_by && e.deprecated_in)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is deprecated but lacks replaced_by/deprecated_in`);
    } else if (e.status === "removed" && !(e.replaced_by && e.removed_in)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is removed but lacks replaced_by/removed_in`);
    } else if (e.status === "not-a-skill" && !e.reason) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is not-a-skill but gives no reason`);
    }
  }
  for (const e of byName.values()) {
    if (e.fallback && !byName.has(e.fallback)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' falls back to '${e.fallback}', not declared`);
    }
  }

  const sources = [...walkMarkdown("skills")];
  for (const entry of fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const rel = `skills/${entry.name}/assets/module.yaml`;
    if (exists(rel)) sources.push(rel);
  }

  let checked = 0;
  for (const rel of sources) {
    const lines = read(rel).split("\n");
    for (let i = 0; i < lines.length; i += 1) {
      for (const m of lines[i].matchAll(BMAD_TOKEN_RE)) {
        const name = m[0];
        checked += 1;
        const e = byName.get(name);
        if (!e) {
          failures.push(`${rel}:${i + 1}: names '${name}', not declared in ${DEP_INVENTORY}\n` +
            `      context: ${lines[i].trim().slice(0, 110)}`);
          continue;
        }
        if (e.status === "deprecated") {
          const line = lines[i];
          const isProbe = /(?:^|[^\w-])ls\s+\S*\.claude\//.test(line);
          // Named `l3io-deprecation-exempt`, not `bmad-*` — a `bmad-*`-prefixed marker would
          // itself match BMAD_TOKEN_RE below and fail as an undeclared name.
          const exempt = /l3io-deprecation-exempt:\s*phase-3/.test(line);
          const isPreference = PREFERENCE_RE.test(line) || BINDING_ASSIGNMENT_RE.test(line) ||
            HEADING_RE.test(line);
          if (!isProbe && !exempt && isPreference) {
            failures.push(`${rel}:${i + 1}: prefers deprecated skill '${name}' — replaced by ` +
              `'${e.replaced_by}' in ${e.deprecated_in}. Preferring a frozen skill is how this ` +
              `package stopped running its own replacement.\n` +
              `      context: ${line.trim().slice(0, 110)}`);
          }
          continue;
        }
        if (e.status !== "removed") continue;
        const line = lines[i];
        // Three arms, and BOTH pattern arms must be token-bounded, not substring tests:
        // (c) is load-bearing — the tolerance design REQUIRES step files to probe for the
        // pre-6.12 names, so a rule forbidding the name would forbid the fix, and a probe line
        // cannot dispatch anything. But `ls` has to be the command and the .claude/ path has to
        // be its argument: a bare line.includes("ls ") is satisfied by "tools ", "details " or
        // "controls ", so a genuine dispatch mentioning .claude/ anywhere would be excused.
        // (b) has the same shape of hole — "bmad-ux-review".includes("bmad-ux") is true, which
        // would let the guard wave through its own worst case — and replaced_by is interpolated
        // into a RegExp, so it is escaped: a metacharacter in a future value must fail this
        // check cleanly rather than throw out of it.
        const isProbe = /(?:^|[^\w-])ls\s+\S*\.claude\//.test(line);
        const escaped = e.replaced_by.split(" ")[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const replacedByToken = new RegExp(`(?<![\\w-])${escaped}(?![\\w-])`);
        const historical = isProbe || replacedByToken.test(line) ||
          /\blegacy\b|\bhistorical\b/i.test(line);
        if (historical) {
          notes.push(`${rel}:${i + 1}: names removed skill '${name}' as history — allowed`);
          continue;
        }
        failures.push(`${rel}:${i + 1}: dispatches removed skill '${name}' — replaced by ` +
          `'${e.replaced_by}'. If the mention is historical, say so on the same line.\n` +
          `      context: ${line.trim().slice(0, 110)}`);
      }
    }
  }
  if (verbose) {
    console.log(`  bmad-dependency-inventory: ${checked} reference(s), ${byName.size} declared`);
  }
}

// ---------------------------------------------------------------------------
// 17. No runtime directive under skills/, and no CI step under .github/workflows/, invokes a
// PEP-723 script with python3.
//
// BMad's own convention is 100% `uv run` -- every core script carries a PEP-723 header and
// python3 bypasses it, either failing outright (no ambient interpreter has the deps) or
// silently running against whatever version happens to be ambient instead of what the header
// declares.
//
// HOW THIS IS DECIDED. A workflow file is parsed as YAML (`yaml`), every `run:` script it
// carries is parsed as shell (`mvdan-sh`, the JS build of mvdan/sh -- the parser `shfmt` and
// `shellcheck`-adjacent tooling use), and the rule is expressed over the resulting argv
// arrays: a command that names a python3-ish interpreter and hands it a `.py` path (or a
// `{pm_status}`/`{spec_align}` helper token) must be a `uv run` carrying a provisioning flag.
// Nothing here splits a line on `&&`/`;`/`|` by regex, and nothing reads the YAML line by
// line; quoting, escaping, `$( )` substitution, backslash continuations, heredocs, `if`/`then`
// blocks, `VAR=value` prefixes and multi-line block scalars are all the parsers' problem, not
// this file's.
//
// WHY IT WAS REBUILT. Four fix rounds hardened a regex predicate plus a `String.split(/&&|;|\||&/)`
// standing in for a shell lexer, and each round's own review found the next hole. The split was
// quote-unaware (`NOTE='x & uv run --with y' python3 S.py` exited 0), the exemption could not
// see through `$( )` (`uv run --with x echo "$(python3 S.py)"` exited 0), and the line-at-a-time
// read produced the mirror error on correct commands -- `timeout 600 uv run --with x python3
// S.py`, an `if`-wrapped invocation, a quoted YAML scalar and `uv  run` with two spaces were all
// red. None of those is a regex-anchoring problem; they are all "this needs a real parser",
// which global rule 1 says to buy rather than write. The parsers cost one `npm ci` step in
// .github/workflows/checks.yml. See docs/adr/0007-ci-installs-npm-dependencies.md.
//
// TWO CORPORA, TWO PREDICATES, ONE RULE. The shared rule is `pep723Offences()` below, and both
// corpora apply it. They differ only in what makes a line a candidate, because they are not the
// same kind of text:
//
//   .github/workflows/**  is executable. Every `run:` script is fed to the shell parser and the
//     rule alone decides. A `run:` body that does not parse as shell is a FAILURE, not a skip --
//     the fail-closed direction for a file CI actually executes. So is a workflow file that does
//     not parse as YAML.
//
//   skills/**.md is prose that quotes shell, decorated with bullets, table pipes and backticks
//     that are not shell at all. A candidate line is still found with PY_INVOKE_RE, exactly as
//     before, because that regex reaches a `- python3 {pm_status} …` bullet or a `| `python3
//     x.py` |` table cell that no shell parser will accept; the rule then decides whether the
//     candidate is exempt. A candidate whose line does not parse as shell is NOT exempted --
//     same fail-closed direction, and the same verdict the old textual exemption reached. Prose
//     that is not a candidate is never parsed, so a sentence like `python3 (3.11+) is needed to
//     run a.py` (not valid shell) is never even offered to the parser.
//
// Scope was widened to include .github/workflows/**: a CI step once ran
// `python3 -m pip install ... && python3 skills/_shared/tests/test-pm-status.py`, invoking a
// PEP-723 script (test-pm-status.py) against an ambient interpreter it had just provisioned
// by hand, while every sibling step in the same workflow used `uv run`. This scan only ever
// walked skills/, so a CI YAML file was invisible to it even though CI is where these scripts
// are actually invoked, and actually matter, most. See the l3io-customization-layer Task 9
// ruling for the found instance.
//
// Tolerance: skills/_shared/steps/shared/step-00-activate.md documents "If `uv` is
// unavailable, use `python3` instead" as an explicit fallback for self-install, and
// skills/l3io-util-doctor/assets/migrate-state.md and bootstrap-state.md restate the same
// fallback. A rule that forbade the word `python3` outright would forbid its own escape
// hatch, so a line naming `uv`+`unavailable` or the word `fallback`, ON THE SAME LINE as the
// invocation, is exempted from this check. PY_FALLBACK_QUALIFIER is MARKDOWN-ONLY and stays
// that way (fix round 2, N-3): a workflow `run:` line is executable, not prose describing an
// escape hatch, and `run: python3 …test-pm-status.py  # fallback until uv lands` used to pass
// on it. Exactly three real sites under skills/ rely on the tolerance -- bootstrap-state.md:266
// and migrate-state.md:484,599, all three restating step-00-activate.md's documented
// `uv`-unavailable fallback for {pm_status}.
//
// DELIBERATE OVER-APPROXIMATION, stated because it is visible in the output: the rule reads
// "no command line hands a .py to python3 outside a provisioned uv run", and it does NOT
// require the interpreter to be argv[0]. So `echo 'a & uv run --with y' python3 s.py` and
// `grep -q 'x | uv run --with y' python3 s.py` are reported although the shell would run
// `echo`/`grep` and never python3. Both were recorded bypasses of the old splitter, both are
// pathological shapes in a `run:` step or a directive, and the fail-closed direction is the
// right one for a guard -- narrowing to argv[0] would also drop the markdown reach that keeps
// a `- python3 {pm_status} …` bullet and a `| `python3 x.py` |` table cell caught.
//
// These offenders get a DIFFERENT message ("contains an unquoted python3 <script> sequence"),
// because saying a `grep` command "invokes a PEP-723 script" would be a false statement in the
// one place a reader checks. The narrow cost is measurable and was measured: the rule compares
// argv WORDS, so `grep -rn "python3 setup.py" skills/` and `echo "never python3 foo.py"` are
// both clean -- only an UNQUOTED `… python3 x.py` tail trips it. Cost on this repo: zero lines.
// There is deliberately NO escape hatch on the workflow side (PY_FALLBACK_QUALIFIER is
// markdown-only, and stays that way). If this ever fires on legitimate workflow content, quote
// the text or restructure the step; do not add a silencer without first measuring, the way this
// paragraph was measured.
//
// Known gaps (listed rather than left to look complete):
//   - a command that reaches python3 through ANOTHER program's own argument parsing or through
//     a second file -- `bash -c 'python3 S.py'`, `sh -lc …`, `make test`, a script that runs a
//     script. The rule sees the argv it is given and does not follow a command into another
//     program's conventions or into another file. (`xargs python3 S.py` IS caught: `python3` is
//     an argv word of the command being read, and the over-approximation above covers it. This
//     entry used to claim otherwise, which understated real coverage -- fix round 1, L-1.)
//   - a variable whose value is not statically known: `PY=$(which python3); $PY S.py`, or one
//     exported by an earlier `run:` step or by `env:` at job level. Literal in-script
//     assignments (`PY=python3; $PY S.py`) ARE resolved.
//   - `python3 -m <runner> <script>.py` is judged by the runner's FIRST non-flag argument, so
//     `-m pytest S.py` is caught and `-m pip install … build.py` is correctly not. A runner
//     that takes the script somewhere else in its argv is missed, including behind one of the
//     runner's OWN value-taking flags (`-m pytest -W ignore::X S.py`): after `-m`, the flags
//     belong to the module, so python3's arity table deliberately stops applying and a flag's
//     separate value reads as the first non-flag argument.
//   - markdown candidacy still rests on PY_INVOKE_RE, so an invocation spelled in a way that
//     regex does not match is not offered to the rule at all in the markdown corpus.
//
// WHAT THIS WAS TESTED AGAINST, so the claim above is a measurement and not a belief (same
// discipline check 21's header follows). A mutation sweep over every decision point in this
// section ran 81 mutations: 51 turned the suite RED, 8 were provably equivalent (no verdict
// changed), and 21 stayed GREEN while changing a real verdict -- every one of those a gap in
// what the suite PINNED, none a defect in the rule. Fix round 2 closed 7 of the 21: the
// provisioning flag's NAME (`--with-coverage` in front of the interpreter), every entry of
// PY_VALUE_OPTS in both directions, quoting at the interpreter/flag/target positions, the
// `.yaml` half of the workflow scope, and the direct-versus-indirect wording of each markdown
// decoration shape. The 14 left open are recorded in the fix-round-2 review and are knowingly
// parked: they are message-only flips, `uv tool run`, `--use-python3`, `python3 -`, the
// block-scalar line offset, and spliced-interpreter variable resolutions -- none changes a
// verdict on any content this repo has. Re-derive by mutating any single decision below and
// running `npm run test:scripts`.
// ---------------------------------------------------------------------------
const PY_INVOKE_RE = /(?<![\w-])python3(?:\.\d+)?(?:\s+-\S+(?:\s+\S+)?)*\s+(?:"?\{(pm_status|spec_align)\}|\S*\.py)(?![\w-])/;
const PY_FALLBACK_QUALIFIER = /\buv\b[^.]*\bunavailable\b|\bfallback\b/i;

const { syntax } = sh;
const shellParser = syntax.NewParser();

// `python3`, `python3.12`, `/usr/bin/python3` -- the whole token, never a substring, so
// `--use-python3` (an option name) and `python3.` (a sentence) are not interpreters.
const PY_INTERPRETER_RE = /^(?:\S*\/)?python3(?:\.\d+)?$/;
// The PEP-723 targets this check exists to protect: any `.py` path, plus the two helper
// tokens the skills spell instead of a path.
const PEP723_HELPER_RE = /^"?\{(?:pm_status|spec_align)\}"?$/;
const isPep723Target = (t) => typeof t === "string" && (t.endsWith(".py") || PEP723_HELPER_RE.test(t));
// CPython options that consume the NEXT argv entry. Taken from python3's own documented CLI
// rather than guessed, so `-X utf8 script.py` finds `script.py` and `-c 'code' script.py`
// correctly finds no executed script at all.
const PY_VALUE_OPTS = new Set(["-c", "-m", "-Q", "-W", "-X", "--check-hash-based-pycs"]);
// Commands that run another command: the invocation to judge is what follows them.
const WRAPPER_COMMANDS = new Set(["env", "sudo", "doas", "nice", "ionice", "nohup", "stdbuf",
  "time", "timeout", "command", "exec", "chrt", "setsid"]);
// uv's real provisioning flags -- the ones that make uv build an environment of its own.
// `--with-coverage` is not one of them; matching a bare `--with\b` used to accept it.
const UV_PROVISION_FLAG_RE = /^--with(?:-editable|-requirements)?(?:=|$)/;

// Flatten a parsed shell Word to the literal text the shell would produce, or null when part
// of it is an expansion whose value is not statically known (a command substitution, an
// arithmetic expansion, an unresolved parameter). Returning null rather than a partial string
// keeps a half-known token from ever comparing equal to `uv`, `run` or an interpreter name.
function wordLiteral(word, vars) {
  let text = "";
  let known = true;
  const visit = (parts) => {
    for (const part of parts || []) {
      const kind = syntax.NodeType(part);
      if (kind === "Lit") text += part.Value;
      else if (kind === "SglQuoted") text += part.Value;
      else if (kind === "DblQuoted") visit(part.Parts);
      else if (kind === "ParamExp" && !part.Exp && part.Param && vars.has(part.Param.Value)) {
        text += vars.get(part.Param.Value);
      } else known = false;
    }
  };
  visit(word.Parts);
  return known ? text : null;
}

// Every simple command in a shell script, as argv arrays, in source order. Commands nested in
// a `$( )` substitution, an `if`/`while` body or a function come out as their own entries --
// that is what makes the substitution and shell-block cases work without a special case here.
// A bare `NAME=value` command (assignments with no argv) sets a variable for the commands that
// follow it instead of producing one. Returns null when the script is not valid shell.
function shellCommands(script) {
  let file;
  try {
    file = shellParser.Parse(script, "run");
  } catch {
    return null;
  }
  const vars = new Map();
  const commands = [];
  syntax.Walk(file, (node) => {
    if (!node || syntax.NodeType(node) !== "CallExpr") return true;
    const args = node.Args || [];
    if (args.length === 0) {
      for (const assign of node.Assigns || []) {
        const name = assign.Name && assign.Name.Value;
        const value = assign.Value ? wordLiteral(assign.Value, vars) : "";
        if (name && value !== null) vars.set(name, value);
      }
      return true;
    }
    commands.push({ argv: args.map((w) => wordLiteral(w, vars)), line: node.Pos().Line() });
    return true;
  });
  return commands;
}

// Drop a leading run of wrapper commands and the options they carry, so the invocation being
// judged is the one that actually execs. `timeout 600 …`, `env FOO=1 …`, `nice -n 10 …` and
// `sudo -E …` all reduce to what they wrap.
function stripWrappers(argv) {
  let i = 0;
  while (i < argv.length && typeof argv[i] === "string" &&
         WRAPPER_COMMANDS.has(argv[i].replace(/^.*\//, ""))) {
    i += 1;
    while (i < argv.length && typeof argv[i] === "string" &&
           (/^-/.test(argv[i]) ||                            // an option
            /^[A-Za-z_][A-Za-z0-9_]*=/.test(argv[i]) ||      // env's NAME=value
            /^\d+(?:\.\d+)?[smhd]?$/.test(argv[i]))) {       // timeout's duration, nice's level
      i += 1;
    }
  }
  return argv.slice(i);
}

// Given argv that begins at a python3-ish interpreter, the PEP-723 target it executes, or null
// when it executes none. Models python3's own option handling: `-X utf8 s.py` runs `s.py`,
// `-c 'code' s.py` runs no script at all (s.py is just sys.argv[1]), and `-m runner s.py` runs
// a module -- judged by the module's first non-option argument, which catches `-m pytest s.py`
// without catching `-m pip install … build.py`.
function pythonTarget(argv) {
  let i = 1;
  while (i < argv.length) {
    const tok = argv[i];
    if (typeof tok !== "string" || tok === "-" || !tok.startsWith("-")) break;
    if (tok === "-c") return null;
    if (tok === "-m") {
      for (let j = i + 2; j < argv.length; j += 1) {
        if (typeof argv[j] !== "string" || argv[j].startsWith("-")) continue;
        return isPep723Target(argv[j]) ? argv[j] : null;
      }
      return null;
    }
    i += PY_VALUE_OPTS.has(tok) ? 2 : 1;
  }
  return isPep723Target(argv[i]) ? argv[i] : null;
}

// The rule, over one command's argv. Returns the offending target, or null.
//
// `uv run --with <deps> python3 <script>.py` is uv choosing and managing the interpreter
// itself and is exempt; `uv run python3 <script>.py` is NOT, because uv only reads a script's
// PEP-723 header when the script path is uv's own first argument -- without a provisioning
// flag nothing is installed and the header is honoured by nobody. The flag must sit between
// `run` and the interpreter: a `--with…` after the script is a script argument, not a uv flag.
function commandOffence(rawArgv) {
  const argv = stripWrappers(rawArgv);
  const pyIndex = argv.findIndex((t) => typeof t === "string" && PY_INTERPRETER_RE.test(t));
  if (pyIndex < 0) return null;
  const target = pythonTarget(argv.slice(pyIndex));
  if (!target) return null;
  const isUvRun = argv[0] === "uv" && argv[1] === "run";
  if (isUvRun &&
      argv.slice(2, pyIndex).some((t) => typeof t === "string" && UV_PROVISION_FLAG_RE.test(t))) {
    return null;
  }
  // `direct` separates what the shell WILL execute (the interpreter is the command, or uv is
  // running it) from the over-approximation above, where python3 is merely an argv word of
  // something else. The two get different messages: only the first is honestly described as
  // "invokes a PEP-723 script".
  return { target, direct: pyIndex === 0 || isUvRun };
}

// The failure text for one offending command. Kept next to commandOffence() so the claim and
// the condition that produced it cannot drift apart.
function offenceMessage(offence) {
  return offence.direct
    ? `invokes a PEP-723 script with python3 (use uv run instead): ${offence.target}`
    : `contains an unquoted \`python3 ${offence.target}\` sequence outside a provisioned ` +
      `\`uv run\` -- the checker does not try to prove it harmless; quote it or remove it`;
}

// Every offending command in a shell script. null means the script is not valid shell -- the
// caller decides what that means for its corpus.
function pep723Offences(script) {
  const commands = shellCommands(script);
  if (commands === null) return null;
  return commands
    .map((c) => ({ line: c.line, offence: commandOffence(c.argv) }))
    .filter((c) => c.offence !== null);
}

function* walkWorkflowFiles() {
  const abs = path.join(repoRoot, ".github", "workflows");
  if (!fs.existsSync(abs)) return;
  for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
    if (entry.isFile() && /\.ya?ml$/.test(entry.name)) {
      yield path.join(".github", "workflows", entry.name);
    }
  }
}

// Markdown: PY_INVOKE_RE picks the candidate line, the shared rule decides it.
function scanMarkdownForPep723(rel) {
  const offenders = [];
  read(rel).split("\n").forEach((line, i) => {
    if (!PY_INVOKE_RE.test(line)) return;
    if (PY_FALLBACK_QUALIFIER.test(line)) return;
    const offences = pep723Offences(line);
    if (offences !== null && offences.length === 0) return;
    // A line the shell parser could not read at all (markdown decoration) has no argv to
    // classify, so it takes the direct wording: PY_INVOKE_RE matched a python3-plus-script
    // sequence and nothing exempted it, which is exactly what that sentence says.
    const direct = offences === null || offences.some((o) => o.offence.direct);
    const detail = direct
      ? `invokes a PEP-723 script with python3 (use uv run instead)`
      : `contains an unquoted python3-plus-script sequence outside a provisioned \`uv run\` ` +
        `-- the checker does not try to prove it harmless`;
    offenders.push(`${rel}:${i + 1}: ${detail}: ${line.trim()}`);
  });
  return offenders;
}

// Workflows: the YAML document supplies the `run:` scripts, the shared rule decides them.
// Both parsers fail closed.
function scanWorkflowForPep723(rel) {
  const text = read(rel);
  const offenders = [];
  let doc;
  try {
    doc = YAML.parseDocument(text, { prettyErrors: true });
  } catch (e) {
    return [`${rel}: does not parse as YAML (${String(e.message).split("\n")[0]}) -- check 17 ` +
      `cannot read its run: steps`];
  }
  if (doc.errors.length > 0) {
    return [`${rel}: does not parse as YAML (${doc.errors[0].message.split("\n")[0]}) -- ` +
      `check 17 cannot read its run: steps`];
  }
  const lineOfOffset = (offset) => text.slice(0, offset).split("\n").length;

  YAML.visit(doc, {
    Pair(_key, pair) {
      if (!YAML.isScalar(pair.key) || pair.key.value !== "run") return;
      if (!YAML.isScalar(pair.value) || typeof pair.value.value !== "string") return;
      const script = pair.value.value;
      const startLine = lineOfOffset(pair.value.range ? pair.value.range[0] : pair.key.range[0]);
      // A block scalar's content begins on the line after its `|`/`>` indicator, so a command's
      // in-script line number maps onto the file. Any other scalar occupies one starting line
      // and may carry escapes, so the whole script is reported against that line.
      const isBlock = typeof pair.value.type === "string" && pair.value.type.startsWith("BLOCK");
      const offences = pep723Offences(script);
      if (offences === null) {
        offenders.push(`${rel}:${startLine}: this run: script does not parse as shell, so ` +
          `check 17 cannot rule on it: ${script.split("\n")[0].trim()}`);
        return;
      }
      for (const found of offences) {
        const line = isBlock ? startLine + found.line : startLine;
        offenders.push(`${rel}:${line}: ${offenceMessage(found.offence)}`);
      }
    },
  });
  return offenders;
}

function checkPep723Invocation() {
  const offenders = [
    ...[...walkMarkdown("skills")].flatMap(scanMarkdownForPep723),
    ...[...walkWorkflowFiles()].flatMap(scanWorkflowForPep723),
  ];
  if (offenders.length) {
    failures.push(`PEP-723 scripts reached without uv, bypassing their header-declared deps ` +
      `(each line says which of the two shapes it is):\n      ${offenders.join("\n      ")}`);
  }
  if (verbose) console.log(`  pep723-invocation: ${offenders.length} offending line(s)`);
}

// ---------------------------------------------------------------------------
// 18. The check count claimed in prose matches what this file actually runs.
//
// Modelled on check 15 (doctor-mode-count): derive the count two ways from the source of
// truth -- never type it -- and require the derivations agree before trusting either one to
// validate the prose. Reuses NUMBER_WORDS (defined above, for check 15).
//
// Derivation A: the numbered entries in this file's own header comment block (the "N. name"
// lines above "Usage:"). Derivation B: the check-function invocations at the bottom of the
// file. These are meant to agree one-for-one; the one check whose surface spans two scripts
// (pm-status.py and spec-align.py, check 4) is implemented as two functions, but the second
// (checkSpecAlignSurface) is called FROM checkCliSurface rather than as its own top-level
// statement, precisely so it does not inflate derivation B against derivation A's single "4."
// entry. A future check added to one list and not the other is caught here as a disagreement,
// not as a silently-wrong prose count three files downstream.
//
// Caught in practice: this exact scenario. CLAUDE.md and scripts/CLAUDE.md both said
// "check:docs runs seventeen checks" after an eighteenth check (pep723-invocation) was added
// and invoked, and nothing compared the prose to the file that would have disproved it.
// ---------------------------------------------------------------------------
const SELF_FILE = "scripts/check-docs.mjs";

function checkDocsCheckCount() {
  const src = read(SELF_FILE);
  const usageAt = src.indexOf("// Usage:");
  const header = usageAt < 0 ? src : src.slice(0, usageAt);
  const headerCount = [...header.matchAll(/^\/\/\s+(\d+)\.\s/gm)].length;
  const invoked = [...src.matchAll(/^check[A-Za-z0-9]+\(\);$/gm)].length;

  if (headerCount !== invoked) {
    failures.push(`${SELF_FILE}: check count derivations disagree — ${headerCount} numbered ` +
      `header entr${headerCount === 1 ? "y" : "ies"}, ${invoked} check function invocation(s) ` +
      `at the bottom of the file; a check was added to one and not the other`);
    return;
  }
  const n = headerCount;
  const flat = (s) => s.replace(/\s+/g, " ");
  const claims = [
    ["CLAUDE.md", /`check:docs` runs ([a-z-]+) checks/, flat(read("CLAUDE.md"))],
    ["scripts/CLAUDE.md", /numbers its ([a-z-]+) checks there/, flat(read("scripts/CLAUDE.md"))],
    // CONTRIBUTING.md's gate table stated the count too, and check 18 did not read it -- a
    // third copy of the same number with no guard behind it, which is how the first one
    // drifted. Added here rather than deleted from the doc: the number is useful where a
    // contributor meets the gate.
    ["CONTRIBUTING.md", /the code it describes — ([a-z-]+) checks/, flat(read("CONTRIBUTING.md"))],
  ];
  for (const [file, re, text] of claims) {
    const m = text.match(re);
    if (!m) {
      failures.push(`${file}: the check-count claim was not found — has the sentence been ` +
        `reworded? check 18 must be updated with it`);
      continue;
    }
    const got = NUMBER_WORDS.indexOf(m[1].toLowerCase());
    if (got !== n) {
      failures.push(`${file}: says "${m[1]}" checks, but ${SELF_FILE} runs ${n} (numbered ` +
        `header entries and invocations both agree on ${n})`);
    }
  }
  if (verbose) console.log(`  docs-check-count: ${n} check(s), ${claims.length} claim site(s)`);
}

// ---------------------------------------------------------------------------
// 19. The skill count, module count, and l3io-pm skill count claimed in prose match what
// skills/ actually has.
//
// Modelled on check 15 (doctor-mode-count): derive the counts from the source of truth --
// the skills/ directory and each skill's own module.yaml -- never type them, and require an
// unmatched claim sentence to fail rather than silently stop being checked.
//
// module.yaml now lives at each module's home (assets/module.yaml -- a dedicated *-setup skill
// for a multi-skill module, or the skill itself for a standalone one); codeOf() also reads the
// skill-root location so a not-yet-migrated module still counts. A module's home can exist
// before it is a full skill -- l3io-pm-setup carries assets/module.yaml from the day this
// relocation lands, but its SKILL.md does not arrive until a later task -- so "skills" counts
// only directories that carry a SKILL.md, while "modules" is derived from every module.yaml
// regardless. "pmSkills" then excludes the module's own home directory from its delivery
// skills, per check-module.mjs's convention that a home shared across multiple skills is a
// dedicated *-setup skill, never one of the module's own skills.
//
// Caught in practice: "seventeen checks" drifted because nothing compared it to anything
// (check 18 closed that gap); every other hand-written count here -- eight skills, four
// modules, four l3io-pm skills -- was exposed to the same failure mode and had not yet
// drifted only because no task had changed the numbers yet.
// ---------------------------------------------------------------------------
function derivedCounts() {
  const dirs = fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name.startsWith("l3io-"))
    .map((e) => e.name);
  // assets/module.yaml is the target module home; a skill-root module.yaml is a not-yet-
  // migrated module. Read both so this check survives a partial migration instead of silently
  // counting zero modules.
  const codeOf = (skill) => {
    for (const rel of [`skills/${skill}/assets/module.yaml`, `skills/${skill}/module.yaml`]) {
      if (!exists(rel)) continue;
      const m = read(rel).match(/^code:\s*(\S+)/m);
      if (m) return m[1];
    }
    return null;
  };
  const homeOfCode = new Map();
  for (const dir of dirs) {
    const code = codeOf(dir);
    if (code) homeOfCode.set(code, dir);
  }
  // A directory is a real, installable skill only once it carries a SKILL.md -- a module home
  // created ahead of its SKILL.md (l3io-pm-setup, until a later task fills it in) is
  // infrastructure, not yet a skill.
  const skillDirs = dirs.filter((dir) => exists(`skills/${dir}/SKILL.md`));
  const pmHome = homeOfCode.get("l3io-pm");
  const pmSkills = skillDirs.filter((dir) =>
    (dir === "l3io-pm" || dir.startsWith("l3io-pm-")) && dir !== pmHome).length;
  return {
    skills: skillDirs.length,
    modules: homeOfCode.size,
    pmSkills,
  };
}

// Claim sentences read from the live docs. `Eight` is capitalised at the start of its
// sentence, so the number word is matched case-insensitively.
const COUNT_CLAIMS = [
  ["docs/skills-and-sequence.md", /([A-Za-z-]+) skills across ([a-z-]+) modules/, ["skills", "modules"]],
  ["docs/getting-started.md",     /New to the ([a-z-]+) skills\?/,                ["skills"]],
  ["docs/getting-started.md",     /You can install all ([a-z-]+) modules/,        ["modules"]],
  ["docs/getting-started.md",     /All ([a-z-]+) modules are installed/,          ["modules"]],
  ["docs/getting-started.md",     /installs all ([a-z-]+) skills and registers the ([a-z-]+) modules/, ["skills", "modules"]],
  ["docs/l3io-pm-reference.md",   /([a-z-]+) skills that cover the delivery lifecycle/, ["pmSkills"]],
  ["docs/l3io-pm-reference.md",   /All ([a-z-]+) modules read the artifact paths/, ["modules"]],
  ["CLAUDE.md",                   /package with ([a-z-]+) modules:/,              ["modules"]],
];

const COUNT_FIELD_NOUN = { skills: "skill", modules: "module", pmSkills: "skill" };

function checkDerivedCounts() {
  const counts = derivedCounts();
  let checked = 0;
  for (const [file, re, fields] of COUNT_CLAIMS) {
    const text = read(file).replace(/\s+/g, " ");
    const m = text.match(re);
    if (!m) {
      failures.push(`${file}: the claim was not found — has the sentence been reworded? ` +
        `check 19 must be updated with it`);
      continue;
    }
    fields.forEach((field, i) => {
      checked += 1;
      const word = m[i + 1];
      const got = NUMBER_WORDS.indexOf(word.toLowerCase());
      const expect = counts[field];
      if (got !== expect) {
        failures.push(`${file}: says "${word}" ${COUNT_FIELD_NOUN[field]}(s), ` +
          `but the package has ${expect} — derived from skills/ and each skill's module.yaml`);
      }
    });
  }
  if (verbose) {
    console.log(`  derived-counts: ${counts.skills} skill(s), ${counts.modules} module(s), ` +
      `${counts.pmSkills} l3io-pm skill(s), ${checked} claim(s) checked`);
  }
}

// ---------------------------------------------------------------------------
// 20. Every skills/_shared/* source a sync group in sync-shared-scripts.mjs references has a
// row in CLAUDE.md's Shared Files table, and every table row names a source that actually
// exists under skills/_shared/.
//
// Scope, stated honestly: this compares the FILE SET in both directions only. It does not
// verify the destination column -- that a row's stated per-skill destination matches the
// sync group's actual targets -- so a row that lists the right source but the wrong
// destination skills still passes. The destination column stays hand-maintained until
// someone derives it too. A guard that overstates its reach is worse than none.
//
// Sources are parsed out of sync-shared-scripts.mjs's own text (tolerant-text, like the
// other checks) rather than imported -- importing would run the sync as a side effect. Table
// rows are parsed out of CLAUDE.md by matching lines starting "| `skills/_shared/". A row may
// name an exact file or a `skills/_shared/<dir>/**` wildcard covering every file the sync
// script pulls from that directory (used for the shared step files: one row for ~19 files).
//
// Caught in practice: the table drifted in three consecutive tasks; most recently Task 8
// added merge-config.py and merge-help-csv.py to a new sync group with no table row, and
// nothing compared the table to the sync groups it claims to describe.
// ---------------------------------------------------------------------------
const SYNC_SCRIPT = "scripts/sync-shared-scripts.mjs";

function sharedSourcesFromSyncScript() {
  const text = read(SYNC_SCRIPT);
  const rels = new Set();
  for (const m of text.matchAll(/path\.join\(sharedDir,\s*([^)]+)\)/g)) {
    const parts = [...m[1].matchAll(/"([^"]+)"/g)].map((p) => p[1]);
    if (parts.length) rels.add(parts.join("/"));
  }
  return rels;
}

function checkSharedFilesTable() {
  const rels = sharedSourcesFromSyncScript();
  if (rels.size === 0) {
    failures.push(`${SYNC_SCRIPT}: no path.join(sharedDir, ...) source found — has the sync ` +
      `script been rewritten? check 20 must be updated with it`);
    return;
  }

  const rows = [...read("CLAUDE.md").matchAll(/^\|\s*`skills\/_shared\/([^`]+)`\s*\|/gm)]
    .map((m) => m[1]);
  const wildcardDirs = rows.filter((r) => r.endsWith("/**")).map((r) => r.slice(0, -3));
  const exactRows = new Set(rows.filter((r) => !r.endsWith("/**")));

  // Direction 1: every synced source has a row.
  for (const rel of [...rels].sort()) {
    if (exactRows.has(rel)) continue;
    if (wildcardDirs.some((dir) => rel === dir || rel.startsWith(`${dir}/`))) continue;
    failures.push(`CLAUDE.md: skills/_shared/${rel} is synced but has no row in the Shared ` +
      `Files table (${SYNC_SCRIPT} references it) — add a row, or widen a \`**\` row to cover it`);
  }

  // Direction 2: every row names a real source.
  for (const row of rows) {
    const rel = row.endsWith("/**") ? row.slice(0, -3) : row;
    if (!exists(path.join("skills", "_shared", rel))) {
      failures.push(`CLAUDE.md: the Shared Files table names \`skills/_shared/${row}\`, but ` +
        `no such file or directory exists under skills/_shared/`);
    }
  }

  if (verbose) {
    console.log(`  shared-files-table: ${rels.size} synced source(s), ${rows.length} table row(s)`);
  }
}

// ---------------------------------------------------------------------------
// 21. Every skills/*/SKILL.md frontmatter strict-YAML-parses, its `name:` field equals the
// directory name, and its `description:` is a present, non-empty string.
//
// Why this matters, mechanically: BMad's installer (`ManifestGenerator.parseSkillMd()`) only
// surfaces a skill into `.claude/skills/<name>/` and `skill-manifest.csv` when its SKILL.md
// frontmatter strict-YAML-parses, `name:` equals the directory name, AND `description` is a
// non-empty string. A skill that fails any of these is dropped from a real install with NO
// warning -- not an error, not a log line, just absent. Task 11A fix round 1 found this live
// via `name`: `l3io-pm-sync/SKILL.md`'s unquoted `Modes: setup, push, ...` in its description
// broke the YAML parse, and a real install silently shipped seven of the module's eight
// skills. Fix round 2's re-review found the same failure class reachable through the
// NEIGHBOURING field: this check originally validated only `name`, so a missing, empty, null,
// list-, mapping-, number-, or boolean-valued `description` passed here while BMad's installer
// still drops the skill -- reproduced end to end (deleting `description:` from a real skill
// left check:docs, check:module, and check:manifest all green while a real install dropped
// it). Both fields are now checked in the same subprocess.
//
// What this does NOT check, stated rather than implied (a check that overstates its own
// coverage is worse than one that says plainly what it covers -- CLAUDE.md §3): it walks one
// level of `skills/` (matching this repo's shipped, flat layout); BMad's installer reads from
// the *installed* tree and recurses into subdirectories, so a nested skill directory added
// later would not be seen here.
//
// Parsing: never hand-rolled (global rule 1 -- this repo's own history with a hand-written
// YAML parser is the cautionary tale the rule cites). It used to shell out to
// `uv run --with 'ruamel.yaml>=0.18' python3 -c …`, because no npm dependency was reachable
// from CI. `npm ci` in .github/workflows/checks.yml removed that constraint, so the parse now
// runs in process against the `yaml` package -- the SAME package BMad's own installer parses
// frontmatter with, which makes this check agree with the thing it is predicting instead of
// approximating it. (Confirmed against BMad's source: `manifest-generator.js` does
// `require('yaml')` and `yaml.parse()` with the same field predicates, at `^2.7.0` to this
// repo's `^2.9.1` -- same major.) The divergences the ruamel version carried go with it: TWO
// shapes, both tabs, both rejected by ruamel and accepted by BMad -- a trailing tab after a
// scalar (`name: x<TAB>`) and a tab between the colon and the value (`name:<TAB>x`). Both were
// false positives here, and both now match BMad. A tab used as INDENTATION is still rejected
// by `yaml`, exactly as BMad rejects it. No file in this repo is affected by any of the three.
//
// Fail-closed, and what replaces the old `uv`-missing branch: the parser is now an `import` at
// the top of this file, so an absent or broken `node_modules` does not degrade check 21 -- it
// stops check-docs.mjs from starting at all, and CI's gate exits nonzero with
// ERR_MODULE_NOT_FOUND. That is strictly stronger than the old branch, which failed only this
// one check. What remains local is per-file: a SKILL.md that cannot be READ is reported as a
// failure rather than skipped, so a permissions or encoding problem cannot quietly shrink the
// set this check examines.
// ---------------------------------------------------------------------------

// Describe what is wrong with a frontmatter `description`, or null when it is a non-empty
// string. Mirrors what BMad's installer requires; every non-string shape is named explicitly
// so the failure message says what was actually found.
function describeDescriptionProblem(data) {
  if (!("description" in data)) return "the 'description' key is missing";
  const desc = data.description;
  if (typeof desc === "string") return desc === "" ? "'description' is an empty string" : null;
  if (desc === null) return "'description' is null";
  if (typeof desc === "boolean") return "'description' is a boolean, not a string";
  if (typeof desc === "number") return "'description' is a number, not a string";
  if (Array.isArray(desc)) return "'description' is a list, not a string";
  if (typeof desc === "object") return "'description' is a mapping, not a string";
  return `'description' is not a string (found ${typeof desc})`;
}

// typeof-aware renderer for a frontmatter value inside a failure message. A plain template
// literal stringifies a non-string value in a way that reads as a near-miss typo rather than a
// type error -- an array joins with commas, `null`/`undefined` disappear -- so a string value
// (the overwhelmingly common, correct case) renders unquoted as before, and everything else
// renders as JSON so the message shows what was actually found. (Fix round 2, N-2.)
function renderFrontmatterValue(value) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function checkSkillFrontmatter() {
  const skills = fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name !== "_shared")
    .map((e) => e.name)
    .filter((name) => exists(path.join("skills", name, "SKILL.md")))
    .sort();

  let parsed = 0;
  for (const name of skills) {
    const rel = `skills/${name}/SKILL.md`;
    const fail = (msg) => failures.push(`${rel}: ${msg}`);

    let text;
    try {
      text = read(rel);
    } catch (e) {
      fail(`could not be read (${e.message}) -- check 21 cannot rule on it`);
      continue;
    }

    if (!text.startsWith("---\n")) {
      fail("frontmatter fails a strict YAML parse (SKILL.md does not start with a --- " +
        "frontmatter fence) -- BMad's installer drops a skill like this from a real install " +
        "with no warning");
      continue;
    }
    const end = text.indexOf("\n---", 4);
    if (end === -1) {
      fail("frontmatter fails a strict YAML parse (SKILL.md frontmatter has no closing --- " +
        "fence) -- BMad's installer drops a skill like this from a real install with no warning");
      continue;
    }

    let data;
    try {
      data = YAML.parse(text.slice(4, end));
    } catch (e) {
      fail(`frontmatter fails a strict YAML parse (${String(e.message).split("\n")[0]}) -- ` +
        `BMad's installer drops a skill like this from a real install with no warning`);
      continue;
    }
    parsed += 1;

    if (data === null || typeof data !== "object" || Array.isArray(data) || !("name" in data)) {
      fail("frontmatter fails a strict YAML parse (frontmatter parsed but has no 'name' key) " +
        "-- BMad's installer drops a skill like this from a real install with no warning");
      continue;
    }

    if (data.name !== name) {
      fail(`frontmatter 'name: ${renderFrontmatterValue(data.name)}' does not match its ` +
        `directory name '${name}' -- BMad's installer requires them to be equal`);
    }
    const problem = describeDescriptionProblem(data);
    if (problem) {
      fail(`${problem} -- BMad's installer requires \`description\` to be a non-empty string ` +
        `and drops a skill like this from a real install with no warning`);
    }
  }
  if (verbose) console.log(`  skill-frontmatter: ${parsed} SKILL.md file(s) strict-parsed`);
}

// ---------------------------------------------------------------------------
// 22. README's Repo Layout block lists the directories each skill actually has.
//
// Caught in practice, three times in three consecutive tasks, all by a human reading: the
// l3io-pm-help row went stale when that skill gained steps/; the l3io-pm-plan row kept
// claiming a scripts/ directory deleted two commits earlier -- in a commit that edited the
// very next line of the same block; and the l3io-pm-setup row omitted references/, which was
// on disk the day the row was written. Nothing read this block, so every drift survived six
// green gates and was found only when someone happened to look.
//
// Both sides are derived. The skill set comes from skills/ (so a new skill with no row fails
// rather than being silently unlisted), the claims come from the fenced block itself, and the
// truth comes from readdirSync. Nothing here is a hand-kept list.
//
// Scope, stated rather than implied. Only DIRECTORY claims are judged -- a token that is a
// bare name followed by `/`. The block also names files (SKILL.md, customize.toml) and, in
// parentheses, files inside assets/ (module.yaml, module-help.csv); those carry no trailing
// slash and are not checked. Only `l3io-*` rows are judged: the `_shared/` row is a prose
// description of shared sources, not a directory listing, and check 20 guards its contents
// from the other direction.
// ---------------------------------------------------------------------------
const REPO_LAYOUT_DOC = "README.md";
const REPO_LAYOUT_HEADING = "## Repo Layout";
// A directory claim: a bare name followed by `/`, delimited on both sides. `scripts/tests/`
// would not match, deliberately -- the block lists one level and a nested claim should fail
// loudly here rather than be half-read.
const LAYOUT_DIR_CLAIM_RE = /(?:^|[\s,(])([a-z][a-z0-9-]*)\/(?=[\s,)]|$)/g;

// The first fenced block after the Repo Layout heading, or null.
function repoLayoutBlock(text) {
  const at = text.indexOf(REPO_LAYOUT_HEADING);
  if (at < 0) return null;
  const rest = text.slice(at);
  const open = rest.indexOf("\n```");
  if (open < 0) return null;
  const bodyStart = rest.indexOf("\n", open + 1);
  const close = rest.indexOf("\n```", bodyStart);
  if (bodyStart < 0 || close < 0) return null;
  return rest.slice(bodyStart + 1, close);
}

function checkReadmeRepoLayout() {
  const skills = fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name.startsWith("l3io-"))
    .map((e) => e.name)
    .sort();

  const block = repoLayoutBlock(read(REPO_LAYOUT_DOC));
  if (block === null) {
    failures.push(`${REPO_LAYOUT_DOC}: no fenced block found under "${REPO_LAYOUT_HEADING}" — ` +
      `has the section been restructured? check 22 must be updated with it`);
    return;
  }

  const claims = new Map();
  for (const line of block.split("\n")) {
    const m = line.match(/^\s*(l3io-[a-z0-9-]+)\/\s+(.*)$/);
    if (!m) continue;
    const named = new Set();
    for (const claim of m[2].matchAll(LAYOUT_DIR_CLAIM_RE)) named.add(claim[1]);
    claims.set(m[1], named);
  }

  for (const [name] of claims) {
    if (skills.includes(name)) continue;
    failures.push(`${REPO_LAYOUT_DOC}: Repo Layout lists '${name}/', which is not a directory ` +
      `under skills/`);
  }

  let checked = 0;
  for (const skill of skills) {
    const listed = claims.get(skill);
    if (!listed) {
      failures.push(`${REPO_LAYOUT_DOC}: Repo Layout has no row for skills/${skill}/ — every ` +
        `skill directory needs one, or the block stops describing the tree`);
      continue;
    }
    const onDisk = new Set(
      fs.readdirSync(path.join(repoRoot, "skills", skill), { withFileTypes: true })
        .filter((e) => e.isDirectory())
        .map((e) => e.name),
    );
    checked += 1;
    const missing = [...onDisk].filter((d) => !listed.has(d)).sort();
    const phantom = [...listed].filter((d) => !onDisk.has(d)).sort();
    if (missing.length) {
      failures.push(`${REPO_LAYOUT_DOC}: the skills/${skill}/ row does not list ` +
        `${missing.map((d) => `${d}/`).join(", ")}, which exist${missing.length === 1 ? "s" : ""} on disk`);
    }
    if (phantom.length) {
      failures.push(`${REPO_LAYOUT_DOC}: the skills/${skill}/ row lists ` +
        `${phantom.map((d) => `${d}/`).join(", ")}, which ` +
        `${phantom.length === 1 ? "does" : "do"} not exist on disk`);
    }
  }
  if (verbose) console.log(`  readme-repo-layout: ${checked} skill row(s) matched against disk`);
}

// ---------------------------------------------------------------------------

checkSkillNames();
checkGatingTables();
checkSectionRefs();
checkCliSurface();
checkConfigValues();
checkStatusValues();
checkMetricList();
checkDigestSize();
checkAuthoringPathDirectives();
checkCliDocstring();
checkAppendIssuePointer();
checkPmStatusSize();
checkSpecAlignContract();
checkAdrHome();
checkDoctorModeCount();
checkBmadDependencyInventory();
checkPep723Invocation();
checkDocsCheckCount();
checkDerivedCounts();
checkSharedFilesTable();
checkSkillFrontmatter();
checkReadmeRepoLayout();

for (const note of notes) if (verbose) console.log(`  note: ${note}`);

if (failures.length > 0) {
  console.error(`\n${failures.length} documentation problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  console.error("These are facts the docs state about code that says otherwise. Fix the doc,");
  console.error("or if the code moved, fix both.");
  process.exit(1);
}

console.log("Documentation checks passed: skill names, gating tables, and section references all resolve.");
