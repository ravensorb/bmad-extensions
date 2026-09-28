#!/usr/bin/env node
/**
 * Gate: BMad Builder's deterministic skill scanners, run over this package's skills.
 *
 * bmb (the `bmad-builder` npm package, a devDependency per ADR-0007) ships the scanners
 * its bmad-workflow-builder skill uses. They found three real defects here that nothing
 * else did, including `uv run ./scripts/merge-config.py` in l3io-setup, which only
 * worked when the working directory happened to be the skill root. Nothing stopped that
 * coming back, so this runs them on every push.
 *
 * SCOPE IS DERIVED, NOT LISTED (CLAUDE.md §4), in both directions:
 *   - the scanners are every `scan-*.py` bmb ships, found by globbing its package, so a
 *     scanner bmb adds starts running here without an edit;
 *   - the skills are every l3io skill directory under skills/ on disk.
 * Neither is a hand-kept list that could quietly stop covering something.
 *
 * EXEMPTIONS. Some scanner rules encode BMad-core conventions this package deliberately
 * does not follow. Each exemption below is as narrow as the reason justifies -- a
 * predicate over the specific finding, never a whole category waved away -- and each has
 * a test in scripts/tests/check-bmb.test.mjs that plants a violation the exemption must
 * NOT swallow. `relative-prefix` is deliberately absent: that is the rule that caught the
 * live defect, and it stays armed.
 */
import { globSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const BMB = 'node_modules/bmad-builder/src/skills/bmad-workflow-builder/scripts';

export function scanners(root = ROOT) {
  return globSync('scan-*.py', { cwd: path.join(root, BMB) }).sort();
}
export function skills(root = ROOT) {
  return globSync('skills/l3io-*/', { cwd: root })
    .map((p) => p.replace(/\/$/, '').split(path.sep).join('/')).sort();
}

/**
 * Scripts that have a unit test anywhere in the repo.
 *
 * Derived from what each suite CONTAINS, not from its filename. Deriving from the name
 * was wrong twice over: test-engine.py drives migrate-engine.py and
 * test-merge-config-wrapper.py drives merge-config.py, so a name match reported both as
 * untested -- which is exactly the false finding that sent me looking for a defect that
 * was not there.
 */
function testedScripts(root = ROOT) {
  const tested = new Set();
  // Two roots after the tests-out-of-payload move: shared suites still live at
  // skills/_shared/tests/ (never shipped since _shared/ is not a marketplace plugin skill);
  // per-skill suites live at tests/{skill-name}/ (top-level, outside any shipped skill dir).
  for (const pattern of ['skills/_shared/tests/test-*.py', 'tests/**/test-*.py']) {
    for (const suite of globSync(pattern, { cwd: root })) {
      if (suite.includes('__pycache__')) continue;
      const body = fs.readFileSync(path.join(root, suite), 'utf8');
      for (const m of body.matchAll(/([a-z0-9][a-z0-9_-]*\.py)/g)) tested.add(m[1]);
    }
  }
  return tested;
}

/** True when `script` declares PEP 723 inline dependencies. */
function hasPep723(root, skillDir, file) {
  try {
    return fs.readFileSync(path.join(root, skillDir, file), 'utf8')
             .slice(0, 400).includes('# /// script');
  } catch { return false; }
}

export const EXEMPTIONS = [
  {
    id: 'project-root-is-not-reserved-here',
    why: 'BMad core reserves {project-root} for _bmad paths. This package does not, and the ' +
         'uses are load-bearing: {project-root}/docs/adr is ADR-0005; ' +
         '{project-root}/.claude/skills/<n>/SKILL.md is the probe path check 29 REQUIRES, so ' +
         '"fixing" it would fail our own gate; and update-ai-rules writes {project-root}/CLAUDE.md, ' +
         '{project-root}/AGENTS.md and the other agent rule files, which live at the project root ' +
         'by definition. Exempted as a category because the rule is a convention we reject, not a ' +
         'defect we tolerate -- narrowing it to a path list would just be that list again.',
    match: (f) => f.category === 'project-root-not-bmad',
  },
  {
    id: 'user-level-runtime-homes',
    why: '~/.claude/ is the user-level half of the same probe pair; ~/.codex/sessions is where ' +
         'the metrics contract reads Codex token usage from. Both are real absolute paths on ' +
         'purpose -- they name another tool\'s home, not ours.',
    match: (f, ctx) => f.category === 'absolute-path' &&
                       /~\/(\.claude|\.codex)\//.test(sourceLine(ROOT, ctx.skill, f.file, f.line)),
  },
  {
    id: 'bmad-config-named-in-prose',
    why: 'Docs name BMad config files (_bmad/config.toml, _bmad/_config/manifest.yaml) as ' +
         'subjects of a sentence, not as path arguments. The command case is not exempt: ' +
         'noBareBmadInCommands() below fails on a bare _bmad/ inside a shell block.',
    match: (f) => f.category === 'bare-bmad',
  },
  {
    id: 'pep723-declared',
    why: 'The scanner greps for "pip install" anywhere in the file. pm-status.py matches on an ' +
         'error message telling a user how to recover; its PEP 723 header is lines 2-4.',
    match: (f, ctx) => f.category === 'dependencies' && hasPep723(ROOT, ctx.skill, f.file),
  },
  {
    id: 'tested-elsewhere',
    why: 'The scanner looks for scripts/tests/test-<script>.py beside the script. This package ' +
         'keeps shared suites in skills/_shared/tests/ and per-skill suites in tests/{skill-name}/ ' +
         '(moved out of skills/{skill}/scripts/tests/ so they no longer ship as payload). Some ' +
         'suites are named after the module they drive (test-engine.py covers migrate-engine.py). ' +
         'Derived from the suites on disk under both roots, so a script with no suite anywhere ' +
         'is still reported.',
    match: (f, ctx) => f.category === 'tests' &&
                       (ctx.tested.has(path.basename(f.file || '')) || (f.file || '').endsWith('/')),
  },
  {
    id: 'advisory-style',
    why: 'agentic-design is advice about argparse/JSON/exit-code style on scripts that already ' +
         'work. Opinion, not a defect; low and medium only.',
    match: (f) => f.category === 'agentic-design' && f.severity !== 'high' &&
                  f.severity !== 'critical',
  },
  {
    id: 'scanner-informational',
    why: 'info-severity notes such as "No scripts/ directory found" describe the scan, not a defect.',
    match: (f) => f.severity === 'info',
  },
];

/** The source line a finding points at, for predicates that need more than truncated `detail`. */
function sourceLine(root, skillDir, file, line) {
  try {
    return fs.readFileSync(path.join(root, skillDir, file), 'utf8').split('\n')[(line || 1) - 1] || '';
  } catch { return ''; }
}

/** Our own stricter replacement for the exempted bare-bmad category: a bare `_bmad/`
 *  inside a SHELL-TAGGED fence is a real cwd dependency. Untagged fences hold display
 *  output (halt banners naming the legacy layout), which is prose in a box, not a command. */
export function noBareBmadInCommands(root = ROOT) {
  const bad = [];
  for (const sk of skills(root)) {
    for (const rel of globSync('**/*.md', { cwd: path.join(root, sk) })) {
      const lines = fs.readFileSync(path.join(root, sk, rel), 'utf8').split('\n');
      let inFence = false;
      lines.forEach((line, i) => {
        const m = /^\s*```(\w*)/.exec(line);
        if (m) { inFence = inFence ? false : /^(bash|sh|shell|console)$/.test(m[1]); return; }
        if (!inFence) return;
        if (/(^|[\s"'`(=])_bmad\//.test(line)) bad.push(`${sk}/${rel}:${i + 1}: ${line.trim()}`);
      });
    }
  }
  return bad;
}

export function run(root = ROOT) {
  const tested = testedScripts(root);
  const scannerList = scanners(root);
  if (scannerList.length === 0) {
    return { fatal: `No scan-*.py found under ${BMB}. Is bmad-builder installed?`, unexempt: [] };
  }
  const unexempt = [];
  let total = 0;
  for (const skill of skills(root)) {
    for (const s of scannerList) {
      const r = spawnSync('uv', ['run', path.join(root, BMB, s), skill], { cwd: root, encoding: 'utf8' });
      let doc;
      try { doc = JSON.parse(r.stdout); } catch { continue; }
      for (const f of doc.findings || []) {
        total++;
        const ctx = { skill, tested };
        if (!EXEMPTIONS.some((e) => e.match(f, ctx))) {
          unexempt.push({ skill, scanner: s, ...f });
        }
      }
    }
  }
  return { total, unexempt, scanners: scannerList.length, skills: skills(root).length };
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  const res = run();
  if (res.fatal) { console.error(res.fatal); process.exit(2); }
  const bare = noBareBmadInCommands();
  for (const b of bare) console.error(`bare _bmad/ inside a shell block: ${b}`);
  for (const f of res.unexempt) {
    console.error(`[${f.severity}] ${f.skill}/${f.file}:${f.line} (${f.category}) ${f.title}`);
  }
  if (res.unexempt.length || bare.length) {
    console.error(`\nbmb scan: ${res.unexempt.length} unexempted finding(s), ${bare.length} bare _bmad in commands.`);
    process.exit(1);
  }
  console.log(`bmb scan passed: ${res.scanners} scanner(s) over ${res.skills} skills, ` +
              `${res.total} finding(s), all matched by a documented exemption.`);
}
