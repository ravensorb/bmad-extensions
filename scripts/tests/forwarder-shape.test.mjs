// scripts/forwarder-shape.mjs — the one definition of "this is a DEPRECATED forwarder".
//
// The bug this file guards: the signal lived in three places and all three disagreed. The
// loosest matched the word DEPRECATED anywhere in SKILL.md, so a skill merely DISCUSSING
// deprecation satisfied it. These tests pin each function to the question its caller asks, and
// pin the three questions as DIFFERENT on purpose — collapsing them would change behaviour.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  declaresForwarder, forwarderTarget, isBareForwarderShape, skillDescription, TARGET_RE,
} from "../forwarder-shape.mjs";

function skill(t, { name = "l3io-pm-plan", desc = null, body = "", files = ["customize.toml"],
                    sub = null, skillMd = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "fwd-shape-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const dir = path.join(root, name);
  fs.mkdirSync(dir, { recursive: true });
  if (skillMd) {
    const fm = desc === null ? "" : `---\nname: ${name}\ndescription: ${desc}\n---\n`;
    fs.writeFileSync(path.join(dir, "SKILL.md"), `${fm}\n${body}`);
  }
  for (const f of files) fs.writeFileSync(path.join(dir, f), "");
  if (sub) fs.mkdirSync(path.join(dir, sub), { recursive: true });
  return dir;
}

test("the description comes from parsed frontmatter, not a line match", (t) => {
  // A quoted, folded or block-scalar description must read the same as a plain one. The
  // line-matched reader the sync path used would have returned the quotes with it.
  assert.equal(skillDescription(skill(t, { desc: '"DEPRECATED forwarder for /l3io-plan."' })),
               "DEPRECATED forwarder for /l3io-plan.");
});

test("the word DEPRECATED in the BODY is not a declaration", (t) => {
  // This is the defect that prompted the file: the old view-checker rule read the whole file.
  const dir = skill(t, { desc: "A current skill.", body: "We discuss DEPRECATED things here.\n" });
  assert.equal(declaresForwarder(dir), false);
  assert.equal(forwarderTarget(dir), null);
});

test("the declaration must OPEN the description, not merely appear in it", (t) => {
  assert.equal(declaresForwarder(skill(t, { desc: "Plans things. DEPRECATED forwarder." })),
               false);
});

test("declaresForwarder is deliberately looser than forwarderTarget", (t) => {
  // The sync path accepts a bare declaration; the view checker needs a named target. Keeping
  // them separate is what stops a reworded sentence changing what ships.
  const dir = skill(t, { desc: "DEPRECATED forwarder. Use the new one." });
  assert.equal(declaresForwarder(dir), true);
  assert.equal(forwarderTarget(dir), null);
});

test("a forwarder naming itself is not a forwarder", (t) => {
  assert.equal(forwarderTarget(skill(t, { name: "l3io-pm-plan",
                                          desc: "DEPRECATED forwarder for /l3io-pm-plan." })),
               null);
});

test("a trailing sentence period is not part of the target", (t) => {
  // The downstream copy allows `.` in the captured name, so `/l3io-plan.` captures the period
  // and then matches no catalogued skill — silently failing the exemption it should grant.
  assert.equal(forwarderTarget(skill(t, { desc: "DEPRECATED forwarder for /l3io-plan." })),
               "l3io-plan");
  assert.equal(TARGET_RE.exec("DEPRECATED forwarder for /l3io-plan.")[1], "l3io-plan");
});

test("bare shape is SKILL.md + customize.toml and nothing else", (t) => {
  assert.equal(isBareForwarderShape(skill(t, {})), true);
  assert.equal(isBareForwarderShape(skill(t, { files: ["customize.toml", "payload-manifest.json"] })),
               false);
  // The case the old no-payload-manifest rule missed entirely: a directory can carry steps/ or
  // references/ and still have no manifest. That is a skill, not a forwarder.
  assert.equal(isBareForwarderShape(skill(t, { sub: "steps" })), false);
});

test("an unreadable or empty directory satisfies nothing", (t) => {
  // A directory that cannot be read is not evidence, so it must not satisfy a predicate
  // something else is about to trust.
  const gone = path.join(os.tmpdir(), "fwd-shape-does-not-exist-zz");
  assert.equal(declaresForwarder(gone), false);
  assert.equal(forwarderTarget(gone), null);
  assert.equal(isBareForwarderShape(gone), false);
  assert.equal(skillDescription(gone), null);
  const empty = skill(t, { files: [], skillMd: false });
  assert.equal(isBareForwarderShape(empty), false, "an empty directory is not a forwarder");
});

test("SKILL.md with no frontmatter, or unparseable frontmatter, yields nothing", (t) => {
  assert.equal(skillDescription(skill(t, { desc: null, body: "# plain\n" })), null);
  const bad = skill(t, {});
  fs.writeFileSync(path.join(bad, "SKILL.md"), "---\ndescription: [unclosed\n---\n# x\n");
  assert.equal(declaresForwarder(bad), false);
});

test("the repo's own four forwarders satisfy every clause", (t) => {
  // Derived, not listed: whatever skills/ actually holds. If a real forwarder stopped
  // satisfying these, the view checker would stop exempting it and smoke:install would fail.
  const skillsRoot = path.resolve(import.meta.dirname, "..", "..", "skills");
  const dirs = fs.readdirSync(skillsRoot, { withFileTypes: true })
    .filter((e) => e.isDirectory() && declaresForwarder(path.join(skillsRoot, e.name)))
    .map((e) => path.join(skillsRoot, e.name));
  assert.ok(dirs.length >= 4, `expected at least 4 forwarders, found ${dirs.length}`);
  for (const d of dirs) {
    assert.ok(isBareForwarderShape(d), `${path.basename(d)} is not a bare forwarder shape`);
    assert.ok(forwarderTarget(d), `${path.basename(d)} names no target`);
  }
});
