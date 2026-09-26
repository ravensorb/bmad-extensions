import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { scanners, skills, EXEMPTIONS, noBareBmadInCommands } from '../check-bmb.mjs';

const ROOT = path.resolve(import.meta.dirname, '../..');
const byId = (id) => {
  const e = EXEMPTIONS.find((x) => x.id === id);
  assert.ok(e, `exemption '${id}' is gone — if it was removed on purpose, remove its test too`);
  return e;
};
/** Is this finding swallowed by ANY exemption? That is what the gate actually asks. */
const exempt = (f, ctx = { skill: 'skills/l3io-util-doctor', tested: new Set() }) =>
  EXEMPTIONS.some((e) => e.match(f, ctx));

test('scope is derived: scanners come from the installed bmb package, skills from disk', () => {
  const s = scanners();
  assert.ok(s.length >= 2, `expected bmb scan-*.py, got ${JSON.stringify(s)}`);
  assert.ok(s.every((n) => /^scan-.*\.py$/.test(n)));
  assert.ok(skills().length >= 8, `expected the l3io skills, got ${skills().length}`);
  assert.ok(skills().every((p) => p.startsWith('skills/l3io-')));
});

test('every exemption carries an id and a stated reason', () => {
  for (const e of EXEMPTIONS) {
    assert.ok(e.id && e.why && typeof e.match === 'function', `incomplete exemption ${e.id}`);
    assert.ok(e.why.length > 40, `exemption ${e.id} needs a real reason, not a label`);
  }
});

test('relative-prefix is NOT exempt — it is the rule that caught the live defect', () => {
  // l3io-pm-setup shipped `uv run ./scripts/merge-config.py`, which only resolved when the
  // cwd happened to be the skill root. If any exemption ever swallows this category the
  // gate stops being able to catch it coming back.
  assert.equal(exempt({
    category: 'relative-prefix', severity: 'medium', file: 'SKILL.md', line: 1,
    detail: 'uv run ./scripts/merge-config.py',
  }), false);
});

test('the project-root exemption does not extend to other categories', () => {
  const e = byId('project-root-is-not-reserved-here');
  assert.equal(e.match({ category: 'project-root-not-bmad' }), true);
  for (const c of ['relative-prefix', 'absolute-path', 'bare-bmad', 'tests']) {
    assert.equal(e.match({ category: c }), false, `leaked into ${c}`);
  }
});

test('absolute-path is exempt only for the two documented runtime homes', () => {
  const f = (line) => ({ category: 'absolute-path', severity: 'high',
                         file: 'steps/execute/step-04-arch-gate.md', line });
  const ctx = { skill: 'skills/l3io-pm-execute', tested: new Set() };
  // Line 34 really does contain ~/.claude/... — the scanner's own `detail` truncates
  // before it, which is why the predicate reads the file instead.
  assert.equal(byId('user-level-runtime-homes').match(f(34), ctx), true);
  // A hard-coded machine path on a line with no ~/.claude or ~/.codex must still fail.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'bmb-'));
  fs.mkdirSync(path.join(tmp, 'skills/fake'), { recursive: true });
  fs.writeFileSync(path.join(tmp, 'skills/fake/SKILL.md'), 'run /usr/local/bin/thing\n');
  assert.equal(exempt({ category: 'absolute-path', severity: 'high', file: 'SKILL.md', line: 1 },
                      { skill: 'skills/fake', tested: new Set() }), false);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('the PEP 723 exemption turns off for a script that declares no inline deps', () => {
  const e = byId('pep723-declared');
  const dep = { category: 'dependencies', severity: 'high' };
  assert.equal(e.match({ ...dep, file: 'scripts/pm-status.py' },
                       { skill: 'skills/l3io-util-doctor' }), true);
  // A .md has no PEP 723 header, so the same category over it is reported.
  assert.equal(e.match({ ...dep, file: 'SKILL.md' }, { skill: 'skills/l3io-util-doctor' }), false);
});

test('the tests exemption is keyed on suites that exist, and reports a script with none', () => {
  const e = byId('tested-elsewhere');
  const t = (file, tested) => e.match({ category: 'tests', file }, { tested: new Set(tested) });
  // Named after the module it drives, not after the script: this is the pair that made a
  // filename-based derivation report migrate-engine.py as untested when it is not.
  assert.equal(t('scripts/migrate-engine.py', ['migrate-engine.py']), true);
  assert.equal(t('scripts/migrate-engine.py', []), false);
  assert.equal(t('scripts/brand-new.py', ['migrate-engine.py']), false);
});

test('advisory-style never swallows a high or critical finding', () => {
  const e = byId('advisory-style');
  assert.equal(e.match({ category: 'agentic-design', severity: 'low' }), true);
  assert.equal(e.match({ category: 'agentic-design', severity: 'high' }), false);
  assert.equal(e.match({ category: 'agentic-design', severity: 'critical' }), false);
});

test('a bare _bmad/ in a shell fence is caught; in prose or an output block it is not', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'bmb-'));
  const sk = path.join(tmp, 'skills/l3io-probe');
  fs.mkdirSync(sk, { recursive: true });
  fs.writeFileSync(path.join(sk, 'ok.md'),
    'Prose may name _bmad/config.toml freely.\n\n```\n⚠️  legacy layout = _bmad/state/\n```\n');
  assert.deepEqual(noBareBmadInCommands(tmp), [],
    'prose and untagged output blocks are not commands');
  fs.writeFileSync(path.join(sk, 'bad.md'), '```bash\ncat _bmad/config.toml\n```\n');
  const hits = noBareBmadInCommands(tmp);
  assert.equal(hits.length, 1, JSON.stringify(hits));
  assert.match(hits[0], /bad\.md:2/);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('the real tree has no bare _bmad/ inside a shell fence', () => {
  assert.deepEqual(noBareBmadInCommands(), []);
});
