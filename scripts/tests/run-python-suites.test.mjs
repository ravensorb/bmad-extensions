import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { discover } from '../run-python-suites.mjs';

const ROOT = path.resolve(import.meta.dirname, '../..');
const RUNNER = path.join(ROOT, 'scripts/run-python-suites.mjs');

test('discovery finds every test-*.py on disk — the scope, not a list', () => {
  // The bug this guards: the CI workflow enumerated suites by hand and silently omitted
  // seven. Comparing discovery against an independent walk of the tree is the only check
  // that can notice an omission, because any list written here would share the mistake.
  const walk = (dir, out = []) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { if (e.name !== '__pycache__') walk(p, out); }
      else if (/^test-.*\.py$/.test(e.name) && path.basename(dir) === 'tests') {
        out.push(path.relative(ROOT, p).split(path.sep).join('/'));
      }
    }
    return out;
  };
  assert.deepEqual(discover(), walk(path.join(ROOT, 'skills')).sort());
});

test('discovery is non-empty and includes the suites CI used to name by hand', () => {
  const got = discover();
  assert.ok(got.length >= 17, `expected >=17 suites, got ${got.length}`);
  for (const s of ['skills/_shared/tests/test-pm-status.py',
                   'skills/_shared/tests/test-spec-align.py',
                   'skills/l3io-util-doctor/scripts/tests/test-engine.py',
                   'skills/l3io-util-doctor/scripts/tests/test-state-record.py']) {
    assert.ok(got.includes(s), `discovery lost ${s}`);
  }
});

test('__pycache__ copies are excluded', () => {
  assert.equal(discover().filter((p) => p.includes('__pycache__')).length, 0);
});

test('a newly added suite is picked up with no other edit', () => {
  // Attacks the scope, not the rule: the whole point is that adding a file is sufficient.
  const dir = path.join(ROOT, 'skills/_shared/tests');
  const f = path.join(dir, 'test-zz-scope-probe.py');
  fs.writeFileSync(f, '# probe\n');
  try {
    assert.ok(discover().includes('skills/_shared/tests/test-zz-scope-probe.py'));
  } finally { fs.unlinkSync(f); }
  assert.ok(!discover().includes('skills/_shared/tests/test-zz-scope-probe.py'));
});

test('an empty discovery refuses rather than reporting success over nothing', () => {
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), 'suites-'));
  fs.mkdirSync(path.join(empty, 'skills'));
  fs.copyFileSync(RUNNER, path.join(empty, 'runner.mjs'));
  // Runner resolves ROOT as its own parent dir, so a copy one level down sees empty/skills.
  fs.mkdirSync(path.join(empty, 'scripts'));
  fs.copyFileSync(RUNNER, path.join(empty, 'scripts/run-python-suites.mjs'));
  let code = 0, err = '';
  try {
    execFileSync(process.execPath, [path.join(empty, 'scripts/run-python-suites.mjs')],
                 { encoding: 'utf8', stdio: 'pipe' });
  } catch (e) { code = e.status; err = String(e.stderr); }
  assert.equal(code, 2, 'an empty set must exit 2, not 0');
  assert.match(err, /Refusing to report success over an empty set/);
  fs.rmSync(empty, { recursive: true, force: true });
});
