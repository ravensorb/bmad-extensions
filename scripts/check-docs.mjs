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
//                    agree, both ways -- across the live docs, every runtime directive under
//                    skills/ (where an invocation's long flags are checked against the
//                    INVOKED SUBCOMMAND's own option set), and the activation digest's CLI
//                    synopsis. Read the Known gaps block below before believing any wider
//                    claim about its reach
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
//  17. pep723-invocation  no live doc, no runtime directive under skills/, and no CI step
//                    under .github/workflows/, invokes a PEP-723 script ({pm_status},
//                    {spec_align}, or a *.py path) with python3, which bypasses the header's
//                    declared deps in favor of whatever sits in the ambient interpreter
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
//                    sides derived (the skill set and the real directories from `git
//                    ls-files`, the claims from the block), so a gitignored build artifact is
//                    not mistaken for something README should describe
//  23. marketplace-deps  `.claude-plugin/marketplace.json`'s `dependencies` block agrees with
//                    the declared inventory in
//                    `skills/l3io-util-doctor/assets/bmad-dependencies.json` — required and
//                    optional sets both ways, with both sides derived from the two files
//  24. shared-pointers  every skill-relative pointer inside a file sync-shared-scripts.mjs
//                    ships resolves in EVERY skill that file's sync group delivers it to —
//                    scope and destinations both derived from syncGroups, no allowlist. Read
//                    check 24's own block below for what "pointer" means and what it misses
//
//  25. doctor-mode-keywords  every `/l3io-util-doctor <keyword>` invocation, in a live doc or
//                    a runtime directive, names a keyword the doctor's routing table still
//                    has -- and every unqualified `steps/<name>.md` pointer inside the doctor
//                    resolves to a file it carries. Read check 25's own block for the two
//                    invocation forms it cannot see
//
//  26. resolver-invariant  state paths are assembled only in pm-status.py's resolver section —
//                    two halves (inside pm-status.py; across all of skills/), scope derived from
//                    the tree, with the canonical status-files.md contract exempt. See the block
//                    above resolverInvariant() for the KNOWN GAP.
//
// ---------------------------------------------------------------------------------------
// KNOWN GAPS — check 4's reach over skills/
//
// Same framing checks 17 and 21 carry, and for the same reason: prose that overstates its own
// coverage is worse than no prose, because it stops the next reader looking. The whole-branch
// review measured five escapes (M-2); those four plus seven more are now closed, and each has
// a mutation test:
//
//   CLOSED  a bare `{pm_status} …` invocation with no literal `uv run` — the anchor is now
//           `uv run` OR the `{pm_status}` binding, the latter qualified on the binding being
//           inside a CLOSED BACKTICK SPAN. See pmStatusAnchors() for why code formatting and
//           not "carries a long flag", which was the first attempt: that predicate held on
//           this corpus only because a span closes the fragment before a flag can appear, and
//           two shipped sentences (assets/migrate-state.md:43, :62) sit outside a span where
//           one added flag would have turned CI red on correct prose.
//   CLOSED  a FLAGLESS bare-binding invocation. Two ship today — `{pm_status} usage` in the
//           digest's routing table and `{pm_status} show` in step-estimate.md §4 — and the
//           long-flag predicate could not see either, so renaming `usage` or `show` would
//           have left them stale with every gate green.
//   CLOSED  a flag that exists somewhere in the CLI but not on the subcommand it is given to
//           (`set-status --scope story`) — flags are judged against the invoked subcommand's
//           own option set. See argparseSurface() / pmStatusSubcommandOptions().
//   CLOSED  step-00-digest.md's CLI synopsis, a second copy of the CLI surface that every
//           dispatched subagent loads on its own and nothing verified. See
//           checkDigestCliSynopsis().
//   CLOSED  SHORT OPTIONS in a skills/ invocation. `set-status -s done` is now reported.
//           argparse is the source: pm-status.py registers no short option on any subcommand
//           today, so every `-x` is wrong — but the set is READ, not assumed, so the day one
//           is added it is accepted with no edit here. Measured before shipping: 0 short
//           options occur in the tree, so the false-positive surface is empty by inspection.
//   CLOSED  FLAG VALUES. `--status not-a-real-status`, `--runtime martian`, `--format xml`
//           are reported where argparse declares `choices` — literal lists and
//           `choices=list(CONST)` alike, the constant resolved from the module. Only a plain
//           literal value is judged; a `{binding}`, `$VAR` or `<PLACEHOLDER>` is what a
//           directive writes for a value the run supplies. Measured: 136 values judged across
//           the tree, 0 offenders, so nothing correct turns red.
//   CLOSED  a value-taking flag given NO value (`set-status --state-root` with nothing after
//           it), derived from argparse's own action= (store_true and friends take none).
//   CLOSED  POSITIONALS: a required one missing (`calibration` with no action), and a
//           positional whose word is not one of its declared `choices`. `nargs="?"`/`"*"`
//           positionals are optional and judged on value only — `usage`'s `transcript` is one,
//           and treating it as required reported 8 correct invocations before nargs was read.
//   CLOSED  FRAGMENTS THAT DO NOT PARSE AS SHELL. A usage synopsis writes alternation as
//           `(--story KEY | --epic ID)`, which puts a `(` mid-command and is not valid shell;
//           8 fragments (2 distinct lines x 4 synced copies) were skipped whole, flags and
//           all. A fragment that fails to parse is now retried with synopsis notation
//           normalised away (brackets and parentheses to spaces, a STANDALONE `|` to a space,
//           so `{story|sprint|epic}` is untouched) and only then counted unreadable. The retry
//           runs only on a fragment that already failed, so it cannot change any verdict that
//           parsing reached; measured, it recovers all 8 and surfaces no new offender. The
//           unreadable count is now 0 and `-v` still prints it.
//   CLOSED  LONG FLAGS ON spec-align.py. checkSpecAlignFlags() judges them per subcommand
//           through the same argparseSurface() extractor, which handles the two shapes
//           spec-align's parser uses and pm-status's does not: six
//           `add_mutually_exclusive_group()` aliases, and the nested `lease acquire` /
//           `lease release` subparsers, folded into `lease` because that is how the
//           invocation is written. Measured: 31 flags judged, 0 offenders.
//   CLOSED  (partly) the live-docs forward arm's HAND-KEPT PREFIX LIST. A second, DERIVED
//           way in was added: a backticked hyphenated token whose first segment is the first
//           segment of a real subcommand, ON A LINE THAT ALSO NAMES pm-status.py or
//           {pm_status}. That brings `adr-reserve` and `add-test-run` in a doc under the
//           check without the explicit `pm-status.py <name>` form. The same-line qualifier is
//           what makes it safe, and it was measured: the derived prefixes ALONE newly judge 39
//           tokens, three of which are correct prose that would red CI (`update-ai-rules`, an
//           l3io-util-doctor mode, and `adr-justified` in two docs, a spec-align disposition
//           value). Requiring pm-status.py on the line drops all three and keeps seven.
//
// What is STILL NOT CHECKED, stated so nobody has to discover it:
//
// This block lists FALSE NEGATIVES — invocations that are wrong and are not reported. It does
// not list false positives, because there are none known: every predicate that could produce
// one (the `uv run` anchor, the code-formatting qualifier, the same-line CLI qualifier, the
// literal-value qualifier) is pinned by a test that plants prose and requires exit 0.
//
//   (a) The bare `pm-status.py` PATH form with no `uv run` in front of it. Unlike the
//      `{pm_status}` binding, its prose occurrences DO carry long flags AND are not reliably
//      code-formatted, so neither qualifier transfers. check 17 forbids reaching a PEP-723
//      script by any route other than `uv run`, so this shape is a check 17 failure rather
//      than a hole here — but it is a hole HERE, and check 17 only looks for a python
//      interpreter, not for the absence of one.
//   (a2) A bare-binding invocation that is NOT code-formatted — `{pm_status} set-status …`
//      written as plain text, or inside a fenced block with no backticks around it and no
//      `uv run`. Re-measured while closing the rest: the tree holds exactly TWO such
//      occurrences, `assets/migrate-state.md:42` and `:61`, and both are prose ("{pm_status}
//      not found", "{pm_status} is version {found}") — there is no real invocation of this
//      shape to miss. The obvious discriminator, "anchor it when the next word is a real
//      subcommand", is also SELF-DEFEATING for the thing this arm exists to catch: if the
//      subcommand were renamed the word would stop being real and the anchor would stop
//      firing, so it could never report the stale name. It would buy only bad-flag detection
//      on a shape no directive uses, in exchange for reddening on a sentence like
//      "the {pm_status} report is written by". Left open deliberately, on that measurement.
//   (a4) Flags past the third soft-wrap inside ONE unclosed code span. MAX_SPAN_JOINS bounds
//      that join (a stray backtick otherwise swallows to end of file); a `\`-continued
//      command has no such cap and is read whole however deep it goes.
//   (a5) The live-docs forward arm still carries a HAND-KEPT prefix list for tokens on a line
//      that does not name pm-status.py at all — see the CLOSED entry above for the derived
//      arm beside it, and for the measurement that says why the derived rule cannot simply
//      replace it.
//   (b2) Short options, flag values and positionals are judged in the skills/ INVOCATION arm
//      only. The live-docs forward arm judges subcommand NAMES (it reads prose, not argv), and
//      the digest-synopsis arm judges flag names but not their values, because a synopsis
//      writes `--scope {story|sprint}` and `--status STATUS` — placeholders by design.
//   (e) Parenthesised spans inside the digest synopsis. `(...)` there is used both for
//      alternation over real flags and for prose notes that legitimately name another
//      subcommand's flags (`archive-epic … (alias for move-epic --to archived)`), so flags
//      inside parentheses are not judged at all. Everything outside them is.
//   (f) Any CLI other than pm-status.py and spec-align.py.
// ---------------------------------------------------------------------------------------
//
// Usage:
//   node scripts/check-docs.mjs        # report and exit nonzero on any failure (CI)
//   node scripts/check-docs.mjs -v     # also print what passed
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import YAML from "yaml";
import sh from "mvdan-sh";

// CHECK_DOCS_ROOT points the checker at another tree -- scripts/tests/check-docs.test.mjs
// runs it against a temp copy with a planted violation.
const repoRoot = process.env.CHECK_DOCS_ROOT ? path.resolve(process.env.CHECK_DOCS_ROOT) : process.cwd();
const verbose = process.argv.includes("-v") || process.argv.includes("--verbose");
// isMain guards the bottom-of-file check invocations so importing this module (e.g. to call
// resolverInvariant() directly in a unit test) does not run the full suite.
const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
const failures = [];
const notes = [];

const read = (p) => fs.readFileSync(path.join(repoRoot, p), "utf8");
const exists = (p) => fs.existsSync(path.join(repoRoot, p));

// Files a reader is told are current. Historical records are excluded on purpose: CHANGELOG
// and the trees below describe what was true when written, and rewriting them to match today
// would falsify the record.
//
// The walk is RECURSIVE. It was a single non-recursive readdirSync of docs/, which put every
// subdirectory outside every check iterating LIVE_DOCS -- checks 1, 3, 4's forward arm, 5, 6
// and now 17. The eight ADRs under docs/adr/ are live, load-bearing, cross-referenced
// documents, and not one rule in this file had ever looked at them.
//
// The exclusion is hand-named, because "is this a historical record?" is not derivable from a
// path -- so it is anchored instead: each entry's existence is asserted when the list is
// built, and a rename fails loudly HERE rather than quietly pulling a historical tree into
// every live-doc check (or, worse, quietly dropping a live one back out of view).
//   docs/superpowers/**   design specs and plans, written against the tree of their day
//   docs/decision-logs/** per-skill authoring records; each one says so in its own header
//                         ("Historical authoring record ... may not describe current behaviour")
const HISTORICAL_DOC_DIRS = ["docs/superpowers", "docs/decision-logs"];

function liveDocFiles() {
  const out = ["README.md", "CLAUDE.md"];
  const excluded = new Set(HISTORICAL_DOC_DIRS);
  for (const rel of HISTORICAL_DOC_DIRS) {
    if (!fs.existsSync(path.join(repoRoot, rel))) {
      failures.push(`${rel} is named as a historical-record tree excluded from LIVE_DOCS, but ` +
        `no such directory exists — has it been renamed or removed? The exclusion list in ` +
        `scripts/check-docs.mjs must be updated with it, or every live-doc check is silently ` +
        `scoped against a tree that is no longer the one intended`);
    }
  }
  const walk = (rel) => {
    for (const entry of fs.readdirSync(path.join(repoRoot, rel), { withFileTypes: true })) {
      const child = path.posix.join(rel, entry.name);
      if (entry.isDirectory()) {
        if (excluded.has(child)) continue;
        walk(child);
      } else if (entry.name.endsWith(".md")) {
        out.push(child);
      }
    }
  };
  walk("docs");
  return out.sort();
}

const LIVE_DOCS = liveDocFiles();

// The module a skill's directory belongs to, from that module's own module.yaml `code:`.
// assets/module.yaml is the target module home; a skill-root module.yaml is a not-yet-migrated
// module. Read both so a partial migration does not silently count zero modules.
function moduleCodeOf(skill) {
  for (const rel of [`skills/${skill}/assets/module.yaml`, `skills/${skill}/module.yaml`]) {
    if (!exists(rel)) continue;
    const m = read(rel).match(/^code:\s*(\S+)/m);
    if (m) return m[1];
  }
  return null;
}

// Every l3io-* directory under skills/, sorted. One derivation, used by every check that asks
// "which skills are there".
function skillDirNames() {
  return fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name.startsWith("l3io-"))
    .map((e) => e.name)
    .sort();
}

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
// Common English glue words -- articles, prepositions, conjunctions, copulas -- that show up
// beside "pm-status.py"/"spec-align.py" in ordinary prose rather than naming a subcommand.
// A closed linguistic class, not a domain enumeration: it does not drift as subcommands or
// modes are added or removed, so keeping it by hand here does not run afoul of "derive the
// scope, never enumerate it" -- there is no source of truth for "words that are English
// filler" to derive it from. Reused below (otherToolPrecedesEveryOccurrence) as the same
// filter on the word immediately BEFORE a candidate token, not just the word after.
const PROSE_AFTER_CMD = new Set(["only", "is", "are", "and", "or", "the", "for", "with",
  "to", "from", "in", "on", "at", "by", "not", "itself", "runs", "writes", "reads",
  "a", "an", "while", "when"]);

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

// The doctor's mode-keyword routing table, read once and shared with check 25
// (checkDoctorModeKeywords), which is the check that owns reporting when the table itself
// fails to parse. Returning {valid, rows} rather than baking the "did it parse" verdict in
// here keeps that ownership in one place instead of two checks each deciding it their own way.
function doctorRoutingTable() {
  const skill = read(`${DOCTOR_DIR}/SKILL.md`);
  const valid = new Set();
  let rows = 0;
  for (const row of skill.matchAll(DOCTOR_ROUTING_ROW_RE)) {
    rows++;
    for (const k of row[1].matchAll(/`([^`]+)`/g)) valid.add(k[1].trim());
  }
  return { valid, rows };
}

// The doctor's valid keyword set, DERIVED from the same routing table check 25 uses -- never
// a hand-list here. Returns null (not an empty set) when the table did not parse, so a caller
// can tell "no keywords" apart from "table unreadable" and skip exempting anything rather than
// silently trusting an empty derivation; check 25 is the one place that reports the parse
// failure itself.
function doctorModeKeywords() {
  const { valid, rows } = doctorRoutingTable();
  return rows < 5 || valid.size < 5 ? null : valid;
}

// A backtick-quoted hyphenated token immediately preceded -- on the same line, outside its own
// backticks, with only whitespace between -- by a bare identifier word (letters/digits/
// underscore only: no hyphen, no dot) that is NOT ordinary English filler (PROSE_AFTER_CMD) is
// claiming to be a subcommand of THAT word's tool, e.g. "git `check-ignore`", "grep
// `check-ignore`" -- not of pm-status.py. This is structural (fires on any qualifying
// preceding bareword) rather than a hand-kept list of other tool names: every real
// pm-status.py reference-table row instead puts the token right after a `| ` table pipe
// (tableRowSubcommands() reads those), never after a bare word, and pm-status.py/{pm_status}
// itself never matches the bareword pattern (both contain a hyphen or a brace). The
// PROSE_AFTER_CMD filter is what keeps this from firing on ordinary sentences ("a
// `clear-lock` remedy", "while `set-lock` exits", "on `estimate-story`") -- measured on this
// tree: without it, 6 correct occurrences of real subcommands lose coverage from this arm
// (they still pass, because they ARE real, so nothing turns red, but the arm's reach for a
// FUTURE fabricated name in the same shape would have narrowed for no reason). EVERY
// occurrence in the text must show the pattern -- a token used once as another tool's
// subcommand and once as a bare (wrong) pm-status.py claim must still be judged on the claim.
function otherToolPrecedesEveryOccurrence(text, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let found = false;
  for (const line of text.split("\n")) {
    const tokenRe = new RegExp("`" + escaped + "`", "g");
    let m;
    while ((m = tokenRe.exec(line)) !== null) {
      found = true;
      const wordMatch = line.slice(0, m.index).match(/\b([a-z][a-z0-9_]*)[ \t]+$/);
      if (!wordMatch || PROSE_AFTER_CMD.has(wordMatch[1])) return false;
    }
  }
  return found;
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
  const cliPrefixes = new Set([...real].map((n) => n.split("-")[0]));
  if (real.size === 0) {
    failures.push(`${PM_STATUS}: no sub.add_parser() calls found — has the CLI been restructured?`);
    return;
  }
  const doctorKeywords = doctorModeKeywords();
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
    // Hyphenated names written in backticks ON A LINE THAT ALSO NAMES pm-status.py or the
    // {pm_status} binding. See the prefix test below for what this buys.
    const onCliLine = new Set();
    for (const docLine of text.split("\n")) {
      if (!/pm-status\.py|\{pm_status\}/.test(docLine)) continue;
      for (const m of docLine.matchAll(/`([a-z]+(?:-[a-z]+)+)`/g)) onCliLine.add(m[1]);
    }
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
      // Which hyphenated tokens are CLAIMING to be subcommands. Two ways in, and the second
      // is derived:
      //   - the hand-kept prefix list, kept because it reaches a token on a line that says
      //     nothing about pm-status.py at all;
      //   - any token whose FIRST SEGMENT is the first segment of a real subcommand, when the
      //     same line also names pm-status.py or {pm_status}. That derivation is what brings
      //     `adr-reserve` and `add-test-run` in a doc under the check at last -- the KNOWN
      //     GAPS block recorded both as reachable only through the explicit form.
      //
      // The same-line qualifier is not decoration; it is what makes the derived set safe.
      // Measured on this tree: the derived prefixes alone newly judge 39 tokens, of which
      // THREE are correct prose that would turn CI red -- `update-ai-rules` (an
      // l3io-util-doctor mode) and `adr-justified` in two docs (a spec-align disposition
      // value). Requiring pm-status.py on the line drops those three and keeps seven.
      const derivedClaim = onCliLine.has(name) && cliPrefixes.has(name.split("-")[0]);
      // The hand-kept prefix list's own catch: a token in this shape but on a line that names
      // neither pm-status.py nor {pm_status}. Two classes of correct prose live there and must
      // not be judged as a pm-status.py claim: an l3io-util-doctor mode keyword (`check-deps`
      // is one; the valid set comes from doctorModeKeywords(), the SAME routing-table source
      // check 25 uses, never a second hand-list here), and a token that is structurally another
      // tool's subcommand on the same line (`grep \`check-ignore\``, `git \`check-ignore\``, via
      // otherToolPrecedesEveryOccurrence()). Both exemptions apply ONLY to this fallback arm --
      // an explicit "pm-status.py check-deps" or a same-line derived claim still gets judged,
      // because that really would be a false claim about the CLI.
      const fallbackClaim = /^(set|estimate|move|archive|append|list|check|clear|self)-/.test(name)
        && !(doctorKeywords && doctorKeywords.has(name))
        && !otherToolPrecedesEveryOccurrence(text, name);
      if (!explicit && !derivedClaim && !fallbackClaim) continue;
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
  checkModuleReferenceCoverage();
  checkDigestCliSynopsis();
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
// WHAT IS JUDGED, per invocation, all of it against the INVOKED SUBCOMMAND's own argparse
// surface (argparseSurface) rather than the union of everything the CLI registers anywhere:
// the subcommand name, every long flag, every SHORT option, each flag's VALUE where argparse
// declares `choices`, whether a value-taking flag was given one, and whether a required
// positional is present and one of its `choices`. pmStatusLongOptions()'s union survives only
// as the fallback for a subcommand the extractor did not see, so a future build_parser() shape
// that defeats it degrades to the old reach instead of turning CI red on correct docs.
//
// Why source and not a subprocess: the authoritative answer needs python, and reaching it
// costs one `uv run` per checker invocation -- ~223 ms measured, multiplied by the 100+
// fixture runs in scripts/tests/check-docs.test.mjs. The extraction is ANCHORED EXTERNALLY
// instead: scripts/tests/check-docs.test.mjs runs the real build_parser() under uv, once, and
// asserts the option sets are identical in both directions.
//
// Values are judged only when the token is a plain literal. `{binding}`, `$VAR` and
// `<PLACEHOLDER>` are what a directive writes for a value the run supplies, and judging those
// would red on correct docs. Measured on this tree: 136 values judged, 0 offenders.
//
// A fragment that does not parse as shell is retried with usage-synopsis notation normalised
// away before being counted unreadable -- see normaliseSynopsis(). That took the unreadable
// count on this tree from 8 to 0 without surfacing a single new offender; -v still prints it.
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

// PER-SUBCOMMAND long options: Map<subcommand, Set<"--flag">>.
//
// Why this is not the union above. The union answers "does pm-status.py have this flag
// anywhere", which passes `set-status --scope story` -- a real flag on the wrong subcommand,
// a class the whole-branch review named as still open (M-2(3)). argparse's per-subparser
// surface is what actually decides, and this reads it out of build_parser()'s source.
//
// Why source and not a subprocess. The authoritative answer needs python, and reaching it
// costs one `uv run` per checker invocation -- ~223 ms measured, multiplied by the 100+
// fixture runs in scripts/tests/check-docs.test.mjs. So the surface is extracted from source
// and ANCHORED EXTERNALLY: scripts/tests/check-docs.test.mjs runs the real build_parser()
// under uv, once, and asserts this function's output is set-identical to
// `{sub: [a.option_strings]}` in BOTH directions. That is the pattern ADR-0008 lesson 5
// prescribes -- derive the scope internally, anchor the content externally -- and it is what
// makes a regex over python source defensible here: it is not a Python parser, it reads one
// deliberately regular construct, and a second source of truth fails the build if it drifts.
// Verified at the time of writing: 31 subcommands, every option set identical both ways.
//
// build_parser()'s shape, which this relies on and the anchor test enforces:
//   VAR = sub.add_parser("name", ...)      binds VAR to that subcommand
//   VAR.add_argument("--a", "--b", ...)    adds to whatever VAR currently names
//   helper(VAR)                            an inner `def helper(param)` that add_argument's
//                                          onto `param` (today: node_args)
// Variables are REUSED (`rp` is report and later repair-issue; `a` is set-actual and later
// add-test-run), so events are replayed in source order and a rebind retargets the variable.
// Root-parser options (`p.add_argument("--version")`) are deliberately excluded: argparse
// accepts `pm-status.py --version`, never `pm-status.py set-status --version`.
// One extractor, four facets. `options` is what pmStatusSubcommandOptions() returns and what
// the external anchor test pins; `shorts`, `choices`, `valueFlags` and `positionals` are the
// facets the KNOWN GAPS block used to list as unjudged (short options, flag VALUES, positional
// and required-argument presence). They come from the same walk because a second walk over the
// same construct is a second thing to keep in step.
//
// Shapes handled, all of them present in one of the two CLIs:
//   SUBS = ROOT.add_subparsers(...)           the root's subparser factory
//   VAR  = SUBS.add_parser("name", ...)       binds VAR to that subcommand
//   NEST = VAR.add_subparsers(...)            a nested factory; its parsers FOLD INTO VAR's
//                                             subcommand, because `lease acquire --owner` is
//                                             written as one invocation and judged as one
//   G    = VAR.add_mutually_exclusive_group() an alias for VAR (spec-align uses six)
//   VAR.add_argument("--a", "-a", "pos", …)   adds to whatever VAR currently names
//   helper(VAR)                               an inner `def helper(param)` that add_argument's
//                                             onto `param` (pm-status's node_args)
// Variables are REUSED (pm-status's `rp` is report and later repair-issue), so events are
// replayed in source order and a rebind retargets the variable.
// Root-parser options (`p.add_argument("--version")`) are deliberately excluded: argparse
// accepts `pm-status.py --version`, never `pm-status.py set-status --version`.
const ARG_NAME_RE = /"((?:--|-)?[A-Za-z0-9][A-Za-z0-9-]*)"/g;

// Every `VAR.add_argument(...)` call in a region, with its FULL argument list. The list is
// found by balancing parentheses (quote-aware), not by a line-shaped regex: an add_argument
// spans lines both ways in these two files -- one call wrapping onto a `help=` continuation,
// and three consecutive one-line calls at the same indent inside `def node_args(sp):`. A
// tail regex that swallows indented lines ate the second and third of those (--epic and
// --sprint vanished from five subcommands, caught by the external anchor test), and one that
// stopped at any `name=` line would truncate the first. Balancing is the only rule that is
// right for both.
function pyArgCalls(region) {
  const out = [];
  const re = /([a-z_]+)\.add_argument\(/g;
  let m;
  while ((m = re.exec(region)) !== null) {
    let depth = 1;
    let i = re.lastIndex;
    let quote = null;
    while (i < region.length && depth > 0) {
      const ch = region[i];
      if (quote !== null) {
        if (ch === "\\") i += 1;
        else if (ch === quote) quote = null;
      } else if (ch === '"' || ch === "'") quote = ch;
      else if (ch === "(") depth += 1;
      else if (ch === ")") depth -= 1;
      i += 1;
    }
    const body = region.slice(re.lastIndex, Math.max(re.lastIndex, i - 1));
    const lead = body.match(/^\s*((?:"[^"]*"\s*,\s*)*"[^"]*")/);
    if (lead) out.push({ at: m.index, varName: m[1], names: lead[1], tail: body });
    re.lastIndex = i;
  }
  return out;
}

// Module-level `NAME = [...]` / `NAME = (...)` string collections, so `choices=list(RESOLUTIONS)`
// resolves to the same values argparse would see. An unresolvable choices= is simply not
// recorded -- an unknown set judges nothing, which is the fail-open direction a value check
// must take.
function pyStringCollections(src) {
  const out = new Map();
  for (const m of src.matchAll(/^([A-Z_][A-Z0-9_]*)\s*=\s*[[(]([^\])]*)[\])]/gm)) {
    const vals = [...m[2].matchAll(/"([^"]*)"|'([^']*)'/g)].map((x) => x[1] ?? x[2]);
    if (vals.length) out.set(m[1], vals);
  }
  return out;
}

const _surfaceCache = new Map();

function argparseSurface(pyRel) {
  if (_surfaceCache.has(pyRel)) return _surfaceCache.get(pyRel);
  const bySub = new Map();
  if (!exists(pyRel)) return (_surfaceCache.set(pyRel, bySub), bySub);
  const src = read(pyRel);
  const consts = pyStringCollections(src);

  const start = src.indexOf("\ndef build_parser(");
  if (start < 0) return (_surfaceCache.set(pyRel, bySub), bySub);
  const rest = src.slice(start + 1);
  const end = rest.search(/\n(?:def |if __name__)/);
  const region = end < 0 ? rest : rest.slice(0, end);
  const lines = region.split("\n");

  const choicesOf = (tail) => {
    const lit = tail.match(/choices=\[([^\]]*)\]/);
    if (lit) {
      const vals = [...lit[1].matchAll(/"([^"]*)"|'([^']*)'/g)].map((x) => x[1] ?? x[2]);
      return vals.length ? vals : null;
    }
    const named = tail.match(/choices=(?:list|tuple|sorted)\(([A-Z_]+)\)/) ||
                  tail.match(/choices=([A-Z_]+)\b/);
    return named && consts.has(named[1]) ? consts.get(named[1]) : null;
  };
  const argsOf = (call, tail) => {
    const names = [...call.matchAll(ARG_NAME_RE)].map((m) => m[1]);
    return {
      names,
      // store_true/store_false/count/store_const consume no value; everything else does.
      takesValue: !/action="(store_true|store_false|count|store_const|help|version)"/.test(tail),
      // nargs="?" and nargs="*" make a positional optional; a bare positional is required.
      optional: /nargs="[?*]"/.test(tail),
      choices: choicesOf(tail),
    };
  };

  // Inner helpers, collected by indentation: `    def NAME(PARAM):` plus the more-indented
  // block under it.
  const helpers = new Map();
  for (let i = 0; i < lines.length; i++) {
    const def = lines[i].match(/^(\s+)def ([a-z_]+)\(([a-z_]+)\):\s*$/);
    if (!def) continue;
    const [, indent, name] = def;
    let body = "";
    for (let j = i + 1; j < lines.length; j++) {
      if (lines[j].trim() !== "" && !lines[j].startsWith(indent + " ")) break;
      body += lines[j] + "\n";
    }
    const args = pyArgCalls(body).map((c) => argsOf(c.names, c.tail));
    helpers.set(name, args);
  }

  const events = [];
  for (const m of region.matchAll(/([a-z_]+)\s*=\s*([a-z_]+)\.add_subparsers\(/g)) {
    events.push({ at: m.index, factory: m[1], of: m[2] });
  }
  for (const m of region.matchAll(/([a-z_]+)\s*=\s*([a-z_]+)\.add_parser\(\s*"([a-z-]+)"/g)) {
    events.push({ at: m.index, bind: m[1], factory: m[2], sub: m[3] });
  }
  for (const m of region.matchAll(/([a-z_]+)\s*=\s*([a-z_]+)\.add_(?:mutually_exclusive_group|argument_group)\(/g)) {
    events.push({ at: m.index, alias: m[1], of: m[2] });
  }
  for (const c of pyArgCalls(region)) {
    events.push({ at: c.at, varName: c.varName, args: [argsOf(c.names, c.tail)] });
  }
  for (const [name, args] of helpers) {
    for (const m of region.matchAll(new RegExp(`\\n\\s*${name}\\(([a-z_]+)\\)`, "g"))) {
      events.push({ at: m.index, varName: m[1], args });
    }
  }
  events.sort((a, b) => a.at - b.at);

  const varToSub = new Map();   // parser variable -> subcommand it belongs to
  const factoryOf = new Map();  // subparsers-factory variable -> parent subcommand, or null for root
  for (const ev of events) {
    if (ev.factory && ev.bind === undefined) {
      factoryOf.set(ev.factory, varToSub.get(ev.of) ?? null);
      continue;
    }
    if (ev.bind) {
      // A nested factory folds into its parent subcommand; the root factory opens a new one.
      const parent = factoryOf.get(ev.factory);
      const sub = parent ?? ev.sub;
      varToSub.set(ev.bind, sub);
      if (!bySub.has(sub)) {
        bySub.set(sub, {
          options: new Set(["--help"]), shorts: new Set(["-h"]),
          choices: new Map(), valueFlags: new Map(), positionals: [],
        });
      }
      continue;
    }
    if (ev.alias) {
      const s = varToSub.get(ev.of);
      if (s) varToSub.set(ev.alias, s);
      continue;
    }
    const sub = varToSub.get(ev.varName);
    if (!sub) continue;  // the root parser, and anything before the first bind
    const entry = bySub.get(sub);
    for (const a of ev.args) {
      for (const name of a.names) {
        if (name.startsWith("--")) {
          entry.options.add(name);
          entry.valueFlags.set(name, a.takesValue);
          if (a.choices) entry.choices.set(name, new Set(a.choices));
        } else if (name.startsWith("-")) {
          entry.shorts.add(name);
        } else {
          entry.positionals.push({ name, optional: a.optional, choices: a.choices });
        }
      }
    }
  }
  _surfaceCache.set(pyRel, bySub);
  return bySub;
}

// PER-SUBCOMMAND long options: Map<subcommand, Set<"--flag">>, the projection of
// argparseSurface() that the external anchor test pins.
//
// Why this is not the union pmStatusLongOptions() returns. The union answers "does
// pm-status.py have this flag anywhere", which passes `set-status --scope story` -- a real
// flag on the wrong subcommand, a class the whole-branch review named as open (M-2(3)).
//
// Why source and not a subprocess. The authoritative answer needs python, and reaching it
// costs one `uv run` per checker invocation -- ~223 ms measured, multiplied by the 100+
// fixture runs in scripts/tests/check-docs.test.mjs. So the surface is extracted from source
// and ANCHORED EXTERNALLY: scripts/tests/check-docs.test.mjs runs the real build_parser()
// under uv, once, and asserts this function's output is set-identical to
// `{sub: [a.option_strings]}` in BOTH directions. That is the pattern ADR-0008 lesson 5
// prescribes -- derive the scope internally, anchor the content externally -- and it is what
// makes a regex over python source defensible here: it is not a Python parser, it reads one
// deliberately regular construct, and a second source of truth fails the build if it drifts.
function pmStatusSubcommandOptions() {
  const out = new Map();
  for (const [sub, entry] of argparseSurface(PM_STATUS)) out.set(sub, entry.options);
  return out;
}

// 4 (continued). The activation digest's CLI synopsis.
//
// Why this exists (M-2(2) of the whole-branch review). `steps/shared/step-00-digest.md`
// carries a fenced synopsis block that is a SECOND COPY of pm-status.py's CLI surface, and
// CLAUDE.md says dispatched subagents load the digest ON ITS OWN -- so for every subagent in
// the system it is not a summary of the CLI reference, it IS the CLI reference. Check 10
// guards pm-status.py's own module docstring; nothing guarded this copy. Measured before this
// arm existed: a fabricated subcommand and a bogus flag planted in the block left all six
// gates green. Same shape as the duplicated clear-lock remedy that motivated the invocation
// arm, at larger blast radius.
//
// Scope, derived: every `steps/shared/step-00-digest.md` under skills/ -- the _shared source
// and each synced copy -- found by walking, never listed. A skill that gains a digest is
// covered on arrival, and a sync that half-lands is caught here as well as by check:scripts.
//
// Parsing. The block is located by its heading, not by line number. Inside it an entry starts
// at column 0 and continues through the indented lines beneath it; the entry's first token is
// the subcommand and every later `--flag` is a flag claim.
//
// Flags are judged PER SUBCOMMAND, with one deliberate exclusion: parenthesised spans are
// stripped first. The synopsis uses `(...)` for two different things -- alternation over real
// flags, `(--story KEY | --epic ID)`, and prose notes that legitimately name ANOTHER
// subcommand's flags, `archive-epic ... (alias for move-epic --to archived)`. Telling those
// apart needs judgement, and a checker that cries wolf gets switched off, so parenthesised
// flags are not judged at all. Everything outside parentheses is, exactly.
const DIGEST_BASENAME = "steps/shared/step-00-digest.md";
const DIGEST_SYNOPSIS_HEADING = "### The calls a sprint or epic run makes";

// A flag token in prose: `--tokens-*`, `--cost*` and `--elapsed-hours*` are globs standing for
// a family, not options, so a `*` immediately after the name disqualifies it.
function synopsisFlags(text) {
  const stripped = text.replace(/\([^)]*\)/g, " ");
  const out = [];
  for (const m of stripped.matchAll(/--[a-z0-9]+(?:-[a-z0-9]+)*/g)) {
    if (stripped[m.index + m[0].length] === "*") continue;
    out.push(m[0]);
  }
  return out;
}

function checkDigestCliSynopsis() {
  const real = cliSubcommands();
  const bySub = pmStatusSubcommandOptions();
  const union = pmStatusLongOptions();
  const offenders = [];
  let files = 0;
  let entries = 0;
  let flagsChecked = 0;

  for (const rel of allSkillDocs()) {
    if (!rel.replaceAll("\\", "/").endsWith(DIGEST_BASENAME)) continue;
    const text = read(rel);
    const at = text.indexOf(DIGEST_SYNOPSIS_HEADING);
    if (at < 0) {
      offenders.push(`${rel}: has no '${DIGEST_SYNOPSIS_HEADING}' section — the CLI synopsis ` +
        `every dispatched subagent reads is the thing this arm guards; if it moved, move ` +
        `this heading with it`);
      continue;
    }
    files += 1;
    const after = text.slice(at);
    const fence = after.match(/```[a-z]*\n([\s\S]*?)\n```/);
    if (!fence) {
      offenders.push(`${rel}: '${DIGEST_SYNOPSIS_HEADING}' is not followed by a fenced block`);
      continue;
    }
    const blockStartLine = text.slice(0, at + after.indexOf(fence[0])).split("\n").length;

    // Entries: a line starting at column 0 opens one; indented lines continue it.
    const blockLines = fence[1].split("\n");
    const blockEntries = [];
    for (let i = 0; i < blockLines.length; i++) {
      const line = blockLines[i];
      if (line.trim() === "") continue;
      if (/^\s/.test(line)) {
        if (blockEntries.length) blockEntries[blockEntries.length - 1].text += " " + line;
        continue;
      }
      blockEntries.push({ text: line, line: blockStartLine + i + 1 });
    }

    for (const entry of blockEntries) {
      const sub = entry.text.trim().split(/\s+/)[0];
      if (!/^[a-z][a-z-]*$/.test(sub)) continue;
      entries += 1;
      if (!real.has(sub)) {
        offenders.push(`${rel}:${entry.line}: the subagent CLI synopsis documents ` +
          `subcommand '${sub}', which pm-status.py does not have\n      CLI has: ` +
          `${[...real].sort().join(", ")}`);
        continue;
      }
      const allowed = bySub.get(sub) || union;
      for (const flag of synopsisFlags(entry.text)) {
        flagsChecked += 1;
        if (allowed.has(flag)) continue;
        offenders.push(`${rel}:${entry.line}: the subagent CLI synopsis gives '${sub}' the ` +
          `flag '${flag}', which pm-status.py does not register on that subcommand\n` +
          `      ${sub} takes: ${[...allowed].sort().join(" ")}`);
      }
    }
  }

  if (files === 0) {
    offenders.push(`no ${DIGEST_BASENAME} found under skills/ — the arm that guards the ` +
      `subagent CLI synopsis has nothing to check, which is a scope failure, not a pass`);
  }
  if (offenders.length) {
    failures.push(`the activation digest's CLI synopsis does not match pm-status.py:\n      ` +
      `${offenders.join("\n      ")}`);
  }
  if (verbose) {
    console.log(`  digest-synopsis: ${entries} synopsis entr(ies) and ${flagsChecked} flag(s) ` +
      `across ${files} digest cop(ies) checked`);
  }
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
// The two are counted SEPARATELY and only the span join is capped. They are not the same kind
// of thing, and one shared counter truncated real commands:
//
//   - A `\`-continued command is ONE command. The shell imposes no depth limit and neither
//     does this, because a run only continues while EVERY line ends in `\` -- it is
//     self-terminating by construction, and stopping early means reading part of a command and
//     judging it as if it were whole. Measured on this tree the deepest real invocation is
//     **14 joins** (`_shared/steps/sprint/step-04-sprint-closure.md:70`), 68 pm-status
//     invocations run past 3, and a shared cap of 3 left 230 of 1441 long-flag tokens (16%,
//     across 26 files) unjudged -- a bogus flag on line 79 of step-06-epic-closure.md's
//     13-line `set-actual` kept the gate green. No number is stated here because there is no
//     limit to state; deriving one from "the longest invocation today plus headroom" would be
//     a hand-kept bound that silently truncates the first command to exceed it.
//   - An unclosed `…` span has no such property: a stray backtick never closes, so without a
//     cap it swallows to end of file. MAX_SPAN_JOINS bounds only that, and its observable
//     effect is the reported line number (see the stray-backtick test).
const MAX_SPAN_JOINS = 3;

function logicalLines(text) {
  const lines = text.split("\n");
  const out = [];
  const spanLeftOpen = (s) => !/^\s*```/.test(s) && ((s.match(/`/g) || []).length % 2 === 1);
  for (let i = 0; i < lines.length; i++) {
    let joined = lines[i];
    let j = i;
    let spanJoins = 0;
    while (j + 1 < lines.length) {
      const shellContinuation = /\\\s*$/.test(joined);
      if (shellContinuation) {
        joined = joined.replace(/\\\s*$/, "");
      } else if (spanLeftOpen(joined) && spanJoins < MAX_SPAN_JOINS) {
        spanJoins += 1;
      } else {
        break;
      }
      j += 1;
      joined += " " + lines[j];
    }
    out.push({ text: joined, line: i + 1 });
    i = j;
  }
  return out;
}

// Anchor positions in one logical line, in source order.
//
// `uv run` anchors need no qualification: check 17 forbids reaching a PEP-723 script any other
// way, so a `uv run` fragment naming pm-status.py IS a command by construction.
//
// A BARE `{pm_status}` anchor is the extension that closes M-2(1). It is qualified on the
// binding being INSIDE A CLOSED BACKTICK SPAN -- code formatting -- and on nothing else.
//
// Why that qualifier and not the long-flag one it replaces. The first version of this arm
// judged a bare-binding fragment only when it carried a `--flag`, on the measurement that no
// prose use of the binding carries one. True, and true for the wrong reason: every prose
// occurrence but two sits inside a backtick span, and a span CLOSES the fragment before any
// flag could appear in it. The property was the corpus's, not the predicate's. The two
// exceptions prove it -- `assets/migrate-state.md:43` and `:62` write an un-backticked
// `{pm_status}` inside a fenced BLOCKED message, so an author adding a long flag to either
// sentence (". . . then re-run with --flock") would have turned CI red on correct prose with
// a message about a subcommand called `is` or `not`. A guard that cries wolf gets switched
// off, and then it protects nothing.
//
// Code formatting is the property the corpus actually relies on, so this requires it
// directly. Measured on this tree, it separates the two classes exactly:
//   `{pm_status} usage`            in a span -> judged   (a real invocation; digest §routing)
//   `{pm_status} show`             in a span -> judged   (a real invocation; step-estimate §4)
//   `{pm_status}` not found...     span holds the binding ALONE, so the fragment ends there,
//                                  no subcommand token follows, nothing is judged
//   BLOCKED: {pm_status} is version{found}...  not in a span -> never anchored
//
// Dropping the flag gate is what makes a FLAGLESS bare invocation reachable at all: the two
// real ones above shipped unchecked under the old predicate, so renaming `usage` or `show`
// would have left them stale with every gate green.
//
// The `pm-status.py` PATH form is still deliberately NOT a bare anchor -- it is the form
// check 17 already governs, and its prose uses are not reliably code-formatted. That
// remainder is in the KNOWN GAPS block in this file's header.
function pmStatusAnchors(text) {
  const anchors = [];
  const covered = []; // [start, end) already inside a `uv run` fragment
  for (const m of text.matchAll(/\buv\s+run\b/g)) {
    anchors.push({ at: m.index, bare: false });
    const rest = text.slice(m.index);
    const closes = rest.indexOf("`");
    covered.push([m.index, closes >= 0 ? m.index + closes : text.length]);
  }

  // An occurrence is inside a closed backtick span when an odd number of backticks precede it
  // on the logical line AND one follows it. The same parity test logicalLines() uses for a
  // soft-wrapped span, applied at a point rather than at end of line.
  const inClosedSpan = (at) => {
    const before = (text.slice(0, at).match(/`/g) || []).length;
    return before % 2 === 1 && text.indexOf("`", at) >= 0;
  };

  for (const m of text.matchAll(/\{pm_status\}/g)) {
    if (covered.some(([start, end]) => m.index >= start && m.index < end)) continue;
    if (!inClosedSpan(m.index)) continue;
    anchors.push({ at: m.index, bare: true });
  }
  return anchors.sort((a, b) => a.at - b.at);
}

// Every pm-status.py invocation in one markdown file, as {sub, argv, at, line, text}, plus an
// {unreadable: true} marker for a fragment the shell parser could not read. Factored out so
// the flag arm below and check 4's module-reference arm read the corpus the SAME way: two
// extractors over one corpus is two things to keep in step, and the second one silently
// diverging is how a guard stops covering what its prose says it covers.
const normaliseSynopsis = (s) =>
  s.replace(/[()[\]]/g, " ").replace(/(^|\s)\|(\s|$)/g, "$1 $2");

function* pmStatusCommands(rel) {
  for (const { text, line } of logicalLines(read(rel))) {
    for (const anchor of pmStatusAnchors(text)) {
      let fragment = text.slice(anchor.at);
      const closingBacktick = fragment.indexOf("`");
      if (closingBacktick >= 0) fragment = fragment.slice(0, closingBacktick);
      if (!/\{pm_status\}|pm-status\.py/.test(fragment)) continue;

      // A usage SYNOPSIS is not valid shell: `(--story KEY | --epic ID)` puts a `(` in the
      // middle of a simple command, which bash rejects. Eight fragments on this tree (two
      // distinct lines x four synced copies) were skipped for that reason alone, taking
      // their real flags with them. So a fragment that does not parse is retried with
      // synopsis notation normalised away -- brackets and parentheses become spaces, a
      // standalone `|` becomes a space -- and only then counted unreadable. The retry runs
      // ONLY on a fragment that already failed, so it cannot change the verdict on anything
      // that parses; measured on this tree it recovers all 8 and surfaces no new offender.
      // `{story|sprint|epic}` is untouched: only a `|` with whitespace on both sides goes.
      let commands = shellCommands(fragment);
      if (commands === null) commands = shellCommands(normaliseSynopsis(fragment));
      if (commands === null) { yield { unreadable: true }; continue; }
      for (const { argv } of commands) {
        const at = argv.findIndex((t) => typeof t === "string" && PM_STATUS_TOKEN_RE.test(t));
        if (at < 0) continue;
        const sub = argv[at + 1];
        if (typeof sub !== "string" || !/^[a-z][a-z-]*$/.test(sub)) continue;
        yield { sub, argv, at, line, text };
      }
    }
  }
}

function checkPmStatusInvocations() {
  const real = cliSubcommands();
  const flags = pmStatusLongOptions();
  const surface = argparseSurface(PM_STATUS);
  let checked = 0;
  let valuesChecked = 0;
  let unreadable = 0;
  // Reported under -v because it is the number a depth regression moves, and nothing else
  // would show it: an invocation truncated mid-command still counts as one `checked`
  // invocation while its remaining flags go unjudged. A shared join cap of 3 hid 230 of these.
  let flagsChecked = 0;
  const offenders = [];

  for (const rel of allSkillDocs()) {
    for (const { sub, argv, at, line, text, unreadable: bad } of pmStatusCommands(rel)) {
      if (bad) { unreadable += 1; continue; }
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
      // M-2(3): judged against the INVOKED subcommand's own option set, not the union of
      // every option the CLI registers anywhere. The union passed `set-status --scope
      // story` -- a real flag on the wrong subcommand -- and the review named that as
      // still open. pmStatusSubcommandOptions() is anchored against the real argparse by
      // scripts/tests/check-docs.test.mjs; the union is kept only as the fallback for a
      // subcommand the extractor did not see, so a future build_parser() shape that
      // defeats it degrades to the old reach instead of turning CI red on correct docs.
      const entry = surface.get(sub);
      const allowed = entry ? entry.options : flags;
      const perSubcommand = Boolean(entry);
      const rest = argv.slice(at + 2);
      const free = [];   // non-option words that are not a preceding flag's value
      for (let i = 0; i < rest.length; i += 1) {
        const token = rest[i];
        if (typeof token !== "string") continue;
        if (token === "--") break;            // everything after it is a positional
        if (!token.startsWith("-") || token === "-") { free.push(token); continue; }

        // SHORT OPTIONS. Derived, never assumed: pm-status.py registers none today, so any
        // `-x` is wrong -- but the set is read out of argparse, so the day one is added it
        // is accepted without touching this file.
        if (!token.startsWith("--")) {
          if (/^-\d/.test(token)) { free.push(token); continue; }   // a negative number value
          if (entry && !entry.shorts.has(token)) {
            offenders.push(`${rel}:${line}: invokes '${sub} ${token}', but pm-status.py ` +
              `registers no such short option on '${sub}'` +
              (entry.shorts.size <= 1 ? " (it registers no short options at all)" : ""));
          }
          continue;
        }

        const flag = token.split("=")[0];
        flagsChecked += 1;
        if (!allowed.has(flag)) {
          offenders.push(
            perSubcommand && flags.has(flag)
              ? `${rel}:${line}: invokes '${sub} ${flag}', but pm-status.py registers that ` +
                `option on other subcommands only, never on '${sub}'\n      ${sub} takes: ` +
                `${[...allowed].sort().join(" ")}`
              : `${rel}:${line}: invokes '${sub} ${flag}', but pm-status.py ` +
                `registers no such option anywhere in its CLI`);
          continue;
        }
        if (!entry) continue;

        // The flag's VALUE: present when argparse needs one, and one of its `choices` when
        // argparse declares them. Only a plain literal value is judged -- a `{binding}`, a
        // `$VAR`, a `<PLACEHOLDER>` or anything else non-literal is what a directive writes
        // for a value the run supplies, and judging those would red on correct docs.
        const takesValue = entry.valueFlags.get(flag) !== false;
        let value = null;
        if (token.includes("=")) value = token.slice(token.indexOf("=") + 1);
        else if (takesValue) {
          const next = rest[i + 1];
          if (typeof next === "string" && !next.startsWith("--")) { value = next; i += 1; }
        }
        if (takesValue && value === null) {
          offenders.push(`${rel}:${line}: invokes '${sub} ${flag}' with no value, but ` +
            `pm-status.py declares it as taking one`);
          continue;
        }
        const choices = entry.choices.get(flag);
        if (!choices || value === null) continue;
        if (!/^[A-Za-z][A-Za-z0-9_.-]*$/.test(value)) continue;
        valuesChecked += 1;
        if (!choices.has(value)) {
          offenders.push(`${rel}:${line}: invokes '${sub} ${flag} ${value}', but ` +
            `pm-status.py accepts only ${[...choices].sort().join(" | ")} there`);
        }
      }

      // POSITIONALS. A required positional (no nargs, or a numeric one) must be supplied,
      // and when argparse declares `choices` for it the word given must be one of them.
      // `nargs="?"`/`nargs="*"` positionals are optional and judged only on their value.
      if (entry) {
        entry.positionals.forEach((pos, idx) => {
          const given = free[idx];
          if (given === undefined) {
            if (!pos.optional) {
              offenders.push(`${rel}:${line}: invokes '${sub}' with no ${pos.name}, but ` +
                `pm-status.py requires that argument` +
                (pos.choices ? ` (${pos.choices.join(" | ")})` : ""));
            }
            return;
          }
          if (!pos.choices) return;
          if (!/^[A-Za-z][A-Za-z0-9_.-]*$/.test(given)) return;
          valuesChecked += 1;
          if (!pos.choices.includes(given)) {
            offenders.push(`${rel}:${line}: invokes '${sub} ${given}', but pm-status.py ` +
              `accepts only ${pos.choices.join(" | ")} as its ${pos.name}`);
          }
        });
      }
    }
  }

  if (offenders.length) {
    failures.push(`runtime directives under skills/ invoke pm-status.py surface that does ` +
      `not exist:\n      ${offenders.join("\n      ")}`);
  }
  if (verbose) {
    console.log(`  pm-status-invocations: ${checked} invocation(s), ${flagsChecked} long ` +
      `flag(s) and ${valuesChecked} flag/positional value(s) in skills/ checked ` +
      `(${unreadable} fragment(s) not readable as shell even after synopsis normalisation, ` +
      `skipped)`);
  }
}

// 4 (continued). Every module's reference doc documents the pm-status.py subcommands that
// module's OWN skills actually run.
//
// Why this exists. The reverse arm above -- "every subcommand the CLI has must be documented"
// -- was bound to one hand-typed constant, docs/l3io-pm-reference.md. That is the right rule
// for the CLI's own reference, and it is the whole reach: docs/l3io-util-reference.md
// documents a skill whose mode files invoke {pm_status} directly, and NOTHING asked whether
// what it runs is written down anywhere in it. The forward arm reads that file (it is in
// LIVE_DOCS) and would catch a subcommand named there that does not exist -- but a subcommand
// that exists, that the skill really runs, and that the doc never mentions is invisible to
// every direction of every check. "Right rule, incomplete set" is the failure mode CLAUDE.md
// §4 names.
//
// Adding a second constant would repeat the mistake one path later, so the set is DERIVED:
//   which modules exist          <- each skill's own module.yaml `code:` (moduleCodeOf)
//   which skills are in a module <- the repo's own naming convention, `<code>` or `<code>-*`,
//                                   the same one check 19 and check-module.mjs use
//   which doc is a module's ref  <- docs/<code>-reference.md
//   what that module runs        <- pmStatusCommands() over that module's skill docs
//   what the doc documents       <- tableRowSubcommands(), the same anchor the arm above uses
//
// Both directions of the doc set are checked, so neither side can silently shrink: a module
// with no reference doc fails, and a docs/l3io-*-reference.md naming no real module fails.
//
// SYNCED COPIES ARE EXCLUDED, and that exclusion is derived too -- a per-skill file whose
// bytes are identical to a file under skills/_shared/ is a generated copy of shared contract
// text, not something this module chose to run. Without it, syncing status-files.md into
// l3io-util-doctor (commit 98945ac) would have demanded rows in docs/l3io-util-reference.md
// for set-lock, check-lock and set-status purely because the shared state contract quotes
// them. A guard that cries wolf gets switched off.
//
// self-install is excluded for the same reason the arm above excludes it: internal plumbing,
// deliberately not user-facing surface.
function sharedDocDigests() {
  const digests = new Set();
  for (const rel of walkMarkdown(path.join("skills", "_shared"))) {
    digests.add(createHash("sha256").update(read(rel)).digest("hex"));
  }
  return digests;
}

const MODULE_REFERENCE_RE = /^docs\/(l3io-[a-z0-9-]+)-reference\.md$/;

function checkModuleReferenceCoverage() {
  const real = cliSubcommands();
  const shared = sharedDocDigests();
  const dirs = skillDirNames();

  const codes = new Set();
  for (const dir of dirs) {
    const code = moduleCodeOf(dir);
    if (code) codes.add(code);
  }
  if (codes.size === 0) {
    failures.push(`no skills/*/module.yaml declares a \`code:\` — check 4's module-reference ` +
      `arm would examine nothing and pass in silence`);
    return;
  }

  // Direction 1: every module named by a module.yaml has a reference doc among the live docs.
  // Direction 2: every docs/l3io-*-reference.md names a module that exists.
  const refDocs = new Map();
  for (const rel of LIVE_DOCS) {
    const m = rel.match(MODULE_REFERENCE_RE);
    if (!m) continue;
    if (!codes.has(m[1])) {
      failures.push(`${rel}: is a reference doc for module '${m[1]}', which no ` +
        `skills/*/module.yaml declares (modules: ${[...codes].sort().join(", ")})`);
      continue;
    }
    refDocs.set(m[1], rel);
  }
  for (const code of [...codes].sort()) {
    if (refDocs.has(code)) continue;
    failures.push(`docs/${code}-reference.md: module '${code}' has no reference doc among the ` +
      `live docs — without one, nothing checks what that module documents about pm-status.py`);
  }

  let checked = 0;
  for (const [code, doc] of [...refDocs].sort()) {
    const owned = dirs.filter((d) => d === code || d.startsWith(`${code}-`));
    const invoked = new Map(); // sub -> "file:line" of the first invocation found
    for (const dir of owned) {
      for (const rel of walkMarkdown(path.join("skills", dir))) {
        if (shared.has(createHash("sha256").update(read(rel)).digest("hex"))) continue;
        for (const { sub, line, unreadable } of pmStatusCommands(rel)) {
          if (unreadable) continue;
          if (sub === "self-install" || !real.has(sub)) continue;
          if (!invoked.has(sub)) invoked.set(sub, `${rel}:${line}`);
        }
      }
    }
    const documented = tableRowSubcommands(read(doc));
    for (const [sub, where] of [...invoked].sort()) {
      checked += 1;
      if (documented.has(sub)) continue;
      failures.push(`${doc}: does not document pm-status.py subcommand '${sub}' as a table ` +
        `row, but ${code}'s own skills invoke it (${where})\n      every subcommand a module ` +
        `runs should appear as a '| \`${sub}\` | ... |' row in that module's reference doc`);
    }
  }
  if (verbose) {
    console.log(`  module-reference-coverage: ${refDocs.size} module reference doc(s), ` +
      `${checked} invoked subcommand claim(s) checked`);
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
//
// FLAGS ARE NOW JUDGED TOO, per subcommand, the same way the pm-status arm judges them and
// through the same argparseSurface() extractor. This arm used to read subcommand NAMES only,
// in both directions, and never look at a flag -- `{spec_align} check-pointers --nope X`
// passed. spec-align.py's parser needs two shapes pm-status.py does not use, and the shared
// extractor handles both: six `add_mutually_exclusive_group()` aliases, and the nested
// `lease acquire` / `lease release` subparsers, whose options fold into `lease` because
// `{spec_align} lease acquire --owner E001` is written and judged as one invocation.
// Measured before shipping: 31 flags judged across the tree, 0 offenders.
//
// Extraction is shell-parsed, not regex'd over text: the same logicalLines() + anchor +
// mvdan-sh path the pm-status arm uses, so a `\`-continued invocation is read whole.
const SPEC_ALIGN_TOKEN_RE = /^(?:.*\/)?(?:\{spec_align\}|spec-align\.py)$/;

function* specAlignCommands(rel) {
  for (const { text, line } of logicalLines(read(rel))) {
    const anchors = [];
    for (const m of text.matchAll(/\buv\s+run\b/g)) anchors.push(m.index);
    // The bare `{spec_align}` binding, qualified on code formatting for exactly the reason
    // pmStatusAnchors() qualifies its own bare anchor -- see that function's comment.
    for (const m of text.matchAll(/\{spec_align\}/g)) {
      const before = (text.slice(0, m.index).match(/`/g) || []).length;
      if (before % 2 === 1 && text.indexOf("`", m.index) >= 0) anchors.push(m.index);
    }
    for (const at of [...new Set(anchors)].sort((a, b) => a - b)) {
      let fragment = text.slice(at);
      const closing = fragment.indexOf("`");
      if (closing >= 0) fragment = fragment.slice(0, closing);
      if (!/\{spec_align\}|spec-align\.py/.test(fragment)) continue;
      let commands = shellCommands(fragment);
      if (commands === null) commands = shellCommands(normaliseSynopsis(fragment));
      if (commands === null) continue;
      for (const { argv } of commands) {
        const i = argv.findIndex((t) => typeof t === "string" && SPEC_ALIGN_TOKEN_RE.test(t));
        if (i < 0) continue;
        // spec-align.py's GLOBAL flags come before the subcommand (`--project-root` is
        // required), so the subcommand is not always the next token. Every real invocation in
        // the tree writes them into the `{spec_align}` binding itself and so has the
        // subcommand first, but a doc spelling the path out does not have to -- skip a
        // leading run of options and their values to find it. Those globals belong to the
        // root parser and are deliberately not judged here.
        let j = i + 1;
        while (j < argv.length && typeof argv[j] === "string" && argv[j].startsWith("-")) {
          j += argv[j].includes("=") ? 1 : 2;
        }
        const cmd = argv[j];
        if (typeof cmd !== "string" || !/^[a-z][a-z-]*$/.test(cmd)) continue;
        yield { sub: cmd, argv, at: j, line };
      }
    }
  }
}

function checkSpecAlignFlags() {
  const surface = argparseSurface(SPEC_ALIGN);
  const offenders = [];
  let flagsChecked = 0;
  for (const rel of [...LIVE_DOCS, ...walkMarkdown("skills")]) {
    for (const { sub, argv, at, line } of specAlignCommands(rel)) {
      const entry = surface.get(sub);
      if (!entry) continue;   // an unknown subcommand is the name arm's offence, not this one
      for (const token of argv.slice(at + 1)) {
        if (typeof token !== "string" || !token.startsWith("--") || token === "--") continue;
        const flag = token.split("=")[0];
        flagsChecked += 1;
        if (entry.options.has(flag)) continue;
        offenders.push(`${rel}:${line}: invokes 'spec-align.py ${sub} ${flag}', but ` +
          `spec-align.py registers no such option on '${sub}'\n      ${sub} takes: ` +
          `${[...entry.options].sort().join(" ")}`);
      }
    }
  }
  if (offenders.length) {
    failures.push(`spec-align.py invocations use options their subcommand does not have:\n` +
      `      ${offenders.join("\n      ")}`);
  }
  if (verbose) console.log(`  spec-align-flags: ${flagsChecked} flag(s) checked per subcommand`);
}

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
  checkSpecAlignFlags();
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
  "twenty-four", "twenty-five", "twenty-six"];
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
// 17. No live doc, no runtime directive under skills/, and no CI step under
// .github/workflows/, invokes a PEP-723 script with python3.
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
// THREE CORPORA, TWO PREDICATES, ONE RULE. The shared rule is `pep723Offences()` below, and
// every corpus applies it. They differ only in what makes a line a candidate, because they are
// not the same kind of text:
//
//   .github/workflows/**  is executable. Every `run:` script is fed to the shell parser and the
//     rule alone decides. A `run:` body that does not parse as shell is a FAILURE, not a skip --
//     the fail-closed direction for a file CI actually executes. So is a workflow file that does
//     not parse as YAML.
//
//   LIVE_DOCS (README.md, CLAUDE.md, docs/**.md minus the historical records) and skills/**.md
//     are both prose that quotes shell, decorated with bullets, table pipes and backticks
//     that are not shell at all. A candidate line is still found with PY_INVOKE_RE, exactly as
//     before, because that regex reaches a `- python3 {pm_status} …` bullet or a `| `python3
//     x.py` |` table cell that no shell parser will accept; the rule then decides whether the
//     candidate is exempt. A candidate whose line does not parse as shell is NOT exempted --
//     same fail-closed direction, and the same verdict the old textual exemption reached. Prose
//     that is not a candidate is never parsed, so a sentence like `python3 (3.11+) is needed to
//     run a.py` (not valid shell) is never even offered to the parser.
//
// Scope was widened a SECOND time to include LIVE_DOCS. The rule was enforced in the files
// agents read and unenforced in the files people read: `docs/estimation-guide.md` carried
// FIFTEEN bare `python3 {pm_status} ...` invocations of a script whose PEP-723 header declares
// ruamel.yaml, `docs/l3io-arch-reference.md:73` a sixteenth, and `docs/l3io-sec-reference.md:38`
// a seventeenth -- every one of them a command a human is meant to copy and paste, and every one
// of them invisible to this check because allSkillDocs() walks skills/ and nothing walked docs/.
// The corpus is LIVE_DOCS, the same derived set the live-doc checks use, so the historical
// records under docs/superpowers/** stay out (rewriting them would falsify the record) and a
// new file under docs/ is covered on arrival rather than on someone remembering.
//
// Scope was widened FIRST to include .github/workflows/**: a CI step once ran
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
// Closed since this list was written, each with a mutation test:
//   - `bash -c 'python3 S.py'` and `sh -lc "…"`. The inner string is shell, so it is parsed as
//     shell and judged by the same rule, to a depth of MAX_SHELL_C_DEPTH. See
//     shellDashCScript(). (`xargs python3 S.py` was ALREADY caught, by the over-approximation
//     above -- re-verified with a test rather than taken on the old note's word.)
//   - `PY=$(which python3); $PY S.py`. A command substitution that is a path LOOKUP --
//     `which X`, `command -v X`, `type -p X` -- resolves to X. See commandLookupTarget().
//     Nothing else in a substitution is resolved: this reads a lookup, it does not guess.
//   - a variable from a workflow's `env:`, at workflow, job or step level, in GitHub's own
//     precedence order. See envForRunStep(). A value containing a `${{ }}` expression is not
//     a literal and is not seeded.
//
// Known gaps (listed rather than left to look complete):
//   - a command that reaches python3 through a SECOND FILE -- `make test`, a script that runs
//     a script. Judging those means following the invocation into another file written in
//     another language (a Makefile, in the first case -- and this repo has none for it to
//     reach). The rule sees the argv it is given; it does not open other files.
//   - a variable exported by an EARLIER `run:` step through `$GITHUB_ENV`. That is state
//     carried between steps through a file, so reading it means interpreting one step's
//     writes as another step's inputs. Literal in-script assignments (`PY=python3; $PY S.py`)
//     and `env:` maps ARE resolved.
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

// The one command substitution whose value IS statically known: a lookup of a command's own
// path. `which python3`, `command -v python3` and `type -p python3` all print a path to
// python3, so `PY=$(which python3); $PY s.py` is a python3 invocation the checker can see --
// it was the first entry under "a variable whose value is not statically known", and it is
// the shape a real workflow writes. Anything else in a substitution stays unknown: this
// resolves a lookup, it does not execute anything or guess.
const PATH_LOOKUP_COMMANDS = new Set(["which", "command", "type", "whence"]);

function commandLookupTarget(cmdSubst) {
  const stmts = cmdSubst.Stmts || [];
  if (stmts.length !== 1) return null;
  const cmd = stmts[0].Cmd;
  if (!cmd || syntax.NodeType(cmd) !== "CallExpr") return null;
  const words = (cmd.Args || []).map((w) => (w.Parts || [])
    .map((pt) => (syntax.NodeType(pt) === "Lit" || syntax.NodeType(pt) === "SglQuoted")
      ? pt.Value : null)
    .reduce((acc, v) => (acc === null || v === null ? null : acc + v), ""));
  if (words.some((w) => w === null) || words.length < 2) return null;
  if (!PATH_LOOKUP_COMMANDS.has(words[0].replace(/^.*\//, ""))) return null;
  const last = words[words.length - 1];
  return /^-/.test(last) ? null : last;
}

// Flatten a parsed shell Word to the literal text the shell would produce, or null when part
// of it is an expansion whose value is not statically known (an arithmetic expansion, an
// unresolved parameter, a command substitution that is not a path lookup). Returning null
// rather than a partial string keeps a half-known token from ever comparing equal to `uv`,
// `run` or an interpreter name.
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
      } else if (kind === "CmdSubst" && commandLookupTarget(part) !== null) {
        text += commandLookupTarget(part);
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
// follow it instead of producing one. `seed` supplies variables the script inherits rather
// than sets -- a workflow's `env:` maps, which are the other half of the
// "value not statically known" gap. Returns null when the script is not valid shell.
function shellCommands(script, seed) {
  let file;
  try {
    file = shellParser.Parse(script, "run");
  } catch {
    return null;
  }
  const vars = new Map(seed || []);
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

// A command that hands a whole script to another shell: `bash -c '…'`, `sh -lc '…'`,
// `zsh -c …`. The inner string is shell, so it is parsed as shell and judged by the same
// rule -- closing the first half of the "reaches python3 through another program's argument
// parsing" gap. The other halves (`make target`, a script that runs a script) are NOT closed:
// both mean following the invocation into ANOTHER FILE written in another language, and the
// repo has no Makefile for the first to even reach. That remains recorded as a gap.
const SHELL_COMMANDS = new Set(["sh", "bash", "zsh", "dash", "ksh", "ash", "busybox"]);
const MAX_SHELL_C_DEPTH = 3;

function shellDashCScript(argv) {
  if (argv.length < 2 || typeof argv[0] !== "string") return null;
  if (!SHELL_COMMANDS.has(argv[0].replace(/^.*\//, ""))) return null;
  for (let i = 1; i < argv.length; i += 1) {
    const tok = argv[i];
    if (typeof tok !== "string") return null;
    // `-c`, or a cluster containing it (`-lc`, `-ec`, `-euxc`). A long option never carries it.
    if (/^-[^-]*c[^-]*$/.test(tok)) {
      const script = argv[i + 1];
      return typeof script === "string" ? script : null;
    }
    if (!tok.startsWith("-")) return null;   // the first non-option ends the option run
  }
  return null;
}

// Every offending command in a shell script. null means the script is not valid shell -- the
// caller decides what that means for its corpus.
function pep723Offences(script, seed, depth = 0) {
  const commands = shellCommands(script, seed);
  if (commands === null) return null;
  const out = [];
  for (const c of commands) {
    const offence = commandOffence(c.argv);
    if (offence !== null) { out.push({ line: c.line, offence }); continue; }
    if (depth >= MAX_SHELL_C_DEPTH) continue;
    const inner = shellDashCScript(stripWrappers(c.argv));
    if (inner === null) continue;
    for (const nested of pep723Offences(inner, seed, depth + 1) || []) {
      // The inner script's own line numbers are meaningless outside it; report the line the
      // wrapping command sits on, which is the line a reader has to edit.
      out.push({ line: c.line, offence: nested.offence });
    }
  }
  return out;
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

// A mapping node's literal string entries, for an `env:` block. A non-scalar or non-string
// value (an expression, a nested map) is simply not seeded -- an unknown variable stays
// unknown, which is where it was before.
function literalEnvMap(node) {
  const out = new Map();
  if (!YAML.isMap(node)) return out;
  for (const pair of node.items) {
    if (!YAML.isScalar(pair.key) || typeof pair.key.value !== "string") continue;
    if (!YAML.isScalar(pair.value) || typeof pair.value.value !== "string") continue;
    if (/\$\{\{/.test(pair.value.value)) continue;   // a GitHub expression, not a literal
    out.set(pair.key.value, pair.value.value);
  }
  return out;
}

// The env a `run:` step inherits: workflow-level, then the job's, then the step's own, in
// GitHub's own precedence order. This closes the `env:`-at-job-level half of the
// "value not statically known" gap -- `env: {PY: python3}` plus `run: $PY s.py` used to be
// invisible. What is still NOT closed is a variable a PREVIOUS step exported through
// $GITHUB_ENV: that is state carried between steps through a file, and reading it means
// interpreting one step's writes as another step's inputs.
function envForRunStep(doc, pairPath) {
  const seed = new Map();
  const apply = (node) => { for (const [k, v] of literalEnvMap(node)) seed.set(k, v); };
  for (const ancestor of pairPath) {
    if (!YAML.isMap(ancestor)) continue;
    const env = ancestor.items.find((it) => YAML.isScalar(it.key) && it.key.value === "env");
    if (env) apply(env.value);
  }
  return seed;
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
    Pair(_key, pair, pairPath) {
      if (!YAML.isScalar(pair.key) || pair.key.value !== "run") return;
      if (!YAML.isScalar(pair.value) || typeof pair.value.value !== "string") return;
      const script = pair.value.value;
      const startLine = lineOfOffset(pair.value.range ? pair.value.range[0] : pair.key.range[0]);
      // A block scalar's content begins on the line after its `|`/`>` indicator, so a command's
      // in-script line number maps onto the file. Any other scalar occupies one starting line
      // and may carry escapes, so the whole script is reported against that line.
      const isBlock = typeof pair.value.type === "string" && pair.value.type.startsWith("BLOCK");
      const offences = pep723Offences(script, envForRunStep(doc, pairPath));
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
  // LIVE_DOCS is listed first because it is the corpus this check was blind to longest, and
  // the one whose offences a human copy-pastes. It is the same derived set every live-doc
  // check uses, so a new file under docs/ is covered on arrival.
  const offenders = [
    ...LIVE_DOCS.flatMap(scanMarkdownForPep723),
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
  const dirs = skillDirNames();
  // moduleCodeOf() is the one derivation of "which module is this skill's home", shared with
  // check 4's module-reference arm, so the two can never disagree about the module set.
  const homeOfCode = new Map();
  for (const dir of dirs) {
    const code = moduleCodeOf(dir);
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
// Both sides are derived. The skill set and the directories a skill really has both come from
// `git ls-files` (so a new skill with no row fails rather than being silently unlisted), and
// the claims come from the fenced block itself. Nothing here is a hand-kept list.
//
// WHY GIT AND NOT readdirSync. "On disk" and "in the repository" are not the same set, and
// this check is about the repository: README describes what a reader clones, not what a local
// build left behind. It used to ask the filesystem, and a gitignored `__pycache__/` -- dropped
// under skills/l3io-pm-plan/scripts/ by an interpreter run before that skill's pm-status.py
// payload copy was cut -- made the gate demand a README row for a `scripts/` directory that
// does not exist as far as the repo is concerned. The row was CORRECT and the gate was RED, in
// a shared checkout, with nothing to fix. A guard that cries wolf gets switched off.
//
// Fallback, stated rather than hidden: when repoRoot is not the top level of a git work tree
// (the test fixtures are plain temp copies), the filesystem answer is used instead and a note
// records it under -v. That direction is strictly the old, stricter behaviour -- it can only
// demand MORE rows, never fewer -- so it cannot turn a real drift green. The git path itself is
// anchored by tests that build a real git work tree; see scripts/tests/check-docs.test.mjs.
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

// Every path git tracks under repoRoot, or null when repoRoot is not a git work tree's top
// level. Asked once per run and cached: `ls-files` over this repo is one process, and the
// answer cannot change under a checker that never writes.
//
// The top-level check is not ceremony. Without it, `git -C <temp dir>` walks UP out of the
// directory it was given and answers about whatever repository it finds above it -- which for
// a fixture under /tmp is either nothing or, worse, an unrelated repo.
let trackedPathsCache;
function trackedPaths() {
  if (trackedPathsCache !== undefined) return trackedPathsCache;
  trackedPathsCache = null;
  const top = spawnSync("git", ["-C", repoRoot, "rev-parse", "--show-toplevel"],
    { encoding: "utf8" });
  if (top.status !== 0) return trackedPathsCache;
  if (path.resolve(top.stdout.trim()) !== path.resolve(repoRoot)) return trackedPathsCache;
  const ls = spawnSync("git", ["-C", repoRoot, "ls-files", "-z"],
    { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (ls.status !== 0) return trackedPathsCache;
  trackedPathsCache = ls.stdout.split("\0").filter(Boolean);
  return trackedPathsCache;
}

// The first path segment of everything tracked under `prefix`, split into the names that are
// DIRECTORIES there (a tracked file lives below them) and the names that are files.
function trackedEntries(prefix) {
  const tracked = trackedPaths();
  if (tracked === null) return null;
  const dirs = new Set();
  for (const rel of tracked) {
    if (!rel.startsWith(prefix)) continue;
    const rest = rel.slice(prefix.length);
    const slash = rest.indexOf("/");
    if (slash > 0) dirs.add(rest.slice(0, slash));
  }
  return dirs;
}
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
  const trackedSkillDirs = trackedEntries("skills/");
  if (trackedSkillDirs === null) {
    notes.push(`check 22: ${repoRoot} is not a git work tree top level, so "what is on disk" ` +
      `fell back to the filesystem — a gitignored build artifact under a skill can produce a ` +
      `false positive here`);
  }
  const skillDirs = trackedSkillDirs ?? new Set(
    fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => e.name),
  );
  const skills = [...skillDirs].filter((name) => name.startsWith("l3io-")).sort();
  // The message names the set it actually consulted, so a reader is never told a directory is
  // "not tracked" by a run that never asked git.
  const fromGit = trackedSkillDirs !== null;
  const present = (n) => (fromGit
    ? `${n === 1 ? "is" : "are"} tracked in the repository`
    : `exist${n === 1 ? "s" : ""} on disk`);
  const absent = (n) => (fromGit
    ? `${n === 1 ? "is" : "are"} not tracked in the repository`
    : `${n === 1 ? "does" : "do"} not exist on disk`);

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
    const onDisk = trackedEntries(`skills/${skill}/`) ?? new Set(
      fs.readdirSync(path.join(repoRoot, "skills", skill), { withFileTypes: true })
        .filter((e) => e.isDirectory())
        .map((e) => e.name),
    );
    checked += 1;
    const missing = [...onDisk].filter((d) => !listed.has(d)).sort();
    const phantom = [...listed].filter((d) => !onDisk.has(d)).sort();
    if (missing.length) {
      failures.push(`${REPO_LAYOUT_DOC}: the skills/${skill}/ row does not list ` +
        `${missing.map((d) => `${d}/`).join(", ")}, which ` +
        `${present(missing.length)}`);
    }
    if (phantom.length) {
      failures.push(`${REPO_LAYOUT_DOC}: the skills/${skill}/ row lists ` +
        `${phantom.map((d) => `${d}/`).join(", ")}, which ` +
        `${absent(phantom.length)}`);
    }
  }
  if (verbose) {
    console.log(`  readme-repo-layout: ${checked} skill row(s) matched against ` +
      `${trackedSkillDirs === null ? "the filesystem (git unavailable)" : "git's tracked tree"}`);
  }
}

// ---------------------------------------------------------------------------
// 23. `.claude-plugin/marketplace.json`'s `dependencies` block agrees with the declared
// inventory, `skills/l3io-util-doctor/assets/bmad-dependencies.json`.
//
// Why: the marketplace block is the first thing a prospective consumer reads about what this
// package needs, and nothing read it. Measured at the time this check was written, it
// declared three DEPRECATED shims (`bmad-create-story`, `bmad-dev-story`,
// `bmad-review-adversarial-general`) as **required**, omitted two skills that really are
// required (`bmad-sprint-planning`, `bmad-review`), and listed one skill BMad removed
// (`bmad-ux-review`) as optional. Check 16 had kept the inventory honest against the runtime
// directives for a year; the marketplace copy of the same facts drifted beside it, unguarded
// — a second copy of a surface that nothing verifies, the same shape as M-2(2)'s digest.
//
// Both sides are derived. The expected sets come from the inventory's own `status` field, and
// the actual sets from the marketplace file; neither is typed here. A skill the inventory
// reclassifies moves in both directions on the next run.
//
// One deliberate carve-out: an entry that is not a `bmad-*` name is this package's own
// intra-package dependency (`l3io-arch-review` — the epic architecture gate and the story
// technical-AC checklist self-skip without it). The inventory declares BMad's skills, not
// ours, so those are checked against `skills/` instead of against it.
const MARKETPLACE = ".claude-plugin/marketplace.json";

function checkMarketplaceDependencies() {
  if (!exists(MARKETPLACE) || !exists(DEP_INVENTORY)) {
    failures.push(`${MARKETPLACE} or ${DEP_INVENTORY} is missing — check 23 has nothing to ` +
      `compare, which is a scope failure, not a pass`);
    return;
  }

  let inventory;
  let marketplace;
  try {
    inventory = JSON.parse(read(DEP_INVENTORY));
    marketplace = JSON.parse(read(MARKETPLACE));
  } catch (e) {
    failures.push(`${MARKETPLACE}/${DEP_INVENTORY}: not valid JSON (${e.message})`);
    return;
  }

  const declared = Array.isArray(inventory.skills) ? inventory.skills : [];
  if (declared.length === 0) {
    failures.push(`${DEP_INVENTORY}: declares no skills — check 23 would compare against an ` +
      `empty set and pass in silence`);
    return;
  }
  const byStatus = (status) =>
    new Set(declared.filter((s) => s.status === status).map((s) => s.name));
  const modules = new Set(declared.map((s) => s.module).filter(Boolean));

  const deps = marketplace.dependencies || {};
  const ownSkills = new Set(
    fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
      .filter((e) => e.isDirectory() && e.name !== "_shared")
      .map((e) => e.name),
  );

  let checked = 0;
  for (const [field, status] of [["required-skills", "required"], ["optional-skills", "optional"]]) {
    const listed = Array.isArray(deps[field]) ? deps[field] : null;
    if (listed === null) {
      failures.push(`${MARKETPLACE}: dependencies.${field} is missing or not an array`);
      continue;
    }
    const expected = byStatus(status);
    const actualBmad = new Set(listed.filter((n) => n.startsWith("bmad-")));

    for (const name of listed) {
      checked += 1;
      if (name.startsWith("bmad-")) continue;
      if (ownSkills.has(name)) continue;
      failures.push(`${MARKETPLACE}: dependencies.${field} names '${name}', which is neither ` +
        `a bmad-* skill nor a directory under skills/`);
    }
    for (const name of [...expected].sort()) {
      if (actualBmad.has(name)) continue;
      const entry = declared.find((s) => s.name === name);
      failures.push(`${MARKETPLACE}: dependencies.${field} omits '${name}', which ` +
        `${DEP_INVENTORY} declares '${status}'${entry?.module ? ` (module ${entry.module})` : ""}`);
    }
    for (const name of [...actualBmad].sort()) {
      if (expected.has(name)) continue;
      const entry = declared.find((s) => s.name === name);
      failures.push(`${MARKETPLACE}: dependencies.${field} names '${name}', which ` +
        `${DEP_INVENTORY} declares ` +
        `${entry ? `'${entry.status}'` : "not at all"} — not '${status}'`);
    }
  }

  const declaredModule = deps["bmad-module"];
  checked += 1;
  if (!modules.has(declaredModule)) {
    failures.push(`${MARKETPLACE}: dependencies.bmad-module is '${declaredModule}', which no ` +
      `entry in ${DEP_INVENTORY} names as its module (inventory uses: ` +
      `${[...modules].sort().join(", ")})`);
  }

  if (verbose) {
    console.log(`  marketplace-deps: ${checked} dependency entr(ies) checked against ` +
      `${declared.length} declared skill(s)`);
  }
}

// ---------------------------------------------------------------------------
// 24. Every skill-relative pointer inside a shared file resolves in EVERY skill that file's
// sync group ships it to.
//
// Why: a file in skills/_shared/ is authored once and copied into several skills, so a
// pointer inside it is evaluated N times against N different directories. `references/…`,
// `assets/…`, `steps/…` and `scripts/…` are all skill-relative, so a pointer that is true in
// the skill the author had in mind is a pointer at nothing in the others -- and BMad installs
// skills independently, so "the other skill has it" is not a fallback a reader can use.
//
// Caught in practice: a 2026-09-22 sweep of skills/*/**.md found 337 such pointers with 56
// unresolved in the skill carrying them. Every one was a shared file naming a file only one
// of its consumers ships -- `metrics-contract.md` citing `steps/sprint/step-04-sprint-closure.md`
// (l3io-pm-execute only), `config-resolution.md` citing `assets/module-setup.md` (module homes
// only), and `status-files.md`, newly shipped to l3io-util-doctor, importing its own onward
// pointers into a skill that carries none of them.
//
// SCOPE IS DERIVED, NOT ENUMERATED (repo CLAUDE.md §4). Both halves come from
// sync-shared-scripts.mjs's own syncGroups, read by spawning the checked tree's copy with
// --dump-deliveries: which files are shared, and which skills each one lands in. A new sync
// group, a widened `dirs`, or a new shared .md is covered the moment it is added. There is no
// allowlist and no list of paths here to go stale.
//
// WHAT COUNTS AS A POINTER: a whole backtick span that is a path starting `references/`,
// `assets/`, `steps/` or `scripts/` (optionally behind `{skill-root}/` or `./`). A span with
// any other root -- `{project-root}/…`, `{implementation_artifacts}/…`, `l3io-pm-execute/…` --
// is not skill-relative and is not judged as one. A span whose first segment IS a real skill
// directory is judged too, against THAT skill: that is the shape this check's own fixes use
// (`l3io-sec-redteam/references/scope-mapping.md`), so the replacement is guarded as well as
// the thing it replaced.
//
// THE ONE EXEMPTION, and it is derived rather than allowlisted: a pointer whose LINE also
// names a real skill directory in which the path does resolve. That is the attribution shape
// the original sweep excluded ("`l3io-util-doctor`'s own `steps/stats.md`") and it carries the
// information a reader needs -- which skill to look in. It is mechanical: the named directory
// must exist under skills/ AND must actually contain the file. Naming a skill that does not
// have it exempts nothing.
//
// FALSE-POSITIVE SURFACE, measured against this tree rather than asserted. Exactly one shape
// can red on correct prose: a sentence stating a NEGATIVE ("the four operational skills do not
// carry `assets/module-setup.md`"). config-resolution.md had the only one, and the fix was to
// name where the file DOES live on the same line, which the sentence should have said anyway.
// The whole tree is otherwise green. If this ever fires on a second negative statement, add
// the "it lives in X" half rather than a silencer.
//
// NOT CHECKED, stated so nobody has to discover it:
//   - files a sync group ships that are not .md (the .py payloads). Their pointers are in
//     Python source, not backtick spans.
//   - pointers in a skill's OWN files. This check's corpus is the shared set only; a
//     l3io-util-doctor step file naming a l3io-util-doctor reference that does not exist is
//     not in scope here, and nothing else checks it either.
//   - whether the pointed-at SECTION exists. Check 3 does that for `<file>.md §N`.
//   - a pointer split across a line break, which the line-scoped scan cannot see as one span.
// ---------------------------------------------------------------------------
const SHARED_POINTER_RE =
  /`(?:\{skill-root\}\/|\.\/)?((?:references|assets|steps|scripts)\/[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*)`/g;
const QUALIFIED_POINTER_RE =
  /`(l3io-[a-z0-9-]+)\/((?:references|assets|steps|scripts)\/[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*)`/g;

function syncDeliveries() {
  const script = path.join(repoRoot, SYNC_SCRIPT);
  const r = spawnSync(process.execPath, [script, "--dump-deliveries"],
    { cwd: repoRoot, encoding: "utf8" });
  if (r.status !== 0) {
    return { error: `${SYNC_SCRIPT} --dump-deliveries exited ${r.status}: ` +
      `${(r.stderr || "").trim().split("\n")[0] || "no output"}` };
  }
  try {
    return { deliveries: JSON.parse(r.stdout) };
  } catch (e) {
    return { error: `${SYNC_SCRIPT} --dump-deliveries did not print JSON (${e.message})` };
  }
}

function checkSharedPointerResolution() {
  const { deliveries, error } = syncDeliveries();
  if (error) {
    failures.push(`check 24 cannot derive its scope — ${error}. It reads the sync groups from ` +
      `the sync script itself; a hand-kept copy of that list here would drift from it.`);
    return;
  }
  const realSkills = new Set(skillDirNames());
  // source -> union of destination skills, across every group naming that source.
  const bySource = new Map();
  for (const d of deliveries) {
    if (!d.source.endsWith(".md")) continue;
    if (!bySource.has(d.source)) bySource.set(d.source, new Set());
    for (const skill of d.skills) bySource.get(d.source).add(skill);
  }

  const offenders = [];
  let pointers = 0;
  for (const [source, skillSet] of [...bySource].sort()) {
    if (!exists(source)) continue;
    const skills = [...skillSet].sort();
    read(source).split("\n").forEach((line, i) => {
      // Attribution: skills named on this line that actually carry the path in question.
      const named = [...realSkills].filter((sk) => line.includes(sk));
      const judge = (rel, owners, label) => {
        pointers += 1;
        const missing = owners.filter((sk) => !exists(path.posix.join("skills", sk, rel)));
        if (missing.length === 0) return;
        if (named.some((sk) => exists(path.posix.join("skills", sk, rel)))) return;
        offenders.push(`${source}:${i + 1}: ${label} does not exist in ` +
          `${missing.join(", ")} — this file is shipped to ${skills.join(", ")}, and nothing ` +
          `on the line names a skill that has it: ${line.trim().slice(0, 120)}`);
      };
      for (const m of line.matchAll(SHARED_POINTER_RE)) judge(m[1], skills, `\`${m[1]}\``);
      for (const m of line.matchAll(QUALIFIED_POINTER_RE)) {
        if (!realSkills.has(m[1])) continue;
        judge(m[2], [m[1]], `\`${m[1]}/${m[2]}\``);
      }
    });
  }

  if (offenders.length) {
    failures.push(`shared files point at paths their consumers do not carry (a pointer inside ` +
      `a synced file must resolve in every skill that file is shipped to — reword it to name ` +
      `the owning skill, or ship the target):\n      ${offenders.join("\n      ")}`);
  }
  if (verbose) {
    console.log(`  shared-pointers: ${pointers} pointer(s) across ${bySource.size} shared ` +
      `.md file(s), ${offenders.length} unresolved`);
  }
}

// ---------------------------------------------------------------------------

// The external anchor for pmStatusSubcommandOptions(), exposed through the entry point CI
// runs rather than by exporting a function, because importing this module runs the checks.
// scripts/tests/check-docs.test.mjs calls this, runs the REAL build_parser() under uv once,
// and asserts the two agree set-for-set in both directions. Not a check: it prints and exits.
if (process.argv.includes("--dump-subcommand-options")) {
  const dump = {};
  for (const [sub, opts] of [...pmStatusSubcommandOptions()].sort()) dump[sub] = [...opts].sort();
  console.log(JSON.stringify(dump));
  process.exit(0);
}

// ---------------------------------------------------------------------------
// 25. Every `/l3io-util-doctor <keyword>` invocation names a keyword that exists.
//
// A removed mode keyword left named somewhere is a runtime defect, not a documentation nit.
// The doctor's router sends any argument it does not recognise to the health check
// (SKILL.md, "Everything else"), so a directive that still says `/l3io-util-doctor overlay`
// does not error -- it silently runs a full project scan instead of the thing it named, and
// the user has no way to tell. Check 1 validates l3io-* SKILL names; nothing validated the
// MODE keywords underneath them, and Task 0C removed five of them by hand.
//
// The valid set is DERIVED from the routing table in SKILL.md -- every backticked token in
// the first cell of a routing row -- never enumerated here. That is the same source of truth
// check 15 counts, so a keyword added or removed moves this check with it, in the same edit.
//
// The corpus is LIVE_DOCS plus every text file under skills/, not only markdown: the doctor's
// own scripts print these invocations in user-facing messages (pm-status.py and spec-align.py
// both name `/l3io-util-doctor triage`), and a dangling keyword in an error message is worse
// than one in a doc, because the user is already stuck when they read it.
//
// KNOWN GAPS -- what this check cannot see, stated so the next reader does not assume cover:
//
//   1. A single-word keyword followed by prose. The rule below reads the token after the
//      command as an argument UNLESS it is followed by whitespace and another lowercase word,
//      because English prose puts one there constantly ("Run /l3io-util-doctor for a health
//      check", "...to install it"). Measured over the whole live tree at the time of writing,
//      that exemption is what keeps the false-positive count at zero; without it there are
//      three prose sites and no real findings. The cost is that
//      "/l3io-util-doctor overlay to see what is customizable" is invisible. A HYPHENATED
//      token is always checked, prose or not, because English does not put one there -- and
//      twelve of the doctor's sixteen keywords are hyphenated, so the reach is most of the set
//      and all of the migration-critical part of it.
//   2. An invocation written some other way -- "the overlay mode", "pass `overlay`", a
//      keyword named in a table cell. Deliberate: docs/upgrading.md must be able to say which
//      keywords were removed and what replaced them, exactly as check 1 lets a doc map a
//      removed skill to its replacement.
//
//      This gap has now cost something, so here is what closing it would cost. README.md's
//      /l3io-util-doctor row listed `overlay` -- removed by d91cb8f -- as a keyword you can
//      "skip directly to", in the same sentence that links docs/l3io-util-reference.md, which
//      says "There is no `overlay` keyword". It sat there through every gate and was found by
//      a human reading in 2026-09-23's independent validation. Two closures were measured
//      against the whole live-doc corpus before this text was written, and neither is worth
//      taking:
//        - THE GENERAL FORM -- treat every backticked lowercase token on a line that mentions
//          /l3io-util-doctor as a claimed keyword. 87 such lines; 56 tokens judged; 45
//          reported, of which ONE is real. A 44-item false-positive surface made of statuses
//          (`done`, `ready-for-dev`), resolutions (`fixed`, `wontfix`), pm-status.py
//          subcommands (`set-status`, `append-issue`) and sibling skill names. That is the
//          checker-that-cries-wolf this file's header refuses to write.
//        - THE NARROW FORM that does catch it -- a gloss list, `` `token` (description) ``,
//          on a line carrying three or more tokens that ARE valid keywords. 0 false
//          positives. But its scope across every live doc is exactly ONE LINE (README.md's
//          row), and it stays one line whether or not the rule is right, so it proves nothing
//          about its own reach (root CLAUDE.md section 4). Guarding it against vacuity needs a
//          "at least one such line must exist" threshold, which is a hand-kept fact about one
//          sentence and turns a legitimate README rewrite red on correct prose.
//      So the gap stays open, with the number attached rather than the bare assertion: the
//      keyword enumeration in README.md is documentation of the routing table that NOTHING
//      mechanically ties back to it. A reader changing that table should grep README for the
//      keyword by hand.
//
// SECOND ARM -- mode-file pointers. A removed mode leaves a second kind of dangling reference:
// a sibling step file still telling the agent to load `steps/<name>.md`. That is worse than a
// stale keyword, because the instruction is to READ A FILE THAT IS NOT THERE. It survived the
// whole of Task 0C's hand sweep and every gate (steps/sort-status.md pointed at
// steps/rename-epic-dirs.md), which is the evidence for this arm existing. Every unqualified
// `steps/<name>.md` inside skills/l3io-util-doctor/ must resolve there; a pointer written
// `<other-skill>/steps/<name>.md` is a cross-skill reference and is skipped, because it
// resolves against that skill, not this one.
// ---------------------------------------------------------------------------
const DOCTOR_ROUTING_ROW_RE = /^\| ((?:`[^`|]+`(?:[,/]| or )?\s*)+)\|/gm;
const DOCTOR_INVOCATION_RE = /\/l3io-util-(?:doctor|cleanup)[ \t]+([a-z][a-z0-9-]*)/g;
const DOCTOR_CORPUS_EXT = [".md", ".py", ".yaml", ".yml", ".toml", ".csv", ".json", ".txt"];

function* walkTextFiles(rel) {
  const abs = path.join(repoRoot, rel);
  if (!fs.existsSync(abs)) return;
  for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
    const child = path.posix.join(rel, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__pycache__" || entry.name === "node_modules") continue;
      yield* walkTextFiles(child);
    } else if (DOCTOR_CORPUS_EXT.some((e) => entry.name.endsWith(e))) {
      yield child;
    }
  }
}

function checkDoctorModeKeywords() {
  // doctorRoutingTable() is the one place that parses the table -- shared with check 4's
  // fallback-arm exemption (doctorModeKeywords()), so the two checks can never derive
  // disagreeing keyword sets from the same source.
  const { valid, rows } = doctorRoutingTable();
  // The set is derived, so a reshaped table would silently derive an EMPTY set and pass
  // everything. Refuse that outcome rather than report a green over nothing.
  if (rows < 5 || valid.size < 5) {
    failures.push(`${DOCTOR_DIR}/SKILL.md: the routing table did not parse — ${rows} row(s), ` +
      `${valid.size} keyword(s). check 25 derives the valid keyword set from it, so it cannot ` +
      `run at all until the table is readable again`);
    return;
  }
  let scanned = 0;
  for (const rel of [...LIVE_DOCS, ...walkTextFiles("skills")]) {
    let text;
    try { text = read(rel); } catch { continue; }
    scanned++;
    for (const m of text.matchAll(DOCTOR_INVOCATION_RE)) {
      const token = m[1];
      if (valid.has(token)) continue;
      const after = text.slice(m.index + m[0].length, m.index + m[0].length + 2);
      if (/^\s[a-z]/.test(after) && !token.includes("-")) continue; // prose, per gap 1
      const line = text.slice(0, m.index).split("\n").length;
      failures.push(`${rel}:${line}: names /l3io-util-doctor ${token}, which is not a keyword ` +
        `the doctor's routing table has — the router sends an unrecognised argument to the ` +
        `health check, so this silently runs a project scan instead. Valid: ` +
        `${[...valid].sort().join(", ")}`);
    }
  }

  let pointers = 0;
  for (const rel of walkTextFiles(DOCTOR_DIR)) {
    let text;
    try { text = read(rel); } catch { continue; }
    for (const m of text.matchAll(/(\S*?)steps\/([a-z0-9-]+\.md)/g)) {
      if (m[1].endsWith("/")) continue; // qualified against another skill
      pointers++;
      if (exists(`${DOCTOR_DIR}/steps/${m[2]}`)) continue;
      const line = text.slice(0, m.index).split("\n").length;
      failures.push(`${rel}:${line}: points at steps/${m[2]}, which ${DOCTOR_DIR} does not ` +
        `carry — a directive to load a file that is not there. Name the mode that absorbed ` +
        `it, or qualify the pointer with the skill that has it`);
    }
  }
  if (verbose) {
    console.log(`  doctor-mode-keywords: ${valid.size} keyword(s), ${scanned} file(s), ` +
      `${pointers} mode-file pointer(s)`);
  }
}

// ---------------------------------------------------------------------------
// 26. State paths are assembled ONLY in pm-status.py's resolver section.
//
// CLAUDE.md states pm-status.py "is the only place that resolves a key to a file
// location". Two doctor procedures were standing exceptions: bootstrap-state.md at SIX
// sites (with its own inline ruamel write_node, bypassing the epic write lock, the event
// log and status validation) and migrate-state.md at three. Both are now routed through
// `import-node`; this check is what keeps them routed.
//
// TWO HALVES, and the second is the load-bearing one:
//   (a) inside pm-status.py -- assembly appears only between the resolver section's
//       marker comments. The markers are matched by TEXT, not line number, so the bounds
//       survive edits above them.
//   (b) across skills/ -- no file assembles a state path at all.
//
// SCOPE IS DERIVED from the tree (every .md and .py under skills/), never enumerated. A
// guard scoped to the two known offenders would have passed over any third one and
// reported success -- the same shape as the vacuous Stage E gate it exists to prevent.
//
// EXEMPTIONS, derived rather than listed by hand: skills/_shared/status-files.md is the
// canonical state-layout contract and has to describe the layout; its synced
// references/status-files.md copies are the same bytes, so they are exempt by the same
// rule rather than by a second entry.
//
// KNOWN GAPS:
// (1) FALSE-NEGATIVE: a path built from a variable whose value is "epic-" assigned elsewhere
//     is not flagged. Stated here so a reader need not discover it.
// (2) FALSE-NEGATIVE: a STATE_PATH_RE match on a line with NONE of the state-context tokens
//     (state, planned, active, archived, state_root, pm_state_root) is suppressed by the
//     STATE_CONTEXT_RE guard — it is far more likely to be an artifact-path assembly
//     ({implementation_artifacts}/epic-{nnn}/..., which is a separate concern) than a
//     state-path assembly. Any artifact-path template written on a line that also
//     happens to carry a state-context token would be a false positive; none exist in the
//     current tree.
//
// CATEGORICAL EXEMPTIONS: SKILL.md (skill overview docs describe layout, not direct it),
// test-*.py / *.test.mjs files (tests legitimately assemble paths for fixtures), Python
// comments (# on line start), and lines inside triple-quoted docstrings in .py files.
// Each closes a class of legitimate false positives the plan's regex over-caught.
//
// ACTIVE-VERB CONJUNCT: lines containing a state-path pattern without any filesystem verb
// (mkdir, ls, os.path.join, Path(...), diff, etc.) are treated as descriptive prose, not
// runtime assembly — this exempts 12 sites in step files that describe the layout in prose
// while keeping the real shell probes flagged (marked with check26:allow below). Five sites
// that read state via `ls -d`/`diff <(ls ...)` exist because pm-status.py has no
// "does this epic exist?" verb; they are suppressed by inline check26:allow markers.
// docs/superpowers/plans/2026-09-24-followup-pm-status-exists-verb.md tracks the follow-up.
//
// check26:allow SITES (state-existence read probes, not path-assembly violations):
//   skills/l3io-pm-help/steps/mode-list-plan.md   — ls -d to find which bucket holds the epic
//   skills/l3io-util-doctor/steps/health-check.md — diff <(ls ...) state/artifact mirror check

const RESOLVER_START_MARKER =
  'Sharded layout resolution — the ONLY place that knows where nodes live'
const RESOLVER_END_MARKER =
  'computed roll-ups — sprint/epic aggregates over per-story child files'

const STATE_PATH_RE =
  /(?:mkdir\s+-p\s+|["'`(]|\/)\s*\{?[\w.\-/{}]*\}?\/?(?:epic-\{?n{2,3}\}?|epic-\{int|sprint-\{?n{1,2}\}?)/

// Require at least one state-context token on the same line so that artifact-path
// templates ({implementation_artifacts}/epic-{nnn}/...) and documentation tables
// that merely NAME the pattern are not caught. A violation must have BOTH.
const STATE_CONTEXT_RE = /\b(?:state|planned|active|archived|state_root|pm_state_root)\b/

// Require at least one active filesystem verb on the line — lines with only a state-path
// pattern and no verb are descriptive prose, not runtime state-path assembly.
const ACTIVE_VERB_RE = /\b(?:mkdir|ls|rm|cp|mv|touch|open|Path|makedirs|rmtree|move|copy|glob|diff|find|test)\b|os\.path\.join|os\.makedirs|shutil\.|\.write\(|\.write_text\(/

// Inline suppression marker — `check26:allow reason: <text>` on the current line or the
// immediately preceding line. Use this only for legitimate read probes (existence checks via
// `ls`/`diff <(ls ...)`) that exist because pm-status.py has no existence-check verb.
// Every marker requires a reason after the colon.
const CHECK26_ALLOW_RE = /check26:allow(?:\s+reason:\s*\S+)?/

function isStatusFilesContract(file) {
  return file === 'skills/_shared/status-files.md' ||
    file.endsWith('/references/status-files.md')
}

// Categorical exemptions for the (b) half of resolverInvariant: file types where state-path
// templates are legitimate and not state-path assembly.
function isCategoricallyExempt(file) {
  // SKILL.md: skill overview docs describe the state layout, they do not direct assembly.
  if (/\/SKILL\.md$/.test(file)) return true
  // Test files: legitimately build paths to populate fixtures; not runtime assembly.
  if (/(?:^|\/)test[-_].*\.py$/.test(file)) return true
  if (file.endsWith('.test.mjs')) return true
  return false
}

// Walk every file under `skills/` whose name ends in one of `exts`, returning repo-relative
// posix paths. Used by resolverInvariant() to derive scope from the tree.
function walkSkillFiles(exts) {
  const out = []
  const walk = (rel) => {
    for (const entry of fs.readdirSync(path.join(repoRoot, rel), { withFileTypes: true })) {
      const child = path.posix.join(rel, entry.name)
      if (entry.isDirectory()) walk(child)
      else if (exts.some((e) => entry.name.endsWith(e))) out.push(child)
    }
  }
  walk('skills')
  return out
}

export function resolverInvariant(opts = {}) {
  const violations = []
  const scannedFiles = []

  // (a) pm-status.py: state-path assembly must appear only inside the resolver section.
  const pmPath = 'skills/_shared/pm-status.py'
  const pmLines = read(pmPath).split('\n')
  if (opts.plantInPmStatus) {
    pmLines.splice(opts.plantInPmStatus.line - 1, 0, opts.plantInPmStatus.text)
  }
  const start = pmLines.findIndex((l) => l.includes(RESOLVER_START_MARKER))
  const end = pmLines.findIndex((l) => l.includes(RESOLVER_END_MARKER))
  if (start < 0 || end < 0) {
    violations.push(`${pmPath}: resolver section markers not found — cannot judge scope`)
  } else {
    let pmInDocstring = false
    pmLines.forEach((line, i) => {
      const n = i + 1
      if (n > start + 1 && n < end + 1) return    // inside the resolver section — allowed
      // Track triple-quoted docstrings; skip lines that start inside or cross a boundary.
      const tripleCount = (line.match(/"""|'''/g) || []).length
      const wasPmInDocstring = pmInDocstring
      if (tripleCount % 2 === 1) pmInDocstring = !pmInDocstring
      if (wasPmInDocstring || tripleCount > 0) return
      if (line.trimStart().startsWith('#')) return  // pure comment line, not code
      if (STATE_PATH_RE.test(line) && STATE_CONTEXT_RE.test(line) && ACTIVE_VERB_RE.test(line)) {
        if (CHECK26_ALLOW_RE.test(line) || (i > 0 && CHECK26_ALLOW_RE.test(pmLines[i - 1]))) return
        violations.push(
          `${pmPath}:${n} assembles a state path outside the resolver section: ${line.trim()}`)
      }
    })
  }

  // (b) skills/: no file assembles a state path. Scope derived by walking the tree.
  const sources = [
    ...walkSkillFiles(['.md', '.py']).map((f) => ({ file: f, text: read(f) })),
    ...(opts.extraSources || []),
  ]
  for (const { file, text } of sources) {
    if (file === pmPath || file.endsWith('/scripts/pm-status.py')) continue
    scannedFiles.push(file)
    if (isStatusFilesContract(file)) continue
    if (isCategoricallyExempt(file)) continue
    const isPy = file.endsWith('.py')
    let inDocstring = false
    const lines = text.split('\n')
    lines.forEach((line, i) => {
      if (isPy) {
        // Track triple-quoted docstring boundaries (heuristic: odd count of triple-quotes
        // on the line toggles state). Skip lines that start inside or cross a boundary.
        const tripleCount = (line.match(/"""|'''/g) || []).length
        const wasInDocstring = inDocstring
        if (tripleCount % 2 === 1) inDocstring = !inDocstring
        if (wasInDocstring || tripleCount > 0) return
        if (line.trimStart().startsWith('#')) return  // python comment
      }
      if (STATE_PATH_RE.test(line) && STATE_CONTEXT_RE.test(line) && ACTIVE_VERB_RE.test(line)) {
        if (CHECK26_ALLOW_RE.test(line) || (i > 0 && CHECK26_ALLOW_RE.test(lines[i - 1]))) return
        violations.push(`${file}:${i + 1} assembles a state path: ${line.trim()}`)
      }
    })
  }

  return { violations, scannedFiles }
}

function checkResolverInvariant() {
  const { violations } = resolverInvariant()
  for (const v of violations) failures.push(`[check 26] ${v}`)
  if (verbose) console.log(`  resolver-invariant: ${violations.length} violation(s)`)
}

if (isMain) {
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
checkMarketplaceDependencies();
checkSharedPointerResolution();
checkDoctorModeKeywords();
checkResolverInvariant();

for (const note of notes) if (verbose) console.log(`  note: ${note}`);

if (failures.length > 0) {
  console.error(`\n${failures.length} documentation problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  console.error("These are facts the docs state about code that says otherwise. Fix the doc,");
  console.error("or if the code moved, fix both.");
  process.exit(1);
}

console.log("Documentation checks passed: skill names, gating tables, and section references all resolve.");
}
