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
//   4. cli-surface   documented pm-status.py subcommands and the real CLI agree, both ways
//   5. config-values values quoted in prose match the defaults customize.toml ships
//   6. status-values --status filters named in skill phrase tables are real state folders
//   7. metric-list   metrics-contract.md documents exactly the metrics in METRIC_FIELDS
//   8. digest-size   the activation digest stays inside its byte budget
//
// Usage:
//   node scripts/check-docs.mjs        # report and exit nonzero on any failure (CI)
//   node scripts/check-docs.mjs -v     # also print what passed
import fs from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();
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

function checkCliSurface() {
  const real = cliSubcommands();
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
const DIGEST_BUDGET = 10400;

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

checkSkillNames();
checkGatingTables();
checkSectionRefs();
checkCliSurface();
checkConfigValues();
checkStatusValues();
checkMetricList();
checkDigestSize();

for (const note of notes) if (verbose) console.log(`  note: ${note}`);

if (failures.length > 0) {
  console.error(`\n${failures.length} documentation problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  console.error("These are facts the docs state about code that says otherwise. Fix the doc,");
  console.error("or if the code moved, fix both.");
  process.exit(1);
}

console.log("Documentation checks passed: skill names, gating tables, and section references all resolve.");
