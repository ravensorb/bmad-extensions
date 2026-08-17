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

checkSkillNames();
checkGatingTables();
checkSectionRefs();

for (const note of notes) if (verbose) console.log(`  note: ${note}`);

if (failures.length > 0) {
  console.error(`\n${failures.length} documentation problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  console.error("These are facts the docs state about code that says otherwise. Fix the doc,");
  console.error("or if the code moved, fix both.");
  process.exit(1);
}

console.log("Documentation checks passed: skill names, gating tables, and section references all resolve.");
