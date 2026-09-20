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
//   4. cli-surface   documented pm-status.py and spec-align.py subcommands and the real CLIs agree, both ways
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
//  16. module-yaml-agreement  sibling module.yaml files sharing a `code:` agree on the
//                    module-level fields, since the installer picks one of them arbitrarily
//  17. bmad-dependency-inventory  every bmad-* name a runtime directive under skills/ uses is
//                    declared in skills/l3io-util-doctor/assets/bmad-dependencies.json, and no
//                    directive dispatches a removed one without same-line historical evidence
//  18. pep723-invocation  no runtime directive under skills/ invokes a PEP-723 script
//                    ({pm_status}, {spec_align}, or a *.py path) with python3, which bypasses
//                    the header's declared deps in favor of whatever sits in the ambient
//                    interpreter
//  19. docs-check-count  the numbered checks in this header agree in count with the check
//                    functions invoked below, and CLAUDE.md / scripts/CLAUDE.md's stated
//                    check count agrees with both
//  20. derived-counts  the skill count, module count, and l3io-pm skill count claimed in
//                    prose match what skills/ actually has, derived from the directory and
//                    each skill's module.yaml `code:` field — never typed
//
// Usage:
//   node scripts/check-docs.mjs        # report and exit nonzero on any failure (CI)
//   node scripts/check-docs.mjs -v     # also print what passed
import fs from "node:fs";
import path from "node:path";

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

  // Check 4 spans two scripts (pm-status.py above, spec-align.py below) implemented as two
  // functions for readability, but it is ONE numbered check -- called from here rather than
  // as its own top-level statement so check 19's derived count (one invocation per header
  // entry) doesn't have to special-case it.
  checkSpecAlignSurface();
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
// 16. Sibling module.yaml files that share a `code:` agree on the module-level fields.
//
// The installer's resolver matches ONE module.yaml per module code, so when several skills of
// the same module each carry one, whichever it enumerates first supplies the module's identity.
// Which one that is, is not something this repo controls.
//
// Caught in practice: all four l3io-pm files declared `code: l3io-pm` with four DIFFERENT
// descriptions -- three of them describing a single skill rather than the module -- and three
// different post-install-notes, each listing only that one skill's requirements. A consumer's
// post-install message therefore named a fraction of the real prerequisites, chosen by
// directory order. module_version cannot drift (postbump stamps every file), but these
// hand-authored fields could and did.
//
// Scope is derived by reading every skills/<dir>/module.yaml, never a list.
// ---------------------------------------------------------------------------
const MODULE_SHARED_FIELDS = ["name", "description", "module_greeting", "post-install-notes",
  "default_selected", "module_version"];

function checkModuleYamlAgreement() {
  const skillsDir = path.join(repoRoot, "skills");
  const byCode = new Map();
  for (const entry of fs.readdirSync(skillsDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const rel = `skills/${entry.name}/module.yaml`;
    if (!exists(rel)) continue;
    const text = read(rel);
    // Block scalars (`key: >`) continue over indented lines; capture the whole value.
    const fields = {};
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i += 1) {
      const m = lines[i].match(/^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$/);
      if (!m) continue;
      let value = m[2].trim();
      if (value === ">" || value === "|" || value === ">-" || value === "|-") {
        const body = [];
        for (let j = i + 1; j < lines.length && /^\s+\S/.test(lines[j]); j += 1) body.push(lines[j].trim());
        value = body.join(" ");
      }
      fields[m[1]] = value.replace(/\s+/g, " ");
    }
    if (!fields.code) continue;
    if (!byCode.has(fields.code)) byCode.set(fields.code, []);
    byCode.get(fields.code).push({ rel, fields });
  }
  let shared = 0;
  for (const [code, files] of byCode) {
    if (files.length < 2) continue;
    shared += 1;
    for (const field of MODULE_SHARED_FIELDS) {
      const seen = new Map();
      for (const f of files) seen.set(f.fields[field] ?? "(absent)", f.rel);
      if (seen.size > 1) {
        const detail = [...seen.entries()]
          .map(([v, rel]) => `        ${rel}: ${v.length > 90 ? `${v.slice(0, 90)}…` : v}`)
          .join("\n");
        failures.push(`module.yaml files sharing \`code: ${code}\` disagree on \`${field}\` ` +
          `(${seen.size} values across ${files.length} files). The installer picks one of them ` +
          `for the whole module, and which one is not defined:\n${detail}\n      ` +
          `Make the module-level fields identical across every skill of the module.`);
      }
    }
  }
  if (verbose) {
    console.log(`  module-yaml-agreement: ${byCode.size} module code(s), ${shared} shared by ` +
      `multiple skills, ${MODULE_SHARED_FIELDS.length} field(s) each`);
  }
}

// ---------------------------------------------------------------------------
// 17. Every bmad-* name a runtime directive uses is declared in one inventory.
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
// Scope is derived by walking skills/ markdown and every skills/<dir>/module.yaml, never a list.
// ---------------------------------------------------------------------------
const DEP_INVENTORY = "skills/l3io-util-doctor/assets/bmad-dependencies.json";
const BMAD_TOKEN_RE = /(?<![\w-])bmad-[a-z0-9-]+/g;
const DEP_STATUSES = ["required", "optional", "removed", "not-a-skill"];

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
    const rel = `skills/${entry.name}/module.yaml`;
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
// 18. No runtime directive under skills/ invokes a PEP-723 script with python3.
//
// BMad's own convention is 100% `uv run` -- every core script carries a PEP-723 header and
// python3 bypasses it, either failing outright (no ambient interpreter has the deps) or
// silently running against whatever version happens to be ambient instead of what the header
// declares. Matches `python3` immediately followed by a `{...}` helper token or a `*.py`
// path, word-bounded on both sides so `--use-python3 {pm_status}` (an option name, not an
// invocation) does not trip it.
//
// Tolerance: skills/_shared/steps/shared/step-00-activate.md documents "If `uv` is
// unavailable, use `python3` instead" as an explicit fallback for self-install, and
// skills/l3io-util-doctor/assets/migrate-state.md and bootstrap-state.md restate the same
// fallback. A rule that forbade the word `python3` outright would forbid its own escape
// hatch, so a line naming `uv`+`unavailable` or the word `fallback`, ON THE SAME LINE as the
// invocation, is exempted from this check. Two of migrate-state.md's fallback sentences used
// to wrap "If `uv` is" onto the line above the invocation, which this same-line-only
// tolerance cannot see across; they were rewrapped onto one line each rather than widening
// the tolerance to look across lines, which would have been broader than the one problem it
// needed to solve.
// ---------------------------------------------------------------------------
const PY_INVOKE_RE = /(?<![\w-])python3\s+(?:"?\{(pm_status|spec_align)\}|\S*\.py)(?![\w-])/;
const PY_FALLBACK_QUALIFIER = /\buv\b[^.]*\bunavailable\b|\bfallback\b/i;

function checkPep723Invocation() {
  const offenders = [];
  for (const rel of walkMarkdown("skills")) {
    read(rel).split("\n").forEach((line, i) => {
      if (!PY_INVOKE_RE.test(line)) return;
      if (PY_FALLBACK_QUALIFIER.test(line)) return;
      offenders.push(`${rel}:${i + 1}: invokes a PEP-723 script with python3 ` +
        `(use uv run instead): ${line.trim()}`);
    });
  }
  if (offenders.length) {
    failures.push(`runtime directives invoke a PEP-723 script with python3, bypassing its ` +
      `header-declared deps:\n      ${offenders.join("\n      ")}`);
  }
  if (verbose) console.log(`  pep723-invocation: ${offenders.length} offending line(s)`);
}

// ---------------------------------------------------------------------------
// 19. The check count claimed in prose matches what this file actually runs.
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
  ];
  for (const [file, re, text] of claims) {
    const m = text.match(re);
    if (!m) {
      failures.push(`${file}: the check-count claim was not found — has the sentence been ` +
        `reworded? check 19 must be updated with it`);
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
// 20. The skill count, module count, and l3io-pm skill count claimed in prose match what
// skills/ actually has.
//
// Modelled on check 15 (doctor-mode-count): derive the counts from the source of truth --
// the skills/ directory and each skill's own module.yaml -- never type them, and require an
// unmatched claim sentence to fail rather than silently stop being checked.
//
// module.yaml lives at the skill root today and a later task relocates it under assets/;
// codeOf() reads both locations so this check survives that move instead of counting zero
// modules afterward.
//
// Caught in practice: "seventeen checks" drifted because nothing compared it to anything
// (check 19 closed that gap); every other hand-written count here -- eight skills, four
// modules, four l3io-pm skills -- was exposed to the same failure mode and had not yet
// drifted only because no task had changed the numbers yet.
// ---------------------------------------------------------------------------
function derivedCounts() {
  const dirs = fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name.startsWith("l3io-"))
    .map((e) => e.name);
  // module.yaml lives at the skill root today and moves to assets/ in a later task -- read
  // BOTH so this check survives that relocation instead of silently counting zero afterwards.
  const codeOf = (skill) => {
    for (const rel of [`skills/${skill}/module.yaml`, `skills/${skill}/assets/module.yaml`]) {
      if (!exists(rel)) continue;
      const m = read(rel).match(/^code:\s*(\S+)/m);
      if (m) return m[1];
    }
    return null;
  };
  const codes = dirs.map(codeOf).filter(Boolean);
  return {
    skills: dirs.length,
    modules: new Set(codes).size,
    pmSkills: codes.filter((c) => c === "l3io-pm").length,
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
        `check 20 must be updated with it`);
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
checkModuleYamlAgreement();
checkBmadDependencyInventory();
checkPep723Invocation();
checkDocsCheckCount();
checkDerivedCounts();

for (const note of notes) if (verbose) console.log(`  note: ${note}`);

if (failures.length > 0) {
  console.error(`\n${failures.length} documentation problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  console.error("These are facts the docs state about code that says otherwise. Fix the doc,");
  console.error("or if the code moved, fix both.");
  process.exit(1);
}

console.log("Documentation checks passed: skill names, gating tables, and section references all resolve.");
