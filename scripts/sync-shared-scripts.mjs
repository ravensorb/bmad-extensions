#!/usr/bin/env node
// Sync canonical shared files from skills/_shared/ into each PM skill's directory.
//
// Why: BMad installs skills independently, so each skill must ship its own copy of any
// shared file. The authored source of truth is skills/_shared/; the per-skill copies are
// GENERATED — never hand-edit them.
//
// Shared files:
//   pm-status.py → scripts/ in exactly ONE skill per module that self-installs it to
//   {project-root}/_bmad/scripts/pm-status.py: `l3io-setup` for the l3io-pm module, and
//   `l3io-doctor` for the (standalone) l3io-util module. Task 11A cut this from four
//   payload copies to two — pm-execute, pm-plan, and pm-sync used to each carry their own
//   copy and self-install identical bytes to the identical destination; now they read
//   `{skill-root}/../l3io-setup/scripts/pm-status.py` at activation
//   (`steps/shared/step-00-activate.md` §2) instead, because `.claude-plugin/marketplace.json`
//   installs the whole `l3io-pm` plugin — all five of its skills — as one unit, so
//   `l3io-setup` is guaranteed to land beside them. `/l3io-setup` itself stays optional:
//   nothing about that read requires the setup skill to ever have been *run*, only installed.
//   check:module (`checkPmStatusSingleton`) guards against a second copy reappearing inside
//   one module.
//   spec-align.py → scripts/ in l3io-execute (arch gate, story prep, closures) and
//   l3io-doctor (health Checks 15-19, triage's spec pass, migrate-adrs); shared because
//   it has two consumers (ADR-0001), run from each skill's own copy, never self-installed
//   status-files.md / metrics-contract.md → references/ in PM skills
//   config-resolution.md → references/ in EVERY l3io skill -- every skill resolves config
//   merge-config.py / merge-help-csv.py / write-module-config.py / module-setup.md →
//   scripts/ and assets/ in each module's HOME only (the *-setup skill for a multi-skill
//   module, the skill itself for a standalone one) -- only the module home performs setup.
//   merge-config.py / merge-help-csv.py are the two scripts BMad's module validator
//   requires by name; see their own docstrings for why they are not the scaffolder's
//   versions.
//
// Not shared, deliberately: resolve_config.py, resolve_customization.py and memlog.py are
// installed by BMad core at {project-root}/_bmad/scripts/ and are never bundled by a skill.
// Vendoring them shipped a stale duplicate of a core script that nothing invoked.
//
// Also not shared, deliberately: test-pm-status.py, test-write-module-config.py,
// test-merge-help-csv.py and test-merge-config-wrapper.py. A consumer never runs a skill's
// shipped tests, CI runs every suite straight from skills/_shared/tests/
// (.github/workflows/checks.yml), and shipping them into every consumer's install was
// ~842 KB of dead payload — the same category this package removed when it stopped
// vendoring BMad core scripts. Do not add a test file back to any of the manifests below;
// if a script gets a test, the test's only home is skills/_shared/tests/.
//
// Usage:
//   node scripts/sync-shared-scripts.mjs           # write the per-skill payload copies
//   node scripts/sync-shared-scripts.mjs --check    # verify copies match source; nonzero exit on drift (CI)
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { writeAllSync } from "./write-all-sync.mjs";

const repoRoot = process.cwd();
const check = process.argv.includes("--check");
const sharedDir = path.join(repoRoot, "skills", "_shared");

// source -> relative destination under each skill dir (pmScriptDirs) or all PM skill dirs (allPmDirs)
const pmScriptFiles = [
  { src: path.join(sharedDir, "pm-status.py"), rel: path.join("scripts", "pm-status.py") },
];

// pm-status.py only (no test suite) for a skill that invokes {pm_status} and self-installs it
// but is not one of the PM execution skills above. A test suite in a consumer skill's payload
// is dead weight — the same kind this package removed when it stopped vendoring BMad core
// scripts — so this group deliberately carries only the runtime script.
const pmStatusOnlyFiles = [
  { src: path.join(sharedDir, "pm-status.py"), rel: path.join("scripts", "pm-status.py") },
];

// spec-align.py: two consumers (pm-execute, util-doctor), so shared per ADR-0001. Each runs
// its own copy via `uv run {skill-root}/scripts/spec-align.py`; its test suite stays in
// skills/_shared/tests/ like every other suite.
const specAlignFiles = [
  { src: path.join(sharedDir, "spec-align.py"), rel: path.join("scripts", "spec-align.py") },
];

// The canonical story AC dimension reference, shipped to the two skills that enrich stories.
const acDimensionFiles = [{ src: path.join(sharedDir, "ac-dimensions.md"), rel: "references/ac-dimensions.md" }];

// Files every l3io skill ships, regardless of module: the config contract every skill
// resolves. Setup itself -- module-setup.md and the script that writes its config -- is a
// module-home concern; see moduleHomeFiles below.
const allSkillFiles = [
  { src: path.join(sharedDir, "config-resolution.md"), rel: path.join("references", "config-resolution.md") },
];

// The two merge scripts BMad's validator requires, module-setup.md, and the config writer
// setup runs, belong in each module's HOME -- the setup skill for multi-skill modules, the
// skill itself for standalone ones. Syncing them into every operational skill would ship
// four copies of a procedure only one of them runs.
const moduleHomeDirs = [
  "l3io-setup", "l3io-doctor", "l3io-sec-redteam", "l3io-arch-review",
].map((name) => path.join(repoRoot, "skills", name));

const moduleHomeFiles = [
  { src: path.join(sharedDir, "merge-config.py"), rel: path.join("scripts", "merge-config.py") },
  { src: path.join(sharedDir, "merge-help-csv.py"), rel: path.join("scripts", "merge-help-csv.py") },
  { src: path.join(sharedDir, "write-module-config.py"), rel: path.join("scripts", "write-module-config.py") },
  { src: path.join(sharedDir, "module-setup.md"), rel: path.join("assets", "module-setup.md") },
];

// status-files.md ALONE, for a skill that needs the state-layout contract but not the metrics
// or calibration ones. l3io-doctor is that skill: migrate-state, split-status,
// clean-layout, health-check and stats all decide what a correct state tree looks like, and
// six of its runtime directives -- SKILL.md:186 among them, calling it "the canonical
// contract" -- told the reader to open `references/status-files.md` in a skill that did not
// ship it. Shipping it is the fix rather than repointing, because a doctor install does not
// imply a PM install: l3io-util is its own module, and a pointer at another module's file is
// a pointer at nothing for anyone who installed only this one. Making it a sync target is
// also what makes the fix stick -- `check:scripts` now fails if the copy goes missing or
// stale, which no amount of prose would have done (repo CLAUDE.md §3).
const stateContractOnly = [
  { src: path.join(sharedDir, "status-files.md"), rel: path.join("references", "status-files.md") },
];

const pmRefFiles = [
  { src: path.join(sharedDir, "status-files.md"), rel: path.join("references", "status-files.md") },
  { src: path.join(sharedDir, "metrics-contract.md"), rel: path.join("references", "metrics-contract.md") },
  // The calibration model, split out of metrics-contract.md: pm-status.py performs all of it
  // and a normal run never reads it, so it must not sit in the contract a capture agent loads.
  { src: path.join(sharedDir, "calibration-model.md"), rel: path.join("references", "calibration-model.md") },
];

// The rule for who SHIPS a pm-status.py payload copy (Task 11A, superseding the note this
// replaced): exactly one skill per module -- the module's home, since a home is guaranteed to
// be co-installed with every operational skill in that module. A skill that merely INVOKES
// {pm_status} does not need its own copy; it can read a sibling module-home's copy instead
// (pm-execute/pm-plan/pm-sync do, from l3io-setup). l3io-doctor is its own,
// standalone module with no sibling *-setup to read from, so it remains a shipper too --
// see newUtilDoctorDirs below.
// Legacy slots kept for backward compat shape; new skills use newPmPlanDirs / newPmExecuteDirs groups below.
const pmScriptDirs = [];

// All PM skills that reference status-files.md
// Legacy slots kept for backward compat shape; new skills use newPmPlanDirs / newPmExecuteDirs / newPmSyncDirs groups below.
const allPmDirs = [];

// New skill directories (created in Tasks 5-9)
const newPmPlanDirs = [
  path.join(repoRoot, "skills", "l3io-plan"),
];
const newPmExecuteDirs = [
  path.join(repoRoot, "skills", "l3io-execute"),
];
const newPmSyncDirs = [
  path.join(repoRoot, "skills", "l3io-sync"),
];

// l3io-pm's module home: the ONE l3io-pm skill that carries pm-status.py (Task 11A). Guaranteed
// to be installed alongside pm-execute/pm-plan/pm-sync because the marketplace manifest
// installs the whole l3io-pm plugin as one unit — see the sync-groups comment above.
const newPmSetupDirs = [
  path.join(repoRoot, "skills", "l3io-setup"),
];

// Skills that invoke {pm_status} but are not part of the l3io-pm module: they need
// pm-status.py to self-install/heal from, but not its test suite. Currently: l3io-doctor,
// the documented post-upgrade entry point (see docs/upgrading.md), a different, standalone
// module with no sibling *-setup skill to read from.
const newUtilDoctorDirs = [
  path.join(repoRoot, "skills", "l3io-doctor"),
];

// Every skill in the package — the four l3io modules' skills all resolve config, so all of
// them carry config-resolution.md (allSkillFiles above); the setup procedure itself is a
// module-home concern (moduleHomeFiles). Derived from skills/ itself, never hand-enumerated:
// a hand-kept list here drifted silently once already (l3io-setup was absent from it and
// so absent from the check:scripts comparison too, even though it needed the same config
// contract as every other skill). Same derivation scripts/check-docs.mjs's derivedCounts()
// uses (withFileTypes + isDirectory()) — a skill directory is a *directory* under skills/
// whose name starts with "l3io-" (_shared is excluded by the prefix). Fix round 1, F-8: an
// earlier version used checkSkillNames()'s derivation instead, which reads plain
// fs.readdirSync() with no isDirectory() filter — harmless while every "l3io-*" entry under
// skills/ happens to be a directory, but a stray file (e.g. a dropped "l3io-notes.md") would
// have been treated as a skill directory and handed to fs.mkdirSync/fs.copyFileSync below.
// A forwarder skill is a minimal dispatcher that carries only SKILL.md + customize.toml and
// exists to keep an old skill name working through a rename cycle. Its SKILL.md frontmatter
// description starts with "DEPRECATED forwarder" — that is the derived signal, so a forwarder
// added later (or removed at 4.0.0) is picked up without a hand-kept list. Excluding
// forwarders from allSkillDirs keeps config-resolution.md and other "every skill" payloads out
// of them; a forwarder does not resolve config, it just dispatches.
function isForwarderSkill(skillDir) {
  const rel = path.join(repoRoot, "skills", skillDir, "SKILL.md");
  if (!fs.existsSync(rel)) return false;
  const body = fs.readFileSync(rel, "utf8");
  const m = body.match(/^description:\s*(.+)$/m);
  return Boolean(m && /^DEPRECATED forwarder/i.test(m[1].trim()));
}

const allSkillDirs = fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
  .filter((e) => e.isDirectory() && e.name.startsWith("l3io-"))
  .map((e) => e.name)
  .filter((name) => !isForwarderSkill(name))
  .sort()
  .map((name) => path.join(repoRoot, "skills", name));

// Shared step files: source path → relative dest path within each skill's steps/ dir
const sharedStepFiles = [
  {
    src: path.join(sharedDir, "steps", "shared", "step-00-activate.md"),
    rel: path.join("steps", "shared", "step-00-activate.md"),
  },
  {
    // The digest, split out of step-00-activate.md §8: dispatched subagents load it alone,
    // inheriting the bootstrap in sections 1-7 rather than re-running it per dispatch.
    src: path.join(sharedDir, "steps", "shared", "step-00-digest.md"),
    rel: path.join("steps", "shared", "step-00-digest.md"),
  },
  {
    src: path.join(sharedDir, "steps", "shared", "step-01-classify-work.md"),
    rel: path.join("steps", "shared", "step-01-classify-work.md"),
  },
  {
    src: path.join(sharedDir, "steps", "shared", "step-estimate.md"),
    rel: path.join("steps", "shared", "step-estimate.md"),
  },
];

const planStepFiles = [
  { src: path.join(sharedDir, "steps", "plan", "step-backlog-intake.md"), rel: path.join("steps", "plan", "step-backlog-intake.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-02-readiness-check.md"), rel: path.join("steps", "plan", "step-02-readiness-check.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-03-story-elaboration.md"), rel: path.join("steps", "plan", "step-03-story-elaboration.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-04-load-state.md"), rel: path.join("steps", "plan", "step-04-load-state.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-05-dependency-graph.md"), rel: path.join("steps", "plan", "step-05-dependency-graph.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-06-plan-output.md"), rel: path.join("steps", "plan", "step-06-plan-output.md") },
];

const executeStepFiles = [
  { src: path.join(sharedDir, "steps", "execute", "step-02-scope-resolve.md"), rel: path.join("steps", "execute", "step-02-scope-resolve.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-03-load-plan.md"), rel: path.join("steps", "execute", "step-03-load-plan.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-04-arch-gate.md"), rel: path.join("steps", "execute", "step-04-arch-gate.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-05-epic-loop.md"), rel: path.join("steps", "execute", "step-05-epic-loop.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-06-epic-closure.md"), rel: path.join("steps", "execute", "step-06-epic-closure.md") },
  { src: path.join(sharedDir, "steps", "sprint", "step-02-story-prep.md"), rel: path.join("steps", "sprint", "step-02-story-prep.md") },
  { src: path.join(sharedDir, "steps", "sprint", "step-03-dev-loop.md"), rel: path.join("steps", "sprint", "step-03-dev-loop.md") },
  { src: path.join(sharedDir, "steps", "sprint", "step-04-sprint-closure.md"), rel: path.join("steps", "sprint", "step-04-sprint-closure.md") },
  { src: path.join(sharedDir, "steps", "closure", "sprint-closure.md"), rel: path.join("steps", "closure", "sprint-closure.md") },
  { src: path.join(sharedDir, "steps", "closure", "epic-closure.md"), rel: path.join("steps", "closure", "epic-closure.md") },
];

const syncStepFiles = [
  { src: path.join(sharedDir, "steps", "sync", "step-02-detect-platform.md"), rel: path.join("steps", "sync", "step-02-detect-platform.md") },
  { src: path.join(sharedDir, "steps", "sync", "step-03-operations.md"),       rel: path.join("steps", "sync", "step-03-operations.md") },
  { src: path.join(sharedDir, "steps", "sync", "step-04-resolve.md"),           rel: path.join("steps", "sync", "step-04-resolve.md") },
];

// Combined sync manifest: [{files, dirs, skipMissing}]
const syncGroups = [
  // Config contract + setup procedure + its writer script into every skill
  { files: allSkillFiles, dirs: allSkillDirs },
  // Legacy: pm-status.py into old execution skills (kept for backward compat shape; skill dirs created in Tasks 5-9)
  { files: pmScriptFiles, dirs: pmScriptDirs },
  { files: pmRefFiles, dirs: allPmDirs },
  // New: shared steps into new skills (dirs only created in Tasks 5-9; skip missing dirs)
  { files: sharedStepFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs, ...newPmSyncDirs], skipMissing: true },
  { files: planStepFiles, dirs: newPmPlanDirs, skipMissing: true },
  { files: executeStepFiles, dirs: newPmExecuteDirs, skipMissing: true },
  { files: syncStepFiles, dirs: newPmSyncDirs, skipMissing: true },
  // pm-status.py into l3io-pm's module home ONLY (Task 11A) -- pm-execute/pm-plan/pm-sync
  // read it from there at activation (`{skill-root}/../l3io-setup/scripts/pm-status.py`,
  // step-00-activate.md §2) instead of each carrying its own copy.
  { files: pmScriptFiles, dirs: newPmSetupDirs, skipMissing: true },
  // status-files.md into new PM skills (plan + execute)
  { files: pmRefFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs], skipMissing: true },
  { files: pmRefFiles, dirs: newPmSyncDirs, skipMissing: true },
  // pm-status.py (no tests) into l3io-doctor — it invokes {pm_status} and self-installs
  // it at activation but is not a PM execution skill; see pmStatusOnlyFiles above.
  { files: pmStatusOnlyFiles, dirs: newUtilDoctorDirs },
  // status-files.md (state layout only, no metrics/calibration) into l3io-doctor --
  // see stateContractOnly above for why it ships rather than being repointed.
  { files: stateContractOnly, dirs: newUtilDoctorDirs },
  // spec-align.py into its two consumers
  { files: specAlignFiles, dirs: [...newPmExecuteDirs, ...newUtilDoctorDirs] },
  // the canonical AC dimension reference into the two skills that enrich stories
  { files: acDimensionFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs], skipMissing: true },
  // The two BMad-validator-required merge scripts, into each module's home only.
  { files: moduleHomeFiles, dirs: moduleHomeDirs },
];

// Every repo-relative path this script writes, derived from syncGroups itself so
// it cannot disagree with what the loop below actually does. scripts/write-payload-
// manifest.mjs imports this: a second hand-kept list would drift from the first,
// and this file's whole purpose is detecting drift.
export const PAYLOAD_TARGETS = syncGroups.flatMap(({ files, dirs, skipMissing }) =>
  files.flatMap(({ src, rel }) =>
    !fs.existsSync(src) && skipMissing
      ? []
      : dirs.flatMap((skillDir) =>
          skipMissing && !fs.existsSync(skillDir)
            ? []
            : [path.relative(repoRoot, path.join(skillDir, rel))],
        ),
  ),
);

// Orphan detection: the drift check above compares synced copies against their sources, but
// it walks syncGroups' own dirs -- it can never notice a copy sitting in a skill NO group
// targets for that rel path. That is exactly the shape Task 11 exposed: narrowing
// moduleHomeFiles to four module homes left module-setup.md and write-module-config.py
// physically present in four other skills until something ran `git rm` on them by hand --
// skip that step and every one of check:scripts/check:docs/check:manifest/check:version/
// check:module stays green while eight dead files still ship.
//
// For every rel path any group delivers, the allowed set is the UNION of that group's `dirs`
// across every group naming the same rel -- never a hand-kept list, so a group that legitimately
// widens or narrows its own targets is picked up automatically. Any other real skill directory
// under skills/ that happens to contain a file at that rel path is an orphan: bytes this script
// does not own, but that still ship.
function findOrphans() {
  const allowedByRel = new Map(); // rel -> Set<absolute skill dir>
  for (const { files, dirs } of syncGroups) {
    for (const { rel } of files) {
      if (!allowedByRel.has(rel)) allowedByRel.set(rel, new Set());
      for (const dir of dirs) allowedByRel.get(rel).add(dir);
    }
  }

  // Every real skill directory -- not just the ones a group already names, since an orphan
  // is by definition a directory no group named for that rel path. Same derivation as
  // allSkillDirs above (readdirSync + isDirectory + "l3io-" prefix; _shared is excluded by
  // the prefix, matching every other scope-derivation in this file).
  const everySkillDir = fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name.startsWith("l3io-"))
    .map((e) => path.join(repoRoot, "skills", e.name));

  const orphans = [];
  for (const [rel, allowedDirs] of allowedByRel) {
    for (const skillDir of everySkillDir) {
      if (allowedDirs.has(skillDir)) continue;
      const candidate = path.join(skillDir, rel);
      if (fs.existsSync(candidate)) orphans.push(path.relative(repoRoot, candidate));
    }
  }
  return orphans.sort();
}

// Guard: importing this module (e.g. from write-payload-manifest.mjs) must not perform a
// sync. The body below only runs when this file is executed directly as the entry point.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  // `--dump-deliveries`: print who ships what, as JSON, and exit without writing anything.
  //
  // scripts/check-docs.mjs's check 24 needs the source -> (destination path, destination
  // skills) mapping, and must get it for the tree IT is checking -- which, under
  // CHECK_DOCS_ROOT, is a temp copy of the repo and not this process's cwd. Importing this
  // module would derive the mapping from the REAL repo (repoRoot is process.cwd()), and
  // re-parsing syncGroups out of this file's text would be a second, hand-written derivation
  // of the thing this file already states -- exactly the drift repo CLAUDE.md §4 forbids. So
  // the checker spawns the COPY's own sync script and reads this.
  if (process.argv.includes("--dump-deliveries")) {
    const deliveries = new Map();   // "<src rel>\0<dest rel>" -> Set<skill name>
    for (const { files, dirs, skipMissing } of syncGroups) {
      for (const { src, rel } of files) {
        if (!fs.existsSync(src)) continue;
        for (const skillDir of dirs) {
          if (skipMissing && !fs.existsSync(skillDir)) continue;
          const key = `${path.relative(repoRoot, src)}\0${rel}`;
          if (!deliveries.has(key)) deliveries.set(key, new Set());
          deliveries.get(key).add(path.basename(skillDir));
        }
      }
    }
    // Not console.log. check-docs.mjs's check 24 spawns this and JSON.parse's what comes back,
    // so a lost tail surfaces as a parse error in an unrelated gate rather than as a visible
    // truncation here. It is LOUD, not silent: the downstream package truncated the real
    // output at all 681 interior points and every one threw, and check-docs.mjs:3766 pushes a
    // failure on the parse error rather than skipping. So the risk is a gate that fails for
    // reasons unrelated to the tree -- which teaches people to re-run it -- not a scope that
    // narrows quietly. (An earlier version of this comment claimed the silent case; it was
    // reasoned, not measured, and it is wrong.)
    writeAllSync(1, JSON.stringify([...deliveries].map(([key, skills]) => {
      const [source, dest] = key.split("\0");
      return {
        source: source.split(path.sep).join("/"),
        dest: dest.split(path.sep).join("/"),
        skills: [...skills].sort(),
      };
    })) + "\n");
    process.exit(0);
  }

  let drift = 0;
  let written = 0;
  const report = [];

  for (const { files, dirs, skipMissing } of syncGroups) {
    for (const { src, rel } of files) {
      if (!fs.existsSync(src)) {
        if (skipMissing) continue;  // step files not created yet — skip
        throw new Error(`Missing canonical source: ${src}`);
      }
      const content = fs.readFileSync(src);
      const mode = fs.statSync(src).mode;
      for (const skillDir of dirs) {
        if (skipMissing && !fs.existsSync(skillDir)) continue;  // skill not created yet
        const dest = path.join(skillDir, rel);
        const exists = fs.existsSync(dest);
        const same = exists && fs.readFileSync(dest).equals(content);
        if (check) {
          if (!same) {
            drift += 1;
            report.push(`DRIFT: ${path.relative(repoRoot, dest)} does not match ${path.relative(repoRoot, src)}`);
          }
          continue;
        }
        if (same) continue;
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.writeFileSync(dest, content);
        fs.chmodSync(dest, mode);
        execFileSync("git", ["add", dest], { cwd: repoRoot, stdio: "ignore" });
        written += 1;
        // Written as it happens, not buffered: this arm mutates the tree, and the `git add`
        // below it can throw. A buffer flushed at the end would lose the record of what had
        // already been copied on exactly the run where you need it. Calling writeAllSync per
        // line is still safe -- the rule it enforces is "never queue", not "write once".
        writeAllSync(1, `Synced ${path.relative(repoRoot, dest)}\n`);
      }
    }
  }

  const orphans = findOrphans();
  for (const orphan of orphans) {
    report.push(`ORPHAN: ${orphan} exists but no sync group targets this skill for this file`);
  }

  if (check) {
    if (drift > 0 || orphans.length > 0) {
      if (drift > 0) {
        report.push(`\n${drift} shared-script copy/copies out of sync — run: npm run sync:scripts`);
      }
      if (orphans.length > 0) {
        report.push(`\n${orphans.length} orphaned shared-script copy/copies found — delete them ` +
          `(git rm) or, if the file legitimately belongs there now, add that skill to the owning ` +
          `sync group in ${path.basename(import.meta.url)}.`);
      }
      writeAllSync(2, report.join("\n") + "\n");
      process.exit(1);
    }
    report.push("Shared-script payload copies are in sync with skills/_shared/, with no orphans.");
  } else {
    report.push(`Shared-script sync complete (${written} file(s) written).`);
    if (orphans.length > 0) {
      report.push(`${orphans.length} orphaned copy/copies found — sync does not delete; remove them by hand.`);
    }
  }
  writeAllSync(1, report.join("\n") + "\n");
}
