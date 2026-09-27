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

const ROOT = path.resolve(import.meta.dirname, '..');
const PATTERN = 'skills/**/tests/test-*.py';

export function discover(root = ROOT) {
  return globSync(PATTERN, { cwd: root })
    .filter((p) => !p.includes('__pycache__'))
    .map((p) => p.split(path.sep).join('/'))
    .sort();
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  const suites = discover();
  if (process.argv.includes('--list')) {
    for (const s of suites) console.log(s);
    process.exit(0);
  }
  // The scope guard. An empty set is the one result that would make this runner report
  // success over nothing at all -- the exact shape of the failure it was written to stop.
  if (suites.length === 0) {
    console.error(`No Python suites matched ${PATTERN}. Refusing to report success over an ` +
                  `empty set -- either the pattern is wrong or the suites are gone.`);
    process.exit(2);
  }
  let failed = [];
  for (const s of suites) {
    process.stdout.write(`\n=== ${s}\n`);
    const r = spawnSync('uv', ['run', s], { cwd: ROOT, stdio: 'inherit' });
    if (r.status !== 0) failed.push(`${s} (exit ${r.status ?? 'signal ' + r.signal})`);
  }
  console.log(`\n${suites.length - failed.length}/${suites.length} Python suites passed.`);
  if (failed.length) {
    console.error(`\nFAILED:\n  ${failed.join('\n  ')}`);
    process.exit(1);
  }
}
