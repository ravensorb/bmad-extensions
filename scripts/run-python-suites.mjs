#!/usr/bin/env node
/**
 * Run every Python unit-test suite in the repo, discovered from disk.
 *
 * WHY THIS EXISTS, rather than a list of steps in checks.yml. The workflow named each
 * suite by hand, and the list drifted: seven suites -- test-engine.py and the five
 * reader suites it depends on, plus test-state-record.py -- were written during the
 * l3io-doctor redesign and never added to it. They sat on disk passing locally and
 * unprotected in CI for as long as they existed, including the suite for the migration
 * engine that deletes a project's source layout after its gated write. Nothing reported
 * this, because a hand-kept list cannot notice what is missing from it (CLAUDE.md §4:
 * derive the scope from the source of truth, never enumerate it by hand).
 *
 * So: the set of suites IS the set of files on disk. Adding a suite runs it; there is no
 * second place to remember.
 *
 * This is a runner, not a test harness (CLAUDE.md §1). It discovers files and shells out
 * to `uv run`, which reads each suite's own PEP-723 header for its dependencies. It
 * contains no assertions, no fixtures and no reporting of its own -- unittest does all of
 * that inside each suite.
 */
import { globSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { writeAllSync } from './write-all-sync.mjs';

const ROOT = path.resolve(import.meta.dirname, '..');
// Test suites live under two roots:
//   - skills/_shared/tests/*.py — shared suites (test-pm-status.py etc.) that CI runs
//     against source, never shipped to consumers because _shared/ is not a marketplace
//     plugin skill.
//   - tests/{skill-name}/*.py — per-skill suites moved out of skills/{skill-name}/scripts/tests/
//     so they don't ship as payload when BMad's --custom-source install copies the skill
//     directory. Each test targets its script via skills/{skill-name}/scripts/{script}.py.
const PATTERNS = ['skills/_shared/tests/test-*.py', 'tests/**/test-*.py'];

export function discover(root = ROOT) {
  const seen = new Set();
  for (const pattern of PATTERNS) {
    for (const p of globSync(pattern, { cwd: root })) {
      if (p.includes('__pycache__')) continue;
      seen.add(p.split(path.sep).join('/'));
    }
  }
  return [...seen].sort();
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  const suites = discover();
  if (process.argv.includes('--list')) {
    writeAllSync(1, suites.join('\n') + '\n');
    process.exit(0);
  }
  // The scope guard. An empty set is the one result that would make this runner report
  // success over nothing at all -- the exact shape of the failure it was written to stop.
  if (suites.length === 0) {
    writeAllSync(2, `No Python suites matched ${PATTERNS.join(' or ')}. Refusing to report success over an ` +
                    `empty set -- either the pattern is wrong or the suites are gone.\n`);
    process.exit(2);
  }
  let failed = [];
  for (const s of suites) {
    // writeAllSync, not process.stdout.write, for a second reason on top of the exit race:
    // the child below inherits this fd and writes to it directly, so an asynchronous parent
    // write can land AFTER the output of the suite it is supposed to be labelling.
    writeAllSync(1, `\n=== ${s}\n`);
    const r = spawnSync('uv', ['run', s], { cwd: ROOT, stdio: 'inherit' });
    if (r.status !== 0) failed.push(`${s} (exit ${r.status ?? 'signal ' + r.signal})`);
  }
  writeAllSync(1, `\n${suites.length - failed.length}/${suites.length} Python suites passed.\n`);
  if (failed.length) {
    writeAllSync(2, `\nFAILED:\n  ${failed.join('\n  ')}\n`);
    process.exit(1);
  }
}
