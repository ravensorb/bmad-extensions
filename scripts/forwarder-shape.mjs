// The one definition of "this skill directory is a DEPRECATED forwarder", shared by every gate
// that needs the answer.
//
// WHY THIS FILE EXISTS. The signal lived in THREE places and all three disagreed:
//
//   check-module.mjs:1285      /^DEPRECATED forwarder for \/([a-z0-9-]+)/   description + target
//   sync-shared-scripts.mjs    /^DEPRECATED forwarder/i                     description only
//   check-module-view.mjs      /\bDEPRECATED\b/ anywhere in SKILL.md        the whole file
//
// The third was added last and matched neither of the other two: it accepted the word appearing
// anywhere in the body, so a skill merely DISCUSSING deprecation satisfied it. Three answers to
// one question in one repo is the drift class these gates exist to catch, so the parsing and the
// regexes are defined once, here. Adopted from the downstream package, which had the same defect
// across two files and factored it out first.
//
// WHAT IS DELIBERATELY *NOT* UNIFIED: the callers ask different questions of the same
// declaration, and collapsing them would change behaviour.
//
//   - `declaresForwarder()` is the bare declaration — the description opens with "DEPRECATED
//     forwarder", nothing more required. This is what the sync path has always used and it stays
//     that way on purpose. Tightening it to also demand `for /<target>` would silently start
//     syncing shared payload INTO any forwarder whose sentence is worded differently: a change
//     to what ships, triggered by a reworded sentence.
//   - `forwarderTarget()` additionally requires the declaration to name where it forwards to.
//     This is the handle `check-module.mjs` derives its whole rule from.
//   - `isBareForwarderShape()` is about the DIRECTORY, not the sentence: SKILL.md and
//     customize.toml and nothing else. Only the view checker requires it, because only it is
//     deciding whether to wave a finding through — and "it says it is a forwarder" is a claim a
//     skill makes about itself, while an empty directory is evidence. That asymmetry is the
//     reason the view checker is the strictest of the three, not an inconsistency.
//
// Every function returns null/false for an unreadable, unparseable or absent directory. A
// directory that cannot be read is not evidence of anything, so it must not satisfy a predicate
// something else is about to trust.
import fs from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";

// Anchored at the START of the description, so this is a declaration and not a mention: a skill
// whose description happens to discuss forwarders in passing is not one.
export const DECLARATION_RE = /^DEPRECATED forwarder/i;
// NARROWER than the downstream package's copy of this file, deliberately. Theirs allows `.`
// inside the captured name, which swallows a trailing sentence period: "forwarder for
// /l3io-plan." captures `l3io-plan.`, which then matches no catalogued skill and silently
// fails the exemption it was meant to grant. `[a-z0-9-]+` is what check-module.mjs has always
// enforced here and matches how BMad actually names skills. Reported upstream to them.
export const TARGET_RE = /^DEPRECATED forwarder for \/([a-z0-9-]+)/;
// The complete contents of a bare forwarder. Anything else means it carries payload, and a skill
// that carries payload is a skill.
//
// `payload-manifest.json` is in the set, and is the one member that is not payload itself.
// It is a DESCRIPTION of payload, and a forwarder's description names exactly the two files
// above. It is listed here because the rule this set enforces exists to stop a second module
// home appearing, and a module home is made by `module.yaml` / `module-help.csv` — which
// BMad's PluginResolver reads — never by a checksum file, which nothing in BMad reads at all.
//
// A forwarder needs one for the same reason every other skill does: `clean-payload.py`
// derives its delete set from the manifest and treats anything absent as "not ours. Not
// touched, not mentioned", so a forwarder without one is a directory `/l3io-doctor uninstall`
// walks straight past and leaves standing.
export const FORWARDER_FILES = new Set(["SKILL.md", "customize.toml", "payload-manifest.json"]);

// The frontmatter `description`, or null. Parsed as YAML rather than line-matched so a quoted,
// folded or block-scalar description reads the same as a plain one.
export function skillDescription(skillDir) {
  let text;
  try {
    text = fs.readFileSync(path.join(skillDir, "SKILL.md"), "utf8");
  } catch {
    return null;
  }
  const fm = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!fm) return null;
  let front;
  try {
    front = parseYaml(fm[1]);
  } catch {
    return null;
  }
  const d = front?.description;
  return typeof d === "string" ? d.trim() : null;
}

// Does this skill declare itself a forwarder? The sync path's question.
export function declaresForwarder(skillDir) {
  const d = skillDescription(skillDir);
  return Boolean(d && DECLARATION_RE.test(d));
}

// Which skill does it forward to, or null. A forwarder naming ITSELF is not a forwarder — it is
// a loop, and waving it through would exempt a skill on the strength of its own name.
export function forwarderTarget(skillDir) {
  const d = skillDescription(skillDir);
  const m = d && TARGET_RE.exec(d);
  if (!m) return null;
  return m[1] === path.basename(skillDir) ? null : m[1];
}

// Does the DIRECTORY have a forwarder's shape: SKILL.md and customize.toml, no payload files, no
// subdirectories? An empty directory is not a forwarder either — it is evidence of nothing.
export function isBareForwarderShape(skillDir) {
  let entries;
  try {
    entries = fs.readdirSync(skillDir, { withFileTypes: true });
  } catch {
    return false;
  }
  if (entries.length === 0) return false;
  return entries.every((e) => e.isFile() && FORWARDER_FILES.has(e.name));
}
