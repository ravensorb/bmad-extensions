#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# ///
"""
clean-payload.py -- remove THIS extension's installed payload, and nothing else.

Dry run by default. Nothing is deleted without `--apply`.

Why a hash and not a path list
------------------------------
`bmad uninstall` removes the entire BMAD installation -- it has no `--modules` flag -- so
removing one extension is not something BMad can do, and a hand-written list of our paths
would drift from what we actually ship the first time a file moved.

Each skill carries a generated `payload-manifest.json`: a SHA-256 per payload file, keyed
relative to that skill's own root. That file already IS the answer to "which files are ours",
it is regenerated whenever payload changes, and `check:manifest` fails the build when it
drifts. So the delete set is derived from it, and the hash decides each file's fate:

  hash matches    -> ours, unmodified. Safe to remove.
  hash differs    -> REPORTED, never removed. Somebody edited it; that edit is theirs, and
                     this script is not entitled to an opinion about it.
  not in manifest -> not ours. Not touched, not mentioned.

Erring this way is deliberate. Leaving a modified file behind is an inconvenience the
operator can see and fix. Deleting one is unrecoverable, and this estate has already paid
for an over-broad delete once.

What it never touches
---------------------
Project state and artifacts. `{implementation_artifacts}/state/**` is the project's own data
-- epics, sprints, stories, the issue backlog, the calibration file -- written by the project
over months and merely READ by our skills. It appears in no payload manifest, so the derived
scope already excludes it; the exclusion is restated here because it is the one mistake that
would matter, and a reader should not have to infer it.

`_bmad/scripts/pm-status/` (the self-installed package) IS removed file by file, each file only
when it matches a manifest hash for the same path under `scripts/pm_status/`: it is our payload,
and reinstalled automatically at the next skill activation. The pre-package single file
`_bmad/scripts/pm-status.py` is treated the same way when it is still present.

Bytecode and the directories our files emptied
----------------------------------------------
File-by-file removal is not what the operator sees. Measured on a real uninstall: all 91
payload files removed, success reported, and 8 `__pycache__` directories holding 20 `.pyc`
files left behind -- which also kept every package directory above them non-empty, so the
whole `_bmad/scripts/pm-status/` tree and the skill's own directories survived an uninstall
that said it was done. Before the package split there was one file and nothing to leave.

A `.pyc` is not in any manifest, and it never can be: the interpreter writes it when it
imports a file of OURS. It is a derived artifact of our payload, so it is removed -- under a
narrow rule, not a recursive delete. Only a directory literally named `__pycache__`, only
when it sits under a skill directory we identified or under the self-installed package
directory, and only when every entry in it is a `.pyc`/`.pyo` FILE. Anything else in there
and the directory is left whole, like any other survivor. The dry run lists what it would
prune, so `--apply` never removes a directory the operator was not shown.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

# Where an installer puts skills. Derived per-root rather than assumed: a project may carry
# one, both, or neither, and a missing one is not an error.
_SKILL_ROOTS = (".claude/skills", ".agents/skills")

# BOTH VALUES ARE OURS, and the pair is a migration, not an accident.
#
# The manifest's scope used to be "files synced from skills/_shared/", and `generated_from`
# recorded that. It is now every file the skill directory ships, so the writer emits
# `skills/<skill>/`. This constant is how a skill is recognised as OURS at all, so accepting
# only the new value would make this script walk past every project installed before the
# change -- reporting `none-found` and removing nothing, which reads exactly like a clean
# uninstall and is the most dangerous way to be wrong here.
#
# An upgrade replaces the whole skill directory, so manifest and script normally move
# together. "Normally" is doing too much work for an uninstall path: a partial copy, a
# restored backup, or a project upgraded by hand can leave one old manifest beside a new
# script. Accepting both costs one tuple and removes the whole class.
_GENERATED_FROM = ("skills/<skill>/", "skills/_shared/")
_SELF_INSTALLED = ("_bmad/scripts/pm-status.py",)      # the pre-package single file
_SELF_INSTALLED_DIR = "_bmad/scripts/pm-status"       # the package directory
_PACKAGE_PAYLOAD = "scripts/pm_status/"               # where a manifest keys the package's files
_BYTECODE_DIR = "__pycache__"
_BYTECODE_SUFFIXES = (".pyc", ".pyo")


def sha256(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def discover(project: Path) -> list[tuple[Path, dict]]:
    """(skill directory, manifest) for every installed skill of ours, under every skill root.

    Identity is a `payload-manifest.json` carrying this package's `generated_from`, so a BMad
    core skill in the same directory is never considered ours, and renaming our skills needs
    no change here.
    """
    found = []
    for root_rel in _SKILL_ROOTS:
        root = project / root_rel
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir(), key=lambda p: p.name):
            manifest = entry / "payload-manifest.json"
            if not (entry.is_dir() and manifest.is_file()):
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("generated_from") not in _GENERATED_FROM:
                continue
            if isinstance(data.get("files"), dict):
                found.append((entry, data))
    return found


def bytecode_dirs(roots) -> list[Path]:
    """`__pycache__` directories under our roots that hold NOTHING but bytecode files.

    Deepest-first, so removing them never leaves a parent `__pycache__` non-empty. The
    all-bytecode condition is the whole safety argument: one foreign file inside and the
    directory is a survivor like any other, so this can never widen into a recursive delete
    of a directory that merely happens to be named `__pycache__`.
    """
    out = []
    for root in roots:
        if not root.is_dir():
            continue
        for d in root.rglob(_BYTECODE_DIR):
            if not d.is_dir():
                continue
            try:
                entries = list(d.iterdir())
            except OSError:
                continue
            if all(e.is_file() and e.suffix in _BYTECODE_SUFFIXES for e in entries):
                out.append(d)
    return sorted(set(out), key=lambda p: (-len(p.parts), p.as_posix()))


def plan(project: Path):
    """(removable, modified, missing, manifests, bytecode) -- decided, nothing done."""
    removable, modified, missing, manifests = [], [], [], []
    roots = [project / _SELF_INSTALLED_DIR]
    for skill_dir, data in discover(project):
        roots.append(skill_dir)
        manifests.append(skill_dir / "payload-manifest.json")
        for rel, want in data["files"].items():
            p = skill_dir / rel
            if not p.is_file():
                missing.append(p)
                continue
            got = sha256(p)
            (removable if got == want else modified).append(p)

    # The self-installed copy is payload too, and it is the one file of ours that lives
    # outside a skill directory. It is matched against any manifest that ships it, because
    # self-install writes whichever module home's copy ran -- there is no single owner.
    wanted, wanted_tree = set(), {}
    for _, data in discover(project):
        for rel, want in data["files"].items():
            if rel.endswith("scripts/pm-status.py"):
                wanted.add(want)
            elif rel.startswith(_PACKAGE_PAYLOAD):
                wanted_tree.setdefault(rel[len(_PACKAGE_PAYLOAD):], set()).add(want)
    for rel in _SELF_INSTALLED:
        p = project / rel
        if not p.is_file():
            continue
        got = sha256(p)
        if got in wanted:
            removable.append(p)
        else:
            modified.append(p)
    pkg = project / _SELF_INSTALLED_DIR
    if pkg.is_dir():
        for p in sorted(pkg.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            sub = p.relative_to(pkg).as_posix()
            (removable if sha256(p) in wanted_tree.get(sub, ()) else modified).append(p)
    return removable, modified, missing, manifests, bytecode_dirs(roots)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="clean-payload.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete; without it nothing is changed")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    a = ap.parse_args(argv)

    project = Path(a.project_root).resolve()
    if not project.is_dir():
        sys.stderr.write(f"clean-payload.py: --project-root {project} is not a directory\n")
        return 2

    removable, modified, missing, manifests, bytecode = plan(project)
    if not (removable or modified or manifests):
        if a.format == "json":
            json.dump({"status": "none-found", "removable": [], "modified": []}, sys.stdout)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(f"clean-payload: no l3io payload found under {project}\n")
        return 4

    def rel(p):
        return str(p.relative_to(project))

    if a.format == "json":
        json.dump({"status": "applied" if a.apply else "dry-run",
                   "removable": sorted(rel(p) for p in removable),
                   "modified": sorted(rel(p) for p in modified),
                   "missing": sorted(rel(p) for p in missing),
                   "bytecode": sorted(rel(p) for p in bytecode)},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        verb = "Removing" if a.apply else "Would remove"
        sys.stdout.write(f"{verb} {len(removable)} payload file(s) under {project}\n")
        for p in sorted(removable):
            sys.stdout.write(f"  - {rel(p)}\n")
        if modified:
            sys.stdout.write(
                f"\nKEEPING {len(modified)} modified file(s) -- the hash does not match what "
                f"we shipped,\nso somebody edited them. Delete by hand if you meant to:\n")
            for p in sorted(modified):
                sys.stdout.write(f"  ! {rel(p)}\n")
        if bytecode:
            # Named in the dry run so --apply never removes a directory the operator was
            # not shown. These hold only .pyc/.pyo the interpreter wrote for OUR files.
            pverb = "Pruning" if a.apply else "Would prune"
            sys.stdout.write(f"\n{pverb} {len(bytecode)} __pycache__ director(ies) left by "
                             f"importing our own files, and any directory they empty:\n")
            for p in bytecode:
                sys.stdout.write(f"  ~ {rel(p)}\n")
        if missing:
            sys.stdout.write(f"\n{len(missing)} manifest entr(ies) already absent.\n")
        sys.stdout.write("\nProject state and artifacts are not touched: they appear in no "
                         "payload manifest.\n")

    if not a.apply:
        return 0

    failed = []
    for p in removable + manifests:
        try:
            p.unlink()
        except OSError as e:
            failed.append(f"{rel(p)}: {e}")
    # Bytecode BEFORE the prune loop: a surviving __pycache__ keeps every directory above it
    # non-empty, which is how a 91-file removal left the whole installed tree standing.
    # Deepest-first, one unlink per entry then one rmdir -- never rmtree.
    for d in bytecode:
        if not d.is_dir():
            continue
        for e in sorted(d.iterdir()):
            try:
                e.unlink()
            except OSError as exc:
                failed.append(f"{rel(e)}: {exc}")
        try:
            d.rmdir()
        except OSError as exc:
            failed.append(f"{rel(d)}: {exc}")
    # Prune directories that our own files emptied, deepest first. Never recursive: a
    # non-empty directory is left alone, which is what keeps a stray file from taking its
    # whole tree with it.
    seeds = {p.parent for p in removable + manifests} | {d.parent for d in bytecode}
    for d in sorted(seeds, key=lambda p: -len(p.parts)):
        cur = d
        while cur != project and cur.is_dir():
            try:
                cur.rmdir()          # fails on a non-empty directory, which is the guard
            except OSError:
                break
            cur = cur.parent
    if failed:
        sys.stderr.write("clean-payload.py: could not remove:\n")
        for f in failed:
            sys.stderr.write(f"  {f}\n")
        return 2
    sys.stdout.write(f"Removed {len(removable)} payload file(s), "
                     f"{len(manifests)} manifest(s) and {len(bytecode)} __pycache__ "
                     f"director(ies).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
