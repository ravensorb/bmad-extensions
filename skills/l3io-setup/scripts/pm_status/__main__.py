#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
# pm-status-version: 3.5.2   (machine-readable marker; `self-install` compares this across copies — keep at top)
"""
pm-status.py — deterministic, atomic, round-trip-safe writer for the l3io-pm
sharded state tree, and the reader behind its progress report.

Why this exists
---------------
Status transitions used to be free-form YAML edits the model performed between
phases. Under load or parallel execution those edits were skipped, malformed, or
they reordered/stripped the file. This script makes every transition a single
deterministic operation:

  * node addressing follows references/status-files.md (epic -> sprints -> stories),
  * writes are atomic (temp file + os.replace) so a crash never leaves a partial file,
  * ruamel round-trip load/dump preserves key order and comments so diffs stay clean,
  * `verify` is a hard read-back gate the orchestrator can branch on (exit code).

BMad standardizes on `uv run`; the PEP-723 header above lets `uv` provision
ruamel.yaml automatically. Always invoke via `uv run pm-status.py ...` — running
under `python3` directly bypasses the provisioning and fails with
ModuleNotFoundError anywhere ruamel.yaml is not already installed globally.

Subcommands
-----------
  set-status    --state-root S  (--story KEY | --epic ID [--sprint ID])  --status S
                [--title T] [--reason "R"] [--resolution "R"]
                [--flock] [--no-events] [--session-id ID]
                (story transitions gated per-pair via VALID_STORY_TRANSITIONS; sprint and
                epic keep enum-only validation. --status blocked REQUIRES --reason and is
                permitted only from in-progress or review; the reason lands on the node
                as blocked_reason and a paired block_open event is appended. A subsequent
                transition off blocked clears blocked_reason and appends block_close with
                the derived duration_hours. blocked -> done additionally REQUIRES
                --resolution. A story set to done resolves every key in its resolves:
                as fixed, ref the story, printing `resolved BL-...` per NEW resolution
                and `ok BL-... already resolved (...)` per key resolved before; a failure
                there warns, naming /l3io-doctor triage, and still exits 0 -- ADR-0003)
  sync-story-doc --artifacts-root R  (NOT the state root)  --story KEY  --status S
                [--quiet]
                (writes status: into the story markdown's frontmatter; the state
                YAML stays the source of truth. Never fails its caller -- a
                missing file, missing/unterminated frontmatter, or a parse
                error prints WARN to stderr and exits 0)
  story-doc-init --state-root S  --artifacts-root R  --story KEY
                (creates the story document skeleton from the state node when absent;
                an existing document is left untouched, exit 0 "exists")
  import-node   --state-root S  (--story KEY | --epic ID [--sprint ID])  --status S
                [--title T] [--classification C] [--origin {inferred}] [--origin-note N]
                [--reason R]   (REQUIRED when --story ... --status blocked; stored as
                                blocked_reason and in the paired block_open event; rejected
                                on any other kind or status)
                [--no-events] [--session-id ID]
                (creates a missing state node from a migration record; idempotent by
                SKIP -- an existing node is left untouched and no event is appended;
                exit 3 when a sprint or story's parent epic is absent)
  set-actual    --state-root S   --node {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
                [--elapsed-hours H] [--man-hours H] [--hitl-hours H]
                [--tokens-input K] [--tokens-output K] [--tokens-cache-write K] [--tokens-cache-read K]
                (any --tokens-* requires --model M; under --runtime claude ALL FOUR are
                required once any is given — an explicit 0 counts; [--token-rates JSON]
                overrides its rate card;
                cost is DERIVED from tokens x rates — --cost is declared but always rejected)
                [--tokens-na]   (in place of --tokens-*; runtime=other only, forbidden under runtime=claude)
                [--runtime {claude,codex,copilot,other}] [--flock] [--no-events] [--session-id ID]
                [--no-calibrate]
                (derives the node's calibration sample inline — write
                completion_evidence.fix_iterations BEFORE this call, or the scope/fix
                split cannot see it; the sample is emitted at most once per node,
                guarded by a `calibration_sampled_at` marker)
  set-estimate  --state-root S  (--story KEY | --epic ID [--sprint ID])
                [--man-hours-low H] [--man-hours-high H] [--hitl-hours-low H] [--hitl-hours-high H]
                [--elapsed-hours-low H] [--elapsed-hours-high H]
                [--tokens-k-min K] [--tokens-k-max K]
                (sprint/epic ranges; kind is inferred from --story vs --epic[/--sprint] —
                a story node instead takes the single-value aliases --man-hours H,
                --hitl-hours H, --elapsed-hours H, --tokens-k K;
                --time-hours* accepted as a deprecated alias for --elapsed-hours*;
                cost is DERIVED from tokens x rates — --cost/--cost-low/--cost-high are
                declared but always rejected; use estimate-story/estimate-rollup instead)
                [--confidence {low,medium,high}] [--flock]
  set-depends-on --state-root S  (--story KEY | --epic ID)
                (--add KEY [--add KEY ...] | --remove KEY [--remove KEY ...] [--force])
                (adds to or removes from depends_on, the one LIST-shaped field: epic keys on an epic
                node, story keys on a story node -- status-files.md §11. set-field would
                store a list as the string "['E001']", which a reader takes for a scalar.
                Idempotent, order preserved, all-or-nothing: every key is validated
                before anything is written. A sprint node has no depends_on: exit 2)
  import-actual --state-root S  --node story|sprint|epic  (--story KEY | --epic ID [--sprint ID])
                [--elapsed-hours H] [--man-hours H] [--hitl-hours H]
                (an actual OBSERVED ELSEWHERE, for a migration. runtime=other, tokens=N/A and
                no calibration sample are FIXED, not flags: --runtime, --tokens-*, --model and
                --calibrate are absent from its surface, so a call that would claim Claude
                provenance or poison the learned ratios is a usage error rather than a silent
                one. Delegates to set-actual, which is unchanged)
  set-field     --state-root S  (--story KEY | --epic ID [--sprint ID])  --field NAME --value V
                (refuses any field in DERIVED_NODE_FIELDS, any sub-path of one
                (<name>.x), or any parent path of one (completion_evidence, which would
                replace test_runs) -- completion_evidence.tests_passing (use
                add-test-run), status (use set-status), resolves (use promote-issue))
  add-test-run  --state-root S  --story KEY  --command CMD  --exit-code N
                (appends {command, exit_code} to completion_evidence.test_runs and
                derives completion_evidence.tests_passing as all(exit_code == 0) over
                the LAST run of each distinct command -- record failures too, a
                re-run of the same command supersedes them for the boolean only)
  usage         [TRANSCRIPT ...]  [--claude-session ID] [--state-root S]
                [--agent NAME] [--epic ID] [--sprint ID] [--story KEY]
                [--since ISO] [--until ISO] [--allow-unidentified]
                [--model M] [--token-rates JSON] [--format {text,json}]
                (sums a session transcript's token usage by class, for feeding
                set-actual; verifies the transcript's sessionId before summing
                and refuses an unconfirmed file unless --allow-unidentified;
                omit TRANSCRIPT to resolve this session's own transcript from
                $CLAUDE_CODE_SESSION_ID or --claude-session; --state-root plus
                node keys derive a --since/--until window from that node's
                dispatch bracket instead of passing one explicitly)
  verify        --state-root S  --scope {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
                [--require-tokens] [--runtime {claude,other}]
                (--scope epic checks structural/back-reference integrity across the
                epic's whole subtree; --scope story/sprint check completion of one node)
  list-epics    --state-root S  [--format keys|json]
                (read-only; empty/absent state -> empty output, exit 0; keys default
                prints one E{nnn} per line, sorted; json prints [{key, bucket, status}, ...]
                with bucket in active/planned/archived order)
  list-stories  --state-root S  --epic E  [--sprint S]  [--format keys|json]
                (read-only; absent epic exits 3; absent sprint -> empty output, exit 0;
                filters out sprint.yaml/epic.yaml and any non-story .yaml files)
  show          --state-root S  --epic ID  [--sprint ID]
  report        --state-root S  [--plan P] [--format tree|json|md] [--out F]
                [--all] [--watch SECS]
  dispatch      --state-root S  --event {open,close}  --agent NAME
                [--epic ID] [--sprint ID] [--story KEY] [--session-id ID]
                (appends a dispatch_open/dispatch_close event to events.jsonl;
                feeds report's stall detection and marks the child/orchestration
                spend boundary -- records timestamps only, never a token count)
  set-lock      --state-root S  --epic ID  --session-id SESS  [--ttl-minutes N]
  clear-lock    --state-root S  --epic ID
  check-lock    --state-root S  --epic ID  --session-id SESS
  append-issue  (--state-root S | --file F)  [--key BL-E{nnn}-{nnn}]  --epic E  [--sprint S]  --title T
                --source S  --severity {Low,Medium,High,Critical}  [--description D]
                [--allow-duplicate]
                [--session-id ID]   (keys: max(next[epic], highest suffix in either
                issue file + 1); an explicit --key is canonicalized and must match --epic)
                (--key omitted allocates the next number for --epic under a lock --
                the caller never invents {nnn}; an explicit --key that already exists
                exits 2, as does allocating past {nnn} = 999. A content duplicate (same
                normalized title/epic/sprint/source)
                of an open item, or of a resolved wontfix/duplicate/obsolete item whose
                severity is at least the new finding's, is skipped (exit 0, nothing written); a
                match against a resolved fixed item is appended as a recurrence, and
                one above a wontfix/duplicate/obsolete severity as re-raised. The
                newest resolved match decides. --allow-duplicate bypasses all of it)
  list-issues   --state-root S  [--epic E] [--sprint S]
                [--severity {Low,Medium,High,Critical}] [--format {text,json}]
                [--status {backlog,scheduled}] [--resolved [--resolution R]] [--all]
                (open items by default; --resolved lists issues-resolved.yaml;
                --all: JSON {open, resolved} under one lock; every JSON item carries
                origin_archived)
                (filters combine with AND; a repeated --severity ORs the given severities;
                a missing issues.yaml, or a filter matching nothing, is success — exit 0
                with an empty result, not an error)
  resolve-issue --state-root S  --key K  --resolution {fixed,wontfix,duplicate,obsolete}
                [--ref R] [--note N] [--session-id ID] [--cause {cli,triage,plan-intake}]
                (moves an open item to issues-resolved.yaml -- resolved file first, open
                file second; fixed needs --ref story key or SHA, duplicate needs --ref an
                open or non-duplicate BL key, wontfix/obsolete need --note; an already
                resolved key exits 0 after clearing any stale open copy)
  update-issue  --state-root S  --key K  --severity {Low,Medium,High,Critical}
                [--note N] [--session-id ID] [--cause {cli,triage,plan-intake}]
                (re-severities an OPEN item; a resolved key exits 2, one in neither
                issue file 3; the severity it already has exits 0 as "unchanged",
                writing no file and no event)
  promote-issue --state-root S  --artifacts-root R  --key K [--key K2 ...]  --epic E
                --sprint S  --classification {simple,standard,complex}  [--title T]
                [--model M] [--token-rates JSON] [--session-id ID] [--cause C]
                (creates an estimated story whose `resolves:` lists the items, writes its
                document, rolls up sprint and epic, then marks the items scheduled; a key
                given TWICE is refused (exit 2) rather than deduped, because --title is
                required on len(keys) > 1 and collapsing a repeat would skip it --
                schedule-issue still dedups, since nothing there reads the count; every
                refusal is checked before the first write; a retry after an interrupted
                run resumes the existing story -- only with the same --epic/--sprint (a
                claimant elsewhere exits 2 naming them), and a dead claim (a story under
                archived/ that is not done) is ignored; a foreign epic lock exits 5 when
                check-lock would report it LOCKED, and whenever promote cannot evaluate
                it (not a mapping, no session_id, a missing, unparseable or timezone-less
                claimed_at, a non-integer ttl_minutes); the holder must equal
                --session-id exactly to count as this session's own, as in set-lock and
                check-lock, and a whitespace-only one is no session_id -- clear-lock removes an
                abandoned one; a story node that does not parse, is not valid UTF-8 or
                is not a mapping, or a claimant whose key: is malformed, exits 2 naming
                the file, before any write)
  schedule-issue --state-root S  --key K [--key K2 ...]  --story E{nnn}-S{nn}-{nnn}
                [--session-id ID] [--cause C]
                (attaches open items to a story that ALREADY EXISTS -- the counterpart to
                promote-issue, which only ever creates one; appends each key to the
                story's `resolves:` and marks the items scheduled, story node first so an
                interrupted run leaves finding 1d, which repair-issue --action link
                repairs, rather than 1e, which has no single-key repair; idempotent by
                skip for a key already scheduled to THIS story, exit 2 for one scheduled
                to a different story; exit 3 for an absent story, exit 2 for a story that
                is `done` or whose epic is under archived/, exit 4 on a back-reference
                mismatch; does NOT re-estimate the story or roll up its parents; locks in
                promote-issue's order -- epic_node_lock then one issues_lock spanning the
                decisive check through the save; every refusal is checked before the first
                write)
  audit-issues  --state-root S  [--format {text,json}]
                (read-only integrity checks 1a-1l over both issue files and the story
                nodes' resolves:, read under issues_lock when either issue file exists;
                otherwise the story walk still runs, unlocked, over an empty store;
                a key with a resolved entry is not evaluated for 1b, 1c, 1d, 1f
                or 1g -- its stale open copy shows as 1a, and 1h and 1j still
                apply; a key duplicated within one file (1i) is not evaluated
                for 1b, 1c, 1d, 1f or 1g either; 1d/1h ignore a dead claim -- a
                story under archived/ that is not done; 1j fires only when the
                ref story's resolves: lists the key; 1e also reports every
                non-canonical alias key in next (1 or '1' for '001') whatever its
                value, and any next above 1000; 1l reports a `story` or `ref`
                field holding a story key no story carries any more, and names
                the heir when exactly one story records it in previous_keys --
                a scheduled item with such an heir is 1l, NOT 1b, because
                repointing restores the scheduling that unschedule discards;
                exit 4 when anything is
                found, and on a malformed issue file or a story node that does
                not parse, is not valid UTF-8 or is not a mapping, where
                --format json prints {"findings": [], "error": MSG})
  repair-issue  --state-root S  --key K  --action {unschedule,link,repoint,reseed,reopen}
                [--story KEY] [--session-id ID] [--cause C]
                (each action refuses unless its audit finding holds: unschedule 1b/1g,
                link 1d (--story must be the story that lists K), repoint 1l with an
                heir (it repoints every stale story-key field of the one item the key
                resolves to, resolved entry first, and writes an issue_repointed event),
                reseed 1e, reopen 1j;
                unschedule and link also refuse a key with a resolved entry -- rerun
                resolve-issue to clear the stale open copy (1a); reseed merges
                non-canonical aliases of the epic's next key by max, drops them, and
                never lowers it, but refuses (nothing written) any of those values
                above 1000;
                unschedule writes an issue_unscheduled event; a story node that does
                not parse, is not valid UTF-8 or is not a mapping exits 2 naming the
                file, before any write)
  dump-plan     --state-root S  [--pretty]
                  (the planned tree plus read-only context, as JSON. The one read interface
                   for consumers that need a plan's SHAPE: check 26 forbids any file under
                   skills/ from assembling a state path, so the reorg analyzer asks for the
                   tree rather than walking it. Active and archived appear as keys and
                   dependencies only -- they are read-only input.)
  retire-epic   --state-root S  --epic ID  --reason TEXT
                  (move-epic --to archived plus retired_reason/retired_at; epic-level only,
                   because planned/active/archived are folders of EPIC directories and a
                   single retired story has nowhere to go. Never deletes.)
  reparent-story  --state-root S  --artifacts-root A  --story K  --to-epic E  --to-sprint SP
                  (moves a PLANNED story to another sprint, re-keying it; moves the state
                   node and its document together, preserving any -slug, repoints inbound
                   depends_on and both backlog story-key fields (`story` and `ref`, in both
                   issue files), appends the old key to previous_keys, and
                   raises the source sprint's high-water so the vacated key is never reissued)
  reorg-log     --state-root S  [--hash] [--record FILE] [--list] [--show ID]
                [--format {text,json}]
                  (the reorg journal. --hash prints the planned tree's PLACEMENT digest and
                   is captured BEFORE applying, as the record's pre_hash; --record appends
                   one reorg's rationale and operations and prints its id. A record whose
                   operations include a kind undo cannot invert is refused, so an entry never
                   promises an undo that cannot run.)
  reorg-undo    --state-root S  --artifacts-root A  --id R0001  [--check]
                  (inverts a recorded reorg through the same reparent-story/move-epic
                   primitives, in reverse order. REFUSES if the planned tree's placement
                   digest no longer matches what was recorded: an undo replays placements
                   derived from a plan that no longer exists. Restores PLACEMENT, not keys --
                   the allocator's high-water never decreases, by design.)
  move-epic     --state-root S  --epic ID  --to {planned,active,archived}
  archive-epic  --state-root S  --epic ID   (alias for move-epic --to archived)
  calibration   show  --state-root S  [--format {text,json}]
                (inspects pm-calibration.yaml; a missing file is a normal
                cold-start state, not an error)
  estimate-story --state-root S  --story KEY  --classification C
                [--confidence {low,medium,high}] [--model M] [--token-rates JSON]
                (writes estimate = band_mid x scope_ratio x fix_factor, per
                metric, using whichever calibrated scope ratio is active per
                metric; cost is priced from the banded tokens_k total rather
                than banded/calibrated on its own; --model falls back to
                DEFAULT_ESTIMATE_MODEL)
  estimate-rollup --state-root S  --epic ID  [--sprint ID]
                [--model M] [--token-rates JSON]
                (rolls a sprint's story estimates, or an epic's sprint
                estimates, up to the parent as sum(children) + a calibrated
                closure band + a calibrated orchestration band, always in
                range form; omit --sprint for epic-level)
  rates         [--model M] [--token-rates JSON]
                (prints the effective per-class token rate table -- shipped
                defaults merged with any --token-rates/modules.l3io-pm
                override -- so what actually prices tokens is inspectable
                without reading source or guessing; read-only)
  self-install  --dest PATH  [--force]
  adr-reserve   --state-root S  --epic ID  --slug SLUG  [--count N]
                (reserves N sequential ADR numbers under a lock, before dispatch;
                prints one zero-padded number per line; see adr_register_path)
  notice        --state-root S  --key KEY
                (records a one-time-ever advisory notice in {state-root}/.notices.yaml
                under flock, keyed on KEY alone -- there is no session concept that
                outlives one skill invocation, so this is scoped to the project, not a
                session; exit 0 = not yet emitted for KEY (and now recorded), exit 1 =
                already emitted, exit 2 = usage error OR an unexpected recording failure
                (never conflated with exit 1); advisory only -- a damaged notices file
                never blocks the caller, but a failed write is reported, not silently
                treated as success)
  sync-agent-instructions  --runtime {claude,codex,copilot,other}  --project-root P
                [--body-file F] [--version V]  (--apply | --remove | --check)
                (creates, replaces or removes the marker-wrapped l3io block in the running
                harness's instruction file, under a lock held across read and write; never
                deletes the file. A block already present in ANOTHER harness's instruction
                file is refreshed in place by --apply and stripped by --remove -- ours to
                keep current wherever it is -- but never created there. exit 1 = --check
                found no block for this harness, exit 2 = usage, an undecodable file, or
                ambiguous markers, exit 3 = --check found another harness's file holding a
                stale copy)

Exit codes: 0 = success/verified, 1 = notice already emitted for this key
(notice only), 2 = usage error or, for notice only, an unexpected recording failure,
3 = node not found, 4 = verification failure (missing/invalid field), 5 = epic locked.
Errors go to stderr; machine output (verify summaries) goes to stdout.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

# --------------------------------------------------------------------------- #
# SCRIPT-PATH BOOTSTRAP. Nothing relative may appear above this block.
#
# The shipped binding runs this file as a SCRIPT (`uv run .../pm-status/__main__.py`),
# where `__package__` is empty and every relative import below raises "attempted
# relative import with no known parent package". Under `import pm_status` -- which is
# how the suite reaches it -- there IS a package and they resolve, so the suite cannot
# see that failure on its own. TestInvocationModes runs the script path for exactly
# that reason, including one test that plants a relative import into a copy of the
# package and fails if this block is gone.
#
# It loads THIS directory as a package named `pm_status` BY PATH and re-enters through
# it, so the relative imports below and the `sys.modules[__name__] = _main` facade in
# __init__.py behave exactly as they do under `import pm_status`. By path, never by
# name: the installed directory is `pm-status`, with a hyphen, which is not an
# importable identifier -- a bootstrap that imported the name passed on a toy fixture
# and failed on the real install.
#
# The exit value is read back out of sys.modules rather than off the module object this
# block created: executing __init__.py REPLACES sys.modules["pm_status"] with the
# __main__ module object, and that is the one carrying `main`.
# --------------------------------------------------------------------------- #
if not __package__ and __name__ == "__main__":
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _spec = importlib.util.spec_from_file_location(
        "pm_status",
        os.path.join(_pkg_dir, "__init__.py"),
        submodule_search_locations=[_pkg_dir],
    )
    sys.modules["pm_status"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules["pm_status"])
    sys.exit(sys.modules["pm_status"].main())

# The dependency root (`core`, see pm_status/core/__init__.py) and the node layer
# (`nodes`, see pm_status/nodes/__init__.py). Two import styles, and the difference is
# load-bearing. The names the suite mock.patches are reached through the MODULE OBJECT
# (`core._load(...)`, `core._atomic_dump(...)`, `nodes.save_node(...)`,
# `nodes.epic_file(...)`): a `from .core import _load` binding here would be a private
# copy that a patch on core could not reach, so the test would pass while guarding
# nothing. Everything else is re-exported by name, because `pm_status.<name>` is this
# module's globals and the suite reads several hundred of them directly through the
# __init__.py facade.
#
# The split is per patch target, not per module, and a patched name is left OUT of the
# re-export lists below: a `pm.save_node` binding beside `pm.nodes.save_node` is a second
# thing to patch, and the wrong one passes silently. TestPatchTargetsAreDefinedInMain is
# the standing guard. `nodes` also carries check 26's resolver-section markers, so it is
# the one file in this package allowed to assemble a state path; nothing here does.
#
# `metrics` is a DIRECTORY of modules (events, rates, calibration, estimates, spend,
# report, actuals_usage -- see pm_status/metrics/__init__.py), so its patch targets are
# two levels down: `metrics.estimates.compute_story_estimate` and
# `metrics.estimates.rollup_parent_estimate` are called through the module object below,
# in `_promote_issue`, and `metrics.actuals_usage.dispatch_window` has no caller outside
# its own module. None of the three is re-exported, here or by `metrics/__init__.py`.
from . import core, metrics, nodes
from .core import (
    _ADR_LOCK,  # noqa: F401 -- re-export only
    _AGENT_INSTR_LOCK,  # noqa: F401 -- re-export only
    _CAL_LOCK,  # noqa: F401 -- re-export only
    _EPIC_NODE_LOCK,  # noqa: F401 -- re-export only
    _GITIGNORE_PATTERNS,  # noqa: F401 -- re-export only
    _ISSUES_LOCK,  # noqa: F401 -- re-export only
    _LOCK_IGNORE_CHECKED,  # noqa: F401 -- re-export only
    _LOCK_IGNORE_LINE,  # noqa: F401 -- re-export only
    _NOTICES_LOCK,  # noqa: F401 -- re-export only
    # Facade-only, and PINNED: test_dir_for_status_is_the_inverse_of_status_for_dir
    # reads pm.DIR_FOR_STATUS. `nodes` imports it from core directly, so dropping it
    # here would error that test rather than go quiet.
    DIR_FOR_STATUS,  # noqa: F401 -- re-export only
    EVENTS_FILENAME,  # noqa: F401 -- re-export only
    METRIC_FIELDS,
    NOTICES_FILENAME,  # noqa: F401 -- re-export only
    PM_STATUS_VERSION,
    STATUS_DIRS,
    STATUS_FOR_DIR,
    VALID_EPIC_STATUS,
    VALID_SPRINT_STATUS,
    VALID_STORY_STATUS,
    VALID_STORY_TRANSITIONS,
    PMError,
    _coerce,
    _die_notfound,
    _die_usage,
    _drop_legacy_file,  # noqa: F401 -- re-export only
    _ensure_lock_ignore,  # noqa: F401 -- re-export only
    _event_keys,
    _exit_code_or_fail,
    _file_lock,
    _file_sha,  # noqa: F401 -- re-export only
    _hashable_field,  # noqa: F401 -- re-export only
    _indexable_key,  # noqa: F401 -- re-export only
    _is_na,
    _is_number,
    _iter_count,
    _lock_age_minutes,
    _lock_rule_present,  # noqa: F401 -- re-export only
    _missing_ignore_patterns,  # noqa: F401 -- re-export only
    _norm_num,
    _now_iso,
    _num_or_none,
    _parse_iso,
    _parse_version_line,  # noqa: F401 -- re-export only
    _require_epic_lock,  # noqa: F401 -- re-export only
    _run_core,
    _state_root_of_node,  # noqa: F401 -- re-export only
    _tree_files,  # noqa: F401 -- re-export only
    _yaml,
    adr_register_lock,
    adr_register_path,
    append_event,
    calibration_lock,  # noqa: F401 -- re-export only
    calibration_path,  # noqa: F401 -- re-export only
    canonical_epic_key,
    canonical_sprint_key,
    cmd_self_install,
    epic_dirname,
    epic_lock_path,  # noqa: F401 -- re-export only
    epic_node_lock,
    events_path,  # noqa: F401 -- re-export only
    issues_lock,
    notices_path,
    package_root,  # noqa: F401 -- re-export only
    parse_story_key,
    sprint_dirname,
    sweep_stale,  # noqa: F401 -- re-export only
    tree_digest,  # noqa: F401 -- re-export only
)

# The instruction-block leaf, re-exported by name: nothing in the suite patches a name it
# defines. It reaches `core` as a module object itself.
from .instructions import (  # noqa: F401 -- re-export only
    _FENCE_RE,
    _RUNTIME_INSTRUCTION_FILE,
    BEGIN_RE,
    END_RE,
    BlockError,
    _fenced_spans,
    _foreign_blocks,
    _newline,
    _normalise_nl,
    _other_instruction_files,
    _outside_fences,
    _render,
    _strip_markers,
    apply_block,
    cmd_sync_agent_instructions,
    find_block,
    remove_block,
)
from .metrics.actuals_usage import (
    CLAUDE_SESSION_ENV,
    cmd_import_actual,
    cmd_set_actual,
    cmd_usage,
    discover_session_transcript,  # noqa: F401 -- re-export only
    read_transcript_usage,  # noqa: F401 -- re-export only
    resolve_session_transcript,  # noqa: F401 -- re-export only
)
from .metrics.calibration import (
    CALIBRATION_MARKER,  # noqa: F401 -- re-export only
    CALIBRATION_METRICS_MARKER,  # noqa: F401 -- re-export only
    CALIBRATION_SCHEMA_VERSION,  # noqa: F401 -- re-export only
    CLASSIFICATIONS,
    CLOSURE_RANGE_KEYS,  # noqa: F401 -- re-export only
    COLD_START_FIX_FACTOR,  # noqa: F401 -- re-export only
    COLD_START_SCOPE_RATIO,  # noqa: F401 -- re-export only
    ORCH_MID,  # noqa: F401 -- re-export only
    ORCH_SPREAD,  # noqa: F401 -- re-export only
    ORCHESTRATION_MARKER,  # noqa: F401 -- re-export only
    TOKEN_BASIS_MARKER,  # noqa: F401 -- re-export only
    WALL_CLOCK_METRICS,  # noqa: F401 -- re-export only
    _component_samples,  # noqa: F401 -- re-export only
    _mark_sampled,  # noqa: F401 -- re-export only
    active_closure_ratio,  # noqa: F401 -- re-export only
    active_fix_factor,  # noqa: F401 -- re-export only
    active_orchestration_fraction,  # noqa: F401 -- re-export only
    active_scope_ratio,  # noqa: F401 -- re-export only
    actual_event_times,  # noqa: F401 -- re-export only
    cmd_calibration,
    derive_closure_sample,  # noqa: F401 -- re-export only
    derive_story_sample,  # noqa: F401 -- re-export only
    load_calibration,  # noqa: F401 -- re-export only
    migrate_calibration,  # noqa: F401 -- re-export only
    migrate_calibration_metrics,  # noqa: F401 -- re-export only
    migrate_calibration_token_basis,  # noqa: F401 -- re-export only
    new_calibration,  # noqa: F401 -- re-export only
    record_closure_sample,  # noqa: F401 -- re-export only
    record_orchestration_sample,  # noqa: F401 -- re-export only
    record_story_sample,  # noqa: F401 -- re-export only
    redrive_story_samples,  # noqa: F401 -- re-export only
    save_calibration,  # noqa: F401 -- re-export only
    weighted_ratio,  # noqa: F401 -- re-export only
)
from .metrics.estimates import (
    BASE_BANDS,  # noqa: F401 -- re-export only
    DEFAULT_ESTIMATE_MODEL,
    cmd_estimate_rollup,
    cmd_estimate_story,
    observed_mix,  # noqa: F401 -- re-export only
    split_tokens,  # noqa: F401 -- re-export only
)

# The measurement layer's exports, by name. The three mock.patch targets --
# `compute_story_estimate`, `rollup_parent_estimate` (metrics/estimates) and
# `dispatch_window` (metrics/actuals_usage) -- are deliberately absent, so a patch
# repointed to `pm.metrics.<mod>.<name>` without the matching call-style change here
# is a NameError rather than a patch that quietly reaches nobody.
from .metrics.events import (
    DEFAULT_STALL_MINUTES,
    _block_duration_since_last_open,
    _total_blocked_hours,  # noqa: F401 -- re-export only
    build_events_index,  # noqa: F401 -- re-export only
    cmd_dispatch,
    compute_flags,  # noqa: F401 -- re-export only
    dwell_hours,  # noqa: F401 -- re-export only
    open_dispatches,  # noqa: F401 -- re-export only
)
from .metrics.rates import (
    COLD_START_TOKEN_MIX,  # noqa: F401 -- re-export only
    FRESH_TOKEN_CLASSES,  # noqa: F401 -- re-export only
    TOKEN_CLASSES,
    TOKEN_RATES,  # noqa: F401 -- re-export only
    cmd_rates,
    cost_from_tokens,
    rate_overrides,
    resolve_rates,
)
from .metrics.report import (
    _write_spend,
    build_progress_model,  # noqa: F401 -- re-export only
    cmd_report,
    list_all_epics,  # noqa: F401 -- re-export only
    load_plan,  # noqa: F401 -- re-export only
    render_tree,  # noqa: F401 -- re-export only
)
from .metrics.spend import (
    SPEND_BUCKETS,  # noqa: F401 -- re-export only
    _fmt_actuals,
    _spend_total,  # noqa: F401 -- re-export only
    rollup_epic,
    rollup_sprint,
)

# The node layer's exports, by name. `save_node` and `epic_file` are deliberately absent
# -- the suite patches them, so they are reached as `nodes.<name>` (see above).
from .nodes import (
    BOOL_NODE_FIELDS,
    DERIVED_NODE_FIELDS,
    NUMERIC_NODE_FIELDS,
    _check_lock_verdict,
    _epic_path_or_die,
    _epic_write_lock,
    _infer_kind,
    _load_checked,
    _sprint_key_from_dir,
    check_backrefs,
    deps_list,
    ensure_node_path,
    find_epic_dir,
    init_story_doc,
    iter_epic_dirs,
    iter_story_files,
    list_sprint_dirs,
    list_story_files,
    load_node,
    resolve_node_path,  # noqa: F401 -- re-export only
    sprint_file,
    story_doc_path,
    story_file,
)

# Type-checking only, and load-bearing. Every ruamel import in this package is lazy or
# guarded -- the `except ModuleNotFoundError` guard that prints a readable message lives
# in core -- so `CommentedSeq` is out of scope at module level here, and an annotation
# naming a type mypy cannot resolve degrades silently to `Any`: calling `Any` is
# permitted, so IssueStore's accessors would type-check nothing.
#
# TYPE_CHECKING is False at runtime, so nothing is imported and core's guard is
# untouched. `check:types` fails on [name-defined], which is what removing this import
# looks like, so the gate cannot go blind without failing.
if TYPE_CHECKING:
    from ruamel.yaml.comments import CommentedSeq


def load_adr_register(state_root: str):
    """Load the ADR register, or a fresh skeleton if absent, empty, or malformed.

    Never raises: an absent file, an empty file, and a `next` that fails to
    parse as an int are all legal states that resolve to "start at 1" — a
    project with no adr-register.yaml yet must still work.
    """
    p = adr_register_path(state_root)
    y, data = core._load(p)
    if data is None:
        from ruamel.yaml.comments import CommentedMap
        reg = CommentedMap()
        reg["next"] = 1
        reg["reserved"] = []
        return y, reg
    if data.get("reserved") is None:
        data["reserved"] = []
    return y, data


# The `ADR-` prefix is optional on the one home and case-insensitive on both. The
# scan's whole reason for existing (see `highest_adr_on_disk`) is the ADR nobody
# allocated through the register -- a hand-written one -- and hand-written ADRs are
# commonly named `ADR-NNNN-slug.md`, which matched neither pattern. A real directory
# holding ADR-0004..ADR-0025 scanned as "highest is 0", exactly as confidently as an
# empty one, and `adr-reserve` then issued numbers that were already on disk.
# Widening can only raise the floor the allocator starts from, never lower it.
_ADR_DOC_NAME = re.compile(r"^(?:[Aa][Dd][Rr]-)?(\d{4})-.+\.md$")
_ADR_OLD_HOME_NAME = re.compile(r"^[Aa][Dd][Rr]-(\d{4})-.+\.md$")


def _git_toplevel(path: str):
    """The git work tree containing `path`, or None (not a repo, or no git on PATH)."""
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                           capture_output=True, check=False, text=True)
    except OSError:
        return None
    top = r.stdout.strip()
    return top if r.returncode == 0 and top else None


class AdrHomeUnresolved(Exception):
    """The one ADR home (ADR-0005) could not be located, so the disk scan is impossible.

    Raised rather than warned-and-continued. `adr-reserve` is the only thing standing
    between two agents and one ADR number, so a number allocated from a scan that never
    happened is worse than no number at all: the caller reads exit 0 and a four-digit
    string off stdout and has no way to tell it apart from a real allocation. The old
    behaviour printed `0001` next to a stderr warning nobody captured.
    """


def highest_adr_on_disk(state_root: str, adr_dir: str = "") -> int:
    """Highest ADR number already written, in the one home and in the old one (ADR-0005).

    The register still records who is in flight; this scan only stops a new reservation
    from colliding with a file that already exists: a hand-written ADR, a Mode C ADR, or
    an ADR in a project that has not run `migrate-adrs`. The one home is `adr_dir` when
    given (step files pass {project-root}/docs/adr, since a BMad project need not be the
    repository root), else <git top-level of the state root>/docs/adr.

    Raises AdrHomeUnresolved when neither is available. The default is deliberately NOT
    widened to some guess (the state root's parent, the cwd): scanning the wrong tree
    reports "highest is 0" just as confidently as scanning an empty right one.
    """
    impl = os.path.dirname(os.path.abspath(state_root))
    hi = 0
    for arch in glob.glob(os.path.join(impl, "epic-*", "arch")):
        for name in os.listdir(arch):
            m = _ADR_OLD_HOME_NAME.match(name)
            if m:
                hi = max(hi, int(m.group(1)))
    if not adr_dir:
        top = _git_toplevel(state_root if os.path.isdir(state_root) else impl)
        if top is None:
            raise AdrHomeUnresolved(
                f"{state_root} is not inside a git work tree, so the one ADR home "
                f"(<git top-level>/docs/adr) cannot be located, and the old home "
                f"(epic-*/arch/) alone does not say what numbers docs/adr already "
                f"holds. Pass --adr-dir DIR naming the project's ADR directory "
                f"(normally {{project-root}}/docs/adr) and retry.")
        adr_dir = os.path.join(top, "docs", "adr")
    if adr_dir and os.path.isdir(adr_dir):
        for name in os.listdir(adr_dir):
            m = _ADR_DOC_NAME.match(name)
            if m:
                hi = max(hi, int(m.group(1)))
    return hi


def cmd_adr_reserve(args) -> int:
    """Allocate ADR numbers before dispatch, under a lock.

    A directory listing shows who has FINISHED writing. Only a register knows
    who is in flight. Three parallel ADR agents read the same near-empty
    directory and two of them chose 0013 while two chose 0014; the surviving
    ADR-0014 was cited by four stories meaning two different documents, and
    repairing that cost more than the gate it came from.
    """
    if args.count < 1:
        sys.stderr.write("ERROR --count must be >= 1\n")
        return 2
    from ruamel.yaml.comments import CommentedMap
    with adr_register_lock(args.state_root):
        yaml, reg = load_adr_register(args.state_root)
        # Unlike a malformed `next` (recoverable -- reset to 1 and keep going),
        # a malformed `reserved` is refused outright rather than repaired: this
        # list is the record of who is in flight, which is the entire reason
        # the register exists. Silently replacing it with [] would let a new
        # reservation collide with an in-flight one it can no longer see.
        reserved = reg.get("reserved")
        if not isinstance(reserved, list):
            sys.stderr.write(
                f"pm-status.py: adr-register.yaml has a malformed 'reserved' field "
                f"(expected a list, got {type(reserved).__name__}: {reserved!r}); "
                f"refusing to reserve -- a register that cannot say who is already "
                f"in flight cannot be trusted to hand out a new number. Fix or "
                f"restore adr-register.yaml by hand, then retry.\n")
            return 2
        try:
            start = int(reg.get("next", 1))
        except (TypeError, ValueError):
            sys.stderr.write(f"pm-status.py: adr-register.yaml has a malformed "
                             f"'next' ({reg.get('next')!r}); resetting to 1\n")
            start = 1
        start = max(start, 1)
        # Refuse rather than guess. Every other failure in this function returns 2
        # before a number is printed, and so does this one: a caller capturing stdout
        # cannot tell a guessed 0001 from a scanned one.
        try:
            on_disk = highest_adr_on_disk(args.state_root, args.adr_dir)
        except AdrHomeUnresolved as exc:
            sys.stderr.write(f"pm-status.py: adr-reserve: refusing to allocate -- {exc}\n")
            return 2
        start = max(start, on_disk + 1)
        numbers = list(range(start, start + args.count))
        for n in numbers:
            entry = CommentedMap()
            entry["number"] = n
            entry["slug"] = args.slug
            entry["epic"] = canonical_epic_key(args.epic)
            entry["reserved_at"] = _now_iso()
            reg.setdefault("reserved", []).append(entry)
        reg["next"] = start + args.count
        core._atomic_dump(yaml, reg, adr_register_path(args.state_root))
    sys.stdout.write("\n".join(f"{n:04d}" for n in numbers) + "\n")
    return 0


def cmd_notice(args) -> int:
    """Record a one-time-ever advisory notice for this project. Exit 0 = emit it now (and
    record it), exit 1 = already emitted for this key, exit 2 = usage error OR an unexpected
    failure while recording (lock/I/O). 2 is deliberately overloaded with "usage error"
    rather than given a new number of its own: a caller that treats any nonzero exit as "do
    not print the pointer" already handles it correctly either way, and the one distinction
    that matters -- 1 means "already said, all is well" -- stays unambiguous. A crash must
    never surface as 1: a caller told "already emitted" says nothing further and moves on,
    so a masked crash would silently and permanently suppress the pointer with nothing to
    show for it.

    Scope is the KEY ALONE, not a session: there is no notion of "session" that outlives one
    skill invocation (`{session_id}` in `step-00-activate.md` is bound fresh per invocation
    and no caller of `notice` is ever a dispatched subagent that could inherit one), so a
    per-session key would never repeat and this would fire every single invocation -- exactly
    the nagging it exists to prevent. A key is recorded at most once, ever, per project: once
    a key has fired, it never fires again for that `--state-root`, which is correct for an
    advisory whose content is static ("this exists, configure it if you want") and whose
    trigger condition (`modules.l3io-pm` being absent) is itself a valid permanent state, not
    a transient one to keep re-flagging.

    An absent or unparseable notices file means nothing has been emitted yet -- a notice is
    advisory only, so a damaged file must never block the caller's real work; it is simply
    treated as empty and rewritten clean on this call. That tolerance covers a bad READ only:
    a failure while actually recording (the lock, or the write itself) is a real failure and
    is reported as one, not folded into "already emitted" or silently swallowed as success.
    """
    key = (args.key or "").strip()
    if not key:
        sys.stderr.write("notice: --key must be non-empty\n")
        return 2
    path = notices_path(args.state_root)
    try:
        os.makedirs(args.state_root, exist_ok=True)
        with core.notices_lock(args.state_root):
            # _load returns (yaml_instance, data) -- data is None when the file is absent
            # or fails to parse the way _load's caller expects. Reuse the returned YAML
            # instance for the dump so round-trip settings (width, indent, quote style)
            # match.
            try:
                y, data = core._load(path)
            except Exception:  # noqa: BLE001 -- a notice ledger that cannot be read is rebuilt, never fatal
                y, data = _yaml(), None
            keys = data.get("keys") if isinstance(data, dict) else None
            if not isinstance(keys, list):
                keys = []
            if key in keys:
                return 1
            keys.append(key)
            core._atomic_dump(y, {"keys": keys}, path)
    except Exception as e:  # noqa: BLE001 -- recording a notice must never fail the command it advises
        sys.stderr.write(f"notice: could not record the notice at {path}: {e}\n")
        return 2
    return 0


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def _resolve_story_items(state_root, node, story_key, session) -> None:
    """After a story reaches `done`, resolve every key in its `resolves:` as fixed.

    ADR-0003: this never fails set-status. The status save already happened and is
    durable; reporting it as failed would invite a retry or a rollback of finished
    work. Every exception except KeyboardInterrupt -- SystemExit included -- becomes
    a warning, and audit-issues finding 1c catches what was missed. `resolves:` itself
    is hand-editable YAML, so normalising it (a bare scalar counts as one key; anything
    else is a malformed-field warning) happens INSIDE the catch-all too -- a bad shape
    there must warn, never raise out of set-status."""
    raw = node.get("resolves")
    if not raw:
        return
    try:
        if isinstance(raw, str):
            keys = [raw]
        elif isinstance(raw, (list, tuple)):
            keys = [str(k) for k in raw]
        else:
            sys.stderr.write(f"pm-status.py: warning -- {story_key} has a malformed resolves: "
                             f"({raw!r}); nothing resolved. Run /l3io-doctor triage.\n")
            return
        open_path = issues_paths(state_root)[0]
        with issues_lock(open_path):
            store = IssueStore(open_path)
            for k in keys:
                try:
                    kc = canonical_bl_key(k)
                    was_resolved = bool(kc and store.resolved_items(kc))
                    msg = resolve_issue_core(store, k, "fixed", story_key, None,
                                             session, "set-status")
                    # `resolved BL-...` is the spec §2.6 output contract for a NEW
                    # resolution only; a key resolved before (a repeat done) gets `ok`.
                    sys.stdout.write(f"{'ok' if was_resolved else 'resolved'} {msg}\n")
                except PMError as e:
                    sys.stderr.write(f"pm-status.py: warning -- could not resolve {k} "
                                     f"for {story_key}: {e.msg} -- run /l3io-doctor "
                                     f"triage\n")
    except KeyboardInterrupt:
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberate, ADR-0003
        sys.stderr.write(f"pm-status.py: warning -- done hook failed for {story_key}: "
                         f"{e!r}; the status write stands. Run /l3io-doctor triage "
                         f"(audit-issues finding 1c) to finish it.\n")


def cmd_set_status(args) -> int:
    kind = _infer_kind(args)
    valid = {"story": VALID_STORY_STATUS, "sprint": VALID_SPRINT_STATUS, "epic": VALID_EPIC_STATUS}[kind]
    if args.status not in valid:
        _die_usage(f"invalid {kind} status '{args.status}' — expected one of {sorted(valid)}")

    # blocked-lifecycle argument guards (story only -- sprint/epic keep no --reason/--resolution).
    reason = str(getattr(args, "reason", "") or "").strip()
    resolution = str(getattr(args, "resolution", "") or "").strip()
    if kind == "story" and args.status == "blocked" and not reason:
        _die_usage("--status blocked requires --reason \"<why>\" -- a blocked story with no reason "
                   "on record is what this flag exists to prevent")
    if kind != "story" and (reason or resolution):
        _die_usage("--reason and --resolution are story-only flags; sprints and epics compose "
                   "from their children")
    if kind == "story" and args.status != "blocked" and reason:
        _die_usage("--reason is only valid with --status blocked; other transitions have no "
                   "reason field to record")

    # An epic node is written under its epic_node_lock. The event append inside is a leaf
    # lock, and the done hook below (issues_lock) runs only for a story, outside any hold.
    with _epic_write_lock(args, kind):
        y, node, path, label = _load_checked(args.state_root, args, kind)
        prior = str(node.get("status", "")) or None

        # Story transitions are per-pair, not per-target. See VALID_STORY_TRANSITIONS.
        if kind == "story" and prior is not None:
            allowed = VALID_STORY_TRANSITIONS.get(prior, set())
            if args.status not in allowed:
                _die_usage(
                    f"invalid story transition {prior!r} -> {args.status!r}; from {prior!r} "
                    f"allowed: {sorted(allowed) or ['(terminal)']}")
            # blocked -> done is the one transition that requires --resolution: the story
            # resolved by the same event that unblocked it (e.g. spec change removed the need).
            if prior == "blocked" and args.status == "done" and not resolution:
                _die_usage("blocked -> done requires --resolution \"<why the story is done "
                           "rather than resumed>\"; use --status in-progress to resume")

        node["status"] = args.status
        node["updated_at"] = _now_iso()
        if args.title:
            node["title"] = args.title
        if kind == "story":
            leaving_blocked = prior == "blocked" and args.status != "blocked"
            entering_blocked = args.status == "blocked" and prior != "blocked"
            if args.status == "blocked":
                node["blocked_reason"] = reason
            elif leaving_blocked and "blocked_reason" in node:
                # Current node reflects only current state; block history lives in the log.
                del node["blocked_reason"]
            if entering_blocked:
                # completion_evidence.blocks_seen: O(1) counter for closure-side
                # observability. Not used for cohort routing -- see §5 of the design.
                # Not decremented on exit (this counts events, not current state).
                from ruamel.yaml.comments import CommentedMap
                ce = node.get("completion_evidence")
                if not isinstance(ce, dict):
                    ce = CommentedMap()
                    node["completion_evidence"] = ce
                ce["blocks_seen"] = int(ce.get("blocks_seen", 0) or 0) + 1
        else:
            leaving_blocked = entering_blocked = False
        nodes.save_node(y, node, path, getattr(args, "flock", False))

        if not getattr(args, "no_events", False):
            payload = {"ts": _now_iso(), "event": "status",
                       "from": prior, "to": args.status,
                       "session": getattr(args, "session_id", None)}
            payload.update(_event_keys(kind, args))
            append_event(args.state_root, payload)
            if entering_blocked:
                bp = {"ts": _now_iso(), "event": "block_open",
                      "story": args.story, "reason": reason,
                      "session": getattr(args, "session_id", None)}
                append_event(args.state_root, bp)
            if leaving_blocked:
                dur = _block_duration_since_last_open(args.state_root, args.story)
                bc = {"ts": _now_iso(), "event": "block_close",
                      "story": args.story, "duration_hours": dur,
                      "session": getattr(args, "session_id", None)}
                if args.status == "done":
                    bc["resolution"] = resolution
                append_event(args.state_root, bc)

    sys.stdout.write(f"OK set-status {label} -> {args.status}\n")
    if kind == "story" and args.status == "done":
        _resolve_story_items(args.state_root, node, args.story,
                             getattr(args, "session_id", None))
    return 0


EPIC_KEY_RE = re.compile(r"^E\d{3}$")
STORY_KEY_RE = re.compile(r"^E\d{3}-S\d{2}-\d{3}$")
# status-files.md §11: `depends_on` lives on BOTH an epic node (epic keys) and a story node
# (story keys). Reading only that section's first sentence gives the epic case and silently
# loses the story case, which is the shape the migration fixtures actually carry.
DEPENDS_ON_KEY_RE = {"epic": EPIC_KEY_RE, "story": STORY_KEY_RE}


def cmd_set_depends_on(args) -> int:
    """Add or remove keys on a node's `depends_on` list.

    `depends_on` is epic-only and list-shaped (status-files.md §11). `set-field --value` takes a
    single string, so routing a list through it would store "['E001']" as a scalar -- worse than
    not writing it at all, because a later reader takes it for one. That is exactly why the
    migration engine WARNed and skipped this field rather than flattening it.

    All-or-nothing: every key is validated before anything is written, because a half-applied
    dependency list is a worse artefact than an absent one -- l3io-plan topologically sorts
    on it, so a missing edge silently reorders a phase.

    --remove EXISTS BECAUSE ITS ABSENCE FORCED A HAND EDIT. This verb was append-only, and
    `set-field` refuses a list, so the only way to drop a dependency was to open epic.yaml and
    edit it -- which the state contract forbids, and for the reason this whole script exists:
    free-form YAML edits were dropped and malformed under parallel execution. A reorg that
    removes the last story edge justifying `E001 depends_on E003` leaves that declaration
    standing, and phases come from epic-level depends_on, so the two epics keep serialising
    and the reorg's whole purpose goes unrealised. There was no command to recommend.

    REMOVING A STILL-JUSTIFIED DEPENDENCY IS REFUSED. If any story under this node still
    depends on a story under the key being removed, dropping the edge tells the planner the
    two can run concurrently when they cannot. `--force` overrides, because an epic
    dependency can also encode a sequencing decision no story edge expresses ("ship the API
    before the client"), and this script cannot tell those apart -- but it can make the
    difference deliberate.
    """
    from ruamel.yaml.comments import CommentedSeq
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ

    kind = _infer_kind(args)
    if kind not in DEPENDS_ON_KEY_RE:
        _die_usage(f"depends_on lives on an epic or a story node, not a {kind} "
                   f"(status-files.md §11)")
    key_re = DEPENDS_ON_KEY_RE[kind]
    self_key = args.epic if kind == "epic" else args.story

    keys = list(args.add or [])
    drops = list(getattr(args, "remove", None) or [])
    if not keys and not drops:
        _die_usage("set-depends-on needs at least one --add KEY or --remove KEY")
    if keys and drops:
        # Refused rather than ordered. Whichever order were chosen, half the readers of a
        # later command would assume the other, and the two are trivially separable calls.
        _die_usage("--add and --remove in one call is refused: the result would depend on an "
                   "order nobody can see. Run them as two commands")
    for k in keys + drops:
        if not key_re.match(k):
            flag = "--add" if k in keys else "--remove"
            _die_usage(f"{flag} {k!r} is not a {kind} key (expected {key_re.pattern}); "
                       f"nothing written")
    for k in keys:
        if k == self_key:
            _die_usage(f"--add {k!r} is the node itself -- it cannot depend on itself; "
                       f"nothing written")

    # The justification check runs BEFORE the lock, because it reads the whole epic tree and
    # refusing is the common outcome on a mistaken call -- taking a write lock to then refuse
    # would block a concurrent legitimate write for no reason.
    if drops and kind == "epic" and not getattr(args, "force", False):
        # Only keys actually PRESENT can be refused. Removing one that is not there is a
        # no-op, and a no-op must not be blocked by a justification for an edge that is
        # already gone -- a caller acting on a stale read would otherwise get an error for
        # asking for a state the tree is already in.
        _p = nodes.epic_file(args.state_root, canonical_epic_key(self_key))
        _cur = []
        if _p:
            _, _n = load_node(_p)
            if isinstance(_n, dict):
                _cur = [str(e) for e in deps_list(_n, _p)]
        present = [k for k in drops if str(k) in _cur]
        blocked = _justifying_story_edges(args.state_root, self_key, present) if present else []
        if blocked:
            shown = ", ".join(f"{a} -> {b}" for a, b in blocked[:5])
            more = f" (+{len(blocked) - 5} more)" if len(blocked) > 5 else ""
            _die_usage(f"refusing to remove {sorted({b for _a, b in blocked})} from "
                       f"{self_key}: {len(blocked)} story dependency(ies) still cross that "
                       f"boundary — {shown}{more}. Dropping the edge would tell the planner "
                       f"these epics can run concurrently when they cannot. Move the stories "
                       f"first (/l3io-plan reorg), or pass --force if this dependency is a "
                       f"sequencing decision no story edge expresses")

    with _epic_write_lock(args, kind):
        y, node, path, label = _load_checked(args.state_root, args, kind)
        existing = node.get("depends_on")
        if not isinstance(existing, list):
            existing = CommentedSeq()
            node["depends_on"] = existing
        added, removed = [], []
        for k in keys:
            if str(k) not in [str(e) for e in existing]:
                existing.append(SQ(k))
                added.append(k)
        for k in drops:
            # Idempotent, like --add: removing a key that is not there is a no-op, not an
            # error. A caller acting on a stale read should not have to care.
            hits = [e for e in existing if str(e) == str(k)]
            for h in hits:
                existing.remove(h)
            if hits:
                removed.append(k)
        # An emptied list is written as `depends_on: []` rather than dropped, so a reader
        # sees "declared, and empty" exactly as it sees "never declared" -- both mean no
        # dependencies, and every reader here treats a missing key and [] the same way.
        node["updated_at"] = _now_iso()
        nodes.save_node(y, node, path, getattr(args, "flock", False))

    if drops:
        sys.stdout.write(f"OK set-depends-on {label} -= {removed or '(nothing present)'}\n")
    else:
        sys.stdout.write(f"OK set-depends-on {label} += {added or '(nothing new)'}\n")
    return 0


def _justifying_story_edges(state_root: str, epic_key: str, targets: list) -> list:
    """(story, target_epic) for every story edge crossing from epic_key into one of targets.

    What makes an epic-level dependency earned: a story under this epic depending on a story
    under that one. Zero such edges is what `plan-graph.py` reports as
    `unneeded-cross-epic-dependency`, and what makes a removal safe.
    """
    want = {canonical_epic_key(t) for t in targets}
    out = []
    for story_key, path in iter_story_files(state_root, canonical_epic_key(epic_key)):
        _, node = load_node(path)
        if not isinstance(node, dict):
            continue
        for dep in deps_list(node, path):
            try:
                dep_epic, _sp, _n = parse_story_key(str(dep))
            except ValueError:
                continue
            if dep_epic in want:
                out.append((story_key, dep_epic))
    return sorted(out)


def cmd_import_node(args) -> int:

    """Create a state node from a migration record. The counterpart to set-status for a
    node that does not exist yet.

    This is cmd_set_status with ONE step swapped -- ensure_node_path() where set-status
    calls _load_checked() -- because _load_checked exits 3 on a missing node, which is
    correct for set-status and fatal for this verb. set-status itself is untouched: it
    must never create anything.

    Idempotent by SKIP, not by overwrite. A migration retried after a partial run must
    not clobber a node a later step already edited, so an existing file is left exactly
    as it is and reported.
    """
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ

    kind = _infer_kind(args)
    valid = {
        "story": VALID_STORY_STATUS,
        "sprint": VALID_SPRINT_STATUS,
        "epic": VALID_EPIC_STATUS,
    }[kind]
    if args.status not in valid:
        _die_usage(
            f"invalid {kind} status '{args.status}' -- expected one of {sorted(valid)}")

    # blocked_reason gate: a story imported at `status: blocked` must carry a --reason
    # the same way set-status does. Migration sources that carry blocked state (bmad-loop
    # is the shape) preserve the reason on the record; a source that reports blocked but
    # cannot preserve the reason is a broken source, not an acceptable import shape.
    # Sprints and epics don't have `blocked` in their status enum, so the guard is
    # story-only by construction.
    reason = str(getattr(args, "reason", "") or "").strip()
    if kind == "story" and args.status == "blocked" and not reason:
        _die_usage("--status blocked requires --reason \"<why>\" -- a blocked story with no "
                   "reason on record is what this flag exists to prevent")
    if kind != "story" and reason:
        _die_usage("--reason is a story-only flag; sprint/epic status sets have no blocked")
    if kind == "story" and args.status != "blocked" and reason:
        _die_usage("--reason is only valid with --status blocked")

    with _epic_write_lock(args, kind, require_exists=False):
        path, label = ensure_node_path(args.state_root, args, kind, args.status)
        if os.path.exists(path):
            sys.stdout.write(f"SKIP import-node {label} -- already exists\n")
            return 0

        node = {}
        if kind == "epic":
            node["key"] = SQ(args.epic)
            node["title"] = args.title or ""
            node["goal"] = ""
        elif kind == "sprint":
            node["key"] = SQ(args.sprint)
            node["epic"] = SQ(args.epic)
            node["title"] = args.title or ""
        else:
            epic_key, sprint_key, _ = parse_story_key(args.story)
            node["key"] = SQ(args.story)
            node["epic"] = SQ(epic_key)
            node["sprint"] = SQ(sprint_key)
            node["title"] = args.title or ""
            node["classification"] = args.classification or "unknown"

        node["status"] = args.status
        node["updated_at"] = _now_iso()
        if args.origin:
            node["origin"] = args.origin
            node["origin_note"] = args.origin_note or ""
        if kind == "story" and args.status == "blocked":
            node["blocked_reason"] = reason
            # completion_evidence.blocks_seen is a counter of OUR events, not the
            # source's history -- import-node predates our history for a migrated node,
            # so the counter starts at 0. A subsequent set-status --status blocked would
            # bump it. Not adding it here.

        nodes.save_node(_yaml(), node, path, getattr(args, "flock", False))

        if not getattr(args, "no_events", False):
            payload = {
                "ts": _now_iso(), "event": "import", "from": None, "to": args.status,
                "session": getattr(args, "session_id", None),
            }
            payload.update(_event_keys(kind, args))
            append_event(args.state_root, payload)
            # For a story imported at blocked, emit a paired block_open so a future
            # set-status transitioning off blocked can derive duration the same way
            # a set-status-created block does. Without this, _block_duration_since_
            # last_open would return None and block_close would land without duration.
            if kind == "story" and args.status == "blocked":
                bp = {"ts": _now_iso(), "event": "block_open",
                      "story": args.story, "reason": reason,
                      "session": getattr(args, "session_id", None)}
                append_event(args.state_root, bp)

    sys.stdout.write(f"OK import-node {label} -> {args.status}\n")
    return 0


def cmd_sync_story_doc(args) -> int:
    """Write `status:` into the story markdown's frontmatter.

    The state YAML is the machine's truth; this file is the human's. They have
    never agreed -- a production audit found 73 of 73 stories divergent, every
    one of them in the same direction, which is an unimplemented write rather
    than drift.

    This NEVER fails its caller. It runs after a set-status that has already
    succeeded, and a documentation write must not be able to strand a state
    transition that is already durable.
    """
    if args.status not in VALID_STORY_STATUS:
        sys.stderr.write(f"ERROR unknown story status {args.status!r}; "
                         f"expected one of {', '.join(sorted(VALID_STORY_STATUS))}\n")
        return 2
    try:
        path = story_doc_path(args.artifacts_root, args.story)
    except ValueError as exc:
        sys.stderr.write(f"ERROR {exc}\n")
        return 2
    if not os.path.exists(path):
        sys.stderr.write(f"WARN no story file at {path} — state was written, "
                         f"document not updated\n")
        return 0

    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---\n"):
        sys.stderr.write(f"WARN {path} has no YAML frontmatter — nothing to update\n")
        return 0
    end = text.find("\n---", 3)
    if end == -1:
        sys.stderr.write(f"WARN {path} has an unterminated frontmatter block\n")
        return 0
    head, body = text[4:end + 1], text[end + 4:]

    # ruamel round-trip: preserves key order and comments. Never split on '---'
    # by hand -- a body line of dashes is legal markdown and would corrupt it.
    from ruamel.yaml.comments import CommentedMap
    yaml = _yaml()
    try:
        meta = yaml.load(head)
    except Exception:                                    # noqa: BLE001
        # Deliberately broad. This runs after a set-status that already
        # succeeded, and no parse failure is worth stranding a durable state
        # transition over. The warning is the signal; the exit code is not.
        sys.stderr.write(f"WARN {path} frontmatter does not parse as YAML — "
                         f"state was written, document not updated\n")
        return 0
    if meta is None:
        meta = CommentedMap()
    if not hasattr(meta, "get"):
        sys.stderr.write(f"WARN {path} frontmatter is not a mapping — "
                         f"state was written, document not updated\n")
        return 0
    if meta.get("status") == args.status:
        if not args.quiet:
            sys.stdout.write(f"OK {args.story} document already {args.status}\n")
        return 0
    meta["status"] = args.status
    buf = io.StringIO()
    yaml.dump(meta, buf)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\n" + buf.getvalue() + "---" + body)
    if not args.quiet:
        sys.stdout.write(f"OK {args.story} document -> {args.status}\n")
    return 0


def cmd_story_doc_init(args) -> int:
    def run():
        result = init_story_doc(args.state_root, args.artifacts_root, args.story)
        sys.stdout.write(f"OK story-doc-init {args.story} {result} -> "
                         f"{story_doc_path(args.artifacts_root, args.story)}\n")
        return 0
    return _run_core(run)


def cmd_set_lock(args) -> int:
    """Claim the epic ownership lock. Exit 0 on success (claim / re-claim / takeover);
    exit 5 (matching cmd_check_lock's "locked" code) when a foreign lock is live or
    unreadable, in which case the file is left untouched.

    The whole read-existing-lock -> decide -> write-claim cycle runs under
    `epic_node_lock` -- see its docstring for why a bare read-then-write here would be
    the same check-then-act race this function exists to close.
    """
    from ruamel.yaml.comments import CommentedMap
    _epic_path_or_die(args)                     # exit 3 before any lock file is created
    with epic_node_lock(args.state_root, args.epic):
        path = _epic_path_or_die(args)          # again: a move may have landed meanwhile
        y, data = load_node(path)
        if data is None:
            _die_notfound(f"epic {args.epic} file is empty")

        takeover_note = ""
        existing = data.get("_lock")
        if existing is not None:
            if not isinstance(existing, dict):
                sys.stdout.write(
                    f"LOCKED epic {args.epic}: existing _lock is malformed (not a "
                    f"mapping) — a lock that cannot be read is not a lock that may "
                    f"be stolen; refusing to claim\n")
                return 5
            holder = str(existing.get("session_id", ""))
            if holder != args.session_id:
                if "claimed_at" not in existing:
                    sys.stdout.write(
                        f"LOCKED epic {args.epic}: existing _lock held by {holder!r} "
                        f"has no claimed_at — refusing to claim\n")
                    return 5
                claimed = _parse_iso(existing.get("claimed_at"))
                if claimed is None:
                    sys.stdout.write(
                        f"LOCKED epic {args.epic}: existing _lock held by {holder!r} "
                        f"has an unparseable claimed_at "
                        f"({existing.get('claimed_at')!r}) — refusing to claim\n")
                    return 5
                ttl = int(existing.get("ttl_minutes", 30))
                age_minutes = _lock_age_minutes(claimed)
                if age_minutes <= ttl:
                    remaining = ttl - age_minutes
                    sys.stdout.write(
                        f"LOCKED epic {args.epic} held by {holder} "
                        f"({remaining:.1f}m remaining of {ttl}m ttl)\n")
                    return 5
                takeover_note = (f" (took over stale lock from {holder}, "
                                  f"age={age_minutes:.1f}m > ttl={ttl}m)")
            # else: same session — re-claim below, refreshing claimed_at. A retry
            # by the owner must not deadlock or refuse against its own lock.

        lock = CommentedMap()
        lock["session_id"] = args.session_id
        lock["claimed_at"] = _now_iso()
        lock["ttl_minutes"] = args.ttl_minutes
        data["_lock"] = lock
        # _lock must appear first — rebuild with _lock at top
        ordered = CommentedMap()
        ordered["_lock"] = lock
        for k, v in data.items():
            if k != "_lock":
                ordered[k] = v
        core._atomic_dump(y, ordered, path)
        sys.stdout.write(
            f"OK set-lock epic {args.epic} session={args.session_id} "
            f"ttl={args.ttl_minutes}m{takeover_note}\n")
    return 0


def cmd_clear_lock(args) -> int:
    """Remove the epic's `_lock`. The read-delete-write runs under epic_node_lock, like every
    epic.yaml write: without it, a concurrent promote-issue roll-up (which saves the whole
    epic node under that lock) could land after this write and restore the lock it removed."""
    absent = f"OK clear-lock epic {args.epic} (epic/file absent — no-op)\n"
    if nodes.epic_file(args.state_root, args.epic) is None:
        sys.stdout.write(absent)                # no lock file for an absent epic
        return 0
    with epic_node_lock(args.state_root, args.epic):
        path = nodes.epic_file(args.state_root, args.epic)     # again: a move may have landed
        if path is None:
            sys.stdout.write(absent)
            return 0
        y, data = load_node(path)
        if data is None:
            sys.stdout.write(f"OK clear-lock epic {args.epic} (file empty — no-op)\n")
            return 0
        if "_lock" not in data:
            sys.stdout.write(f"OK clear-lock epic {args.epic} (no _lock present — no-op)\n")
            return 0
        del data["_lock"]
        core._atomic_dump(y, data, path)
    sys.stdout.write(f"OK clear-lock epic {args.epic}\n")
    return 0


def cmd_check_lock(args) -> int:
    """Exit 0 if epic is free to claim; exit 5 if held by another session within TTL.

    Timestamp parsing and age arithmetic go through `_parse_iso`/`_lock_age_minutes`
    -- the same helpers `cmd_set_lock` uses -- so the two TTL comparisons cannot drift
    apart into two independently-wrong implementations. The verdict itself lives in
    `_check_lock_verdict`, which promote-issue shares.
    """
    path = nodes.epic_file(args.state_root, args.epic)
    if path is None:
        sys.stdout.write("FREE\n")
        return 0
    _y, data = load_node(path)
    if data is None or "_lock" not in data:
        sys.stdout.write("FREE\n")
        return 0
    code, line = _check_lock_verdict(data["_lock"], args.session_id)
    sys.stdout.write(line + "\n")
    return code


def _maybe_set(d, key: str, val, coerce):
    if val is not None:
        try:
            d[key] = coerce(val)
        except (ValueError, TypeError):
            d[key] = val


def cmd_set_estimate(args) -> int:
    # Rejected before anything else is touched: cost is derived from tokens x
    # rates (cmd_estimate_story / cmd_estimate_rollup), never accepted as
    # direct input. --cost, --cost-low, and --cost-high stay declared (with
    # help=argparse.SUPPRESS) purely so this is a clear usage error instead of
    # an argparse "unrecognized arguments" one.
    if getattr(args, "cost", None) is not None or getattr(args, "cost_low", None) is not None \
            or getattr(args, "cost_high", None) is not None:
        _die_usage("cost is derived from tokens x rates and cannot be set directly — "
                   "fix the token counts or modules.l3io-pm.token_rates instead")

    kind = _infer_kind(args)
    with _epic_write_lock(args, kind):
        return _set_estimate(args, kind)


def _set_estimate(args, kind) -> int:
    """cmd_set_estimate's body; the caller holds the epic lock for an epic node."""
    y, node, path, label = _load_checked(args.state_root, args, kind)

    from ruamel.yaml.comments import CommentedMap
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est

    if kind == "story":
        # Stories: single values (not ranges)
        _maybe_set(est, "man_hours", args.man_hours, float)
        _maybe_set(est, "hitl_hours", args.hitl_hours, float)
        _maybe_set(est, "elapsed_hours", args.elapsed_hours, float)
        _maybe_set(est, "tokens_k", args.tokens_k_min, int)
    else:
        # Sprints and epics: low/high ranges
        _maybe_set(est, "man_hours_low", args.man_hours_low, float)
        _maybe_set(est, "man_hours_high", args.man_hours_high, float)
        _maybe_set(est, "hitl_hours_low", args.hitl_hours_low, float)
        _maybe_set(est, "hitl_hours_high", args.hitl_hours_high, float)
        _maybe_set(est, "elapsed_hours_low", args.elapsed_hours_low, float)
        _maybe_set(est, "elapsed_hours_high", args.elapsed_hours_high, float)
        _maybe_set(est, "tokens_k_min", args.tokens_k_min, int)
        _maybe_set(est, "tokens_k_max", args.tokens_k_max, int)

    # Calibration factors: applied to get from base values to the estimate
    _maybe_set(est, "fix_factor", getattr(args, "fix_factor", None), float)
    _maybe_set(est, "scope_ratio", getattr(args, "scope_ratio", None), float)

    # Confidence: explicit arg wins; else derive from completeness
    if args.confidence:
        est["confidence"] = args.confidence
    elif "confidence" not in est:
        # No cost/cost_low/cost_high in EITHER list: set-estimate never writes
        # any of them (cost is derived, not settable — see the rejection above),
        # so requiring one would make the estimate permanently "low" confidence.
        # The story list used to name `cost`, which set-estimate rejects at the
        # top of this function and can therefore never satisfy — so every
        # hand-written story estimate came out `low` no matter how complete it
        # was, and the derivation could only ever report one of its two values.
        range_keys = ["man_hours_low", "man_hours_high", "hitl_hours_low", "hitl_hours_high",
                      "elapsed_hours_low", "elapsed_hours_high",
                      "tokens_k_min", "tokens_k_max"]
        story_keys = ["man_hours", "hitl_hours", "elapsed_hours", "tokens_k"]
        check = story_keys if kind == "story" else range_keys
        est["confidence"] = "medium" if all(k in est for k in check) else "low"

    nodes.save_node(y, node, path, getattr(args, "flock", False))
    sys.stdout.write(f"OK set-estimate {label}\n")
    return 0


def cmd_set_field(args) -> int:
    """Set an arbitrary nested field at a dot-path within a node.
    --story KEY | --epic ID [--sprint ID] selects the node.
    --field: dot-path within the node, e.g. 'retrospective.summary', 'closed.date'
    --value: string value to set
    """
    # The field itself OR any sub-path of it: an exact-match lookup let `resolves.x` walk
    # into the node and save a mapping under resolves:, and `status.x` crash mid-walk.
    derived = next((d for d in DERIVED_NODE_FIELDS
                    if args.field == d or args.field.startswith(d + ".")), None)
    if derived is not None:
        inside = "" if derived == args.field else f" (it is inside {derived})"
        _die_usage(f"--field {args.field} is not directly writable{inside}: "
                   f"{DERIVED_NODE_FIELDS[derived]}")
    # ...or a PARENT of one: `completion_evidence` would replace the whole mapping and
    # discard the test_runs that tests_passing is derived from.
    contained = next((d for d in sorted(DERIVED_NODE_FIELDS)
                      if d.startswith(args.field + ".")), None)
    if contained is not None:
        _die_usage(f"--field {args.field} is not directly writable (it contains {contained}): "
                   f"{DERIVED_NODE_FIELDS[contained]}")

    kind = _infer_kind(args)
    _check_lane_value(args, kind)
    with _epic_write_lock(args, kind):
        return _set_field(args, kind)


# A lane is a NUMBER, 1..999. Not a style choice -- it is what makes "never a person"
# mechanical instead of hopeful. A word-shaped token cannot be screened: `sarah` and
# `backend` are the same shape, so any regex permitting the second permits the first, and a
# list of names to reject would be both brittle and culturally parochial. Numbering closes
# the question by construction, and it matches the rest of the design: `lane_count` is a
# count, and a lane is a slot in `1..lane_count`.
_LANE_RE = re.compile(r"^[1-9][0-9]{0,2}$")


def _check_lane_value(args, kind) -> None:
    """Guard the `lane` field: epic-only, and never a person's name.

    WHY THE FIELD IS `lane` AND NOT `owner`. `owner` attracts names — somebody commits
    `owner: sarah` and the generic concept erodes by default rather than by decision. A lane
    is a slot in a partition; who fills it lives in the gitignored user layer, so a human's
    name cannot reach the repository at all. The vocabulary is the guardrail, and this
    function is what stops the vocabulary being the ONLY guardrail.

    EPIC-ONLY, because `1 epic = 1 lane` is the invariant everything else rests on: sprints
    and stories live under their epic's directory and inherit its lane by construction. A
    story carrying its own lane would make the lane graph a different graph from the epic
    graph, and every cross-lane question would need its own traversal instead of relabelling
    the epic one.
    """
    if getattr(args, "field", None) != "lane":
        return
    if kind != "epic":
        _die_usage(f"`lane` lives on an epic node, not a {kind}. Sprints and stories inherit "
                   f"their epic's lane from the directory they are in — one epic is one lane, "
                   f"and a story with its own lane would break that")
    value = str(getattr(args, "value", "") or "")
    if not _LANE_RE.match(value):
        _die_usage(f"lane {value!r} is not a lane number. A lane is a SLOT in a partition — "
                   f"1, 2, 3 — never a person: who works a lane is recorded in the gitignored "
                   f"user config, so a name cannot reach the repository. Numbering is what "
                   f"makes that mechanical: a word-shaped token cannot be screened, because "
                   f"`backend` and `sarah` are the same shape. Expected 1-999")


def _set_field(args, kind) -> int:
    """cmd_set_field's body; the caller holds the epic lock for an epic node."""
    y, node, path, label = _load_checked(args.state_root, args, kind)

    field_parts = args.field.split(".")
    target = node
    for part in field_parts[:-1]:
        if target.get(part) is None:
            from ruamel.yaml.comments import CommentedMap
            target[part] = CommentedMap()
        target = target[part]
    value = args.value
    if args.field in NUMERIC_NODE_FIELDS:
        n = _iter_count(value) if args.field.endswith("fix_iterations") else None
        if args.field.endswith("fix_iterations"):
            if n is None:
                _die_usage(
                    f"--field {args.field} needs a non-negative whole number, got {value!r}. "
                    "Stored as text this silently becomes provenance=backout on a story that "
                    "needed no rework, and the clean fix cohort never fills. If the value came "
                    "from a template placeholder, it was not substituted.")
            value = n
        elif _is_number(value):
            value = _coerce(field_parts[-1], value)
    elif args.field in BOOL_NODE_FIELDS:
        low = str(value).strip().lower()
        if low in ("true", "yes", "1"):
            value = True
        elif low in ("false", "no", "0"):
            value = False
    target[field_parts[-1]] = value

    nodes.save_node(y, node, path, getattr(args, "flock", False))
    sys.stdout.write(f"OK set-field {label} {args.field}={args.value!r}\n")
    return 0


def cmd_add_test_run(args) -> int:
    """Append one executed test command and derive tests_passing from the set.

    The boolean it replaces recorded that the agent was satisfied, not that
    anything passed: a story shipped `tests_passing: true` having broken a
    suite it never ran, and the break surfaced two stories later. A command
    and an exit code are falsifiable by anyone who re-runs them.

    DERIVATION RULE: `tests_passing` is `all(exit_code == 0)` over the **last
    run of each distinct command**, not over every run ever appended. Agents
    are told to record every command they ran, failures included, so the normal
    fix-then-rerun cycle -- `pytest` -> 1, fix, `pytest` -> 0 -- appends both.
    Folding history into the boolean would leave that story permanently
    `tests_passing: false` and punish exactly the behavior the record wants.
    The full history stays in `test_runs`: that is the evidence, and dropping
    the failed run to make the boolean come out right would destroy it. A
    command whose last run is non-zero still derives False, however many green
    runs preceded it.
    """
    if args.exit_code < 0:
        sys.stderr.write("ERROR --exit-code must be >= 0\n")
        return 2
    path = story_file(args.state_root, args.story)
    if path is None:
        _die_notfound(f"story {args.story}")
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"story {args.story} — file {path} is empty")
    from ruamel.yaml.comments import CommentedMap
    ce = node.setdefault("completion_evidence", CommentedMap())
    runs = ce.setdefault("test_runs", [])
    entry = CommentedMap()
    entry["command"] = args.command
    entry["exit_code"] = int(args.exit_code)
    runs.append(entry)
    # Last run wins per distinct command (see the docstring's DERIVATION RULE).
    # dict keeps insertion order and a re-run overwrites in place, so this is the
    # latest verdict for each command, in the order the commands first appeared.
    latest = {}
    for r in runs:
        if not isinstance(r, dict):
            # A hand-edited list can hold a scalar; an unreadable entry must never
            # derive a pass, and it has no command to key on -- give it its own slot.
            latest[("__malformed__", id(r))] = r
            continue
        latest[r.get("command")] = r
    ce["tests_passing"] = all(
        _exit_code_or_fail(r.get("exit_code") if isinstance(r, dict) else None) == 0
        for r in latest.values()
    )
    nodes.save_node(y, node, path, use_flock=True)
    sys.stdout.write(f"OK {args.story} test run recorded "
                     f"({args.command} -> {args.exit_code}); "
                     f"tests_passing={ce['tests_passing']}\n")
    return 0


_BL_KEY_RE = re.compile(r"^BL-E(\d+)-(\d+)$")


# --------------------------------------------------------------------------- #
# Issue store -- issues.yaml (open items) + issues-resolved.yaml (resolved).
# Spec: docs/superpowers/specs/2026-09-10-issue-lifecycle-design.md; ADR-0002.
# --------------------------------------------------------------------------- #
ISSUES_FILENAME = "issues.yaml"
RESOLVED_FILENAME = "issues-resolved.yaml"
OPEN_ISSUE_STATUSES = ("backlog", "scheduled")
# Statuses the PRE-3.0 schema used for an open item, mapped to their current equivalent.
# `deferred` was that schema's resting state for a deliberate deferral -- open, unscheduled --
# which is exactly `backlog` now. A project upgrading with a legacy backlog otherwise gets one
# undifferentiated 1f per item (453 on a real one) whose repair text is "report only", so
# triage reports everything and can act on nothing. Mapping to a RESOLVED state instead would
# be a judgement, not a migration, so it is deliberately not done here.
LEGACY_OPEN_STATUSES = {"deferred": "backlog"}


RESOLUTIONS = ("fixed", "wontfix", "duplicate", "obsolete", "deferred")
# A backlog item's kind. `defect` is the default and is never written, so every file written
# before kinds existed still reads as all defects. The spec kinds come from spec-align.py's
# spec sync (docs/adr/0004-agents-edit-architecture-specs.md): they are confirmed or
# rejected in doctor triage, never promoted to a story.
ISSUE_KINDS = ("defect", "spec-change", "spec-proposal")
SPEC_ISSUE_KINDS = ISSUE_KINDS[1:]
SEVERITY_RANK = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _int_or_none(v):
    if isinstance(v, bool):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def canonical_bl_key(key):
    """'BL-E1-2' -> 'BL-E001-002'. None when the key cannot be written canonically."""
    m = _BL_KEY_RE.match(str(key).strip())
    if not m:
        return None
    epic, n = int(m.group(1)), int(m.group(2))
    if epic > 999 or n > 999 or n < 1:
        return None
    return f"BL-E{epic:03d}-{n:03d}"


def issues_paths(state_root: str) -> tuple:
    return (os.path.join(state_root, ISSUES_FILENAME),
            os.path.join(state_root, RESOLVED_FILENAME))


def _remove_identity(lst, obj) -> None:
    """Remove `obj` itself -- not an equal mapping -- from a list."""
    for i, x in enumerate(lst):
        if x is obj:
            del lst[i]
            return


class IssueStore:
    """Both issue files, loaded together. The caller holds issues_lock(open_path)
    across the whole load -> mutate -> save cycle; the resolved file lives beside
    the open one, so one lock covers both."""

    def __init__(self, open_path: str):
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        self.open_path = open_path
        self.state_root = os.path.dirname(os.path.abspath(open_path))
        self.resolved_path = os.path.join(self.state_root, RESOLVED_FILENAME)
        self.y, self.open = core._load(open_path)
        self.yr, self.res = core._load(self.resolved_path)
        if self.open is None:
            self.open = CommentedMap()
        if self.open.get("backlog") is None:
            self.open["backlog"] = CommentedSeq()
        if self.res is None:
            self.res = CommentedMap()
        if self.res.get("resolved") is None:
            self.res["resolved"] = CommentedSeq()
        for name, lst, path in (("backlog", self.open["backlog"], open_path),
                                ("resolved", self.res["resolved"], self.resolved_path)):
            if not isinstance(lst, list):
                raise PMError(2, f"{path} has a malformed '{name}' field (expected a list, "
                                 f"got {type(lst).__name__}: {lst!r}); refusing to write -- "
                                 f"a list that cannot say what is recorded cannot be trusted "
                                 f"to receive more. Fix or restore it by hand, then retry.")

    # Annotated so reading these as methods -- `store.backlog()` -- is a type error rather
    # than a runtime TypeError. The annotations only bind because of the TYPE_CHECKING
    # import at the top of this file; without it they resolve to `Any` and check nothing.
    @property
    def backlog(self) -> CommentedSeq:
        return self.open["backlog"]

    @property
    def resolved(self) -> CommentedSeq:
        return self.res["resolved"]

    @staticmethod
    def _matching(lst, key):
        return [i for i in lst if isinstance(i, dict) and str(i.get("key", "")) == key]

    def open_items(self, key):
        return self._matching(self.backlog, key)

    def resolved_items(self, key):
        return self._matching(self.resolved, key)

    def single_open(self, key):
        """The one open item with this key, or None. PMError(2) when the key appears
        more than once -- no verb may act on an ambiguous key (audit-issues 1i)."""
        opens = self.open_items(key)
        if len(opens) > 1:
            raise PMError(2, f"{key} appears {len(opens)} times in {self.open_path} -- "
                             f"resolve it by hand (audit-issues finding 1i)")
        return opens[0] if opens else None

    def highest_suffix(self, epic_norm: str) -> int:
        highest = 0
        for item in list(self.backlog) + list(self.resolved):
            if not isinstance(item, dict):
                continue
            m = _BL_KEY_RE.match(str(item.get("key", "")))
            if m and _norm_num(m.group(1), 3) == epic_norm:
                highest = max(highest, int(m.group(2)))
        return highest

    def stored_next(self, epic_norm: str):
        nxt = self.open.get("next")
        if not isinstance(nxt, dict) or epic_norm not in nxt:
            return None
        n = _int_or_none(nxt.get(epic_norm))
        if n is None:
            sys.stderr.write(f"pm-status.py: warning -- next[{epic_norm!r}] = "
                             f"{nxt.get(epic_norm)!r} is not an integer; ignoring it\n")
        return n

    def _next_map(self):
        from ruamel.yaml.comments import CommentedMap
        nxt = self.open.get("next")
        if nxt is not None and not isinstance(nxt, dict):
            sys.stderr.write(f"pm-status.py: warning -- {self.open_path} has a malformed "
                             f"'next' ({nxt!r}); rebuilding it from the highest keys\n")
            nxt = None
        if nxt is None:
            nxt = CommentedMap()
            if "next" in self.open:
                self.open["next"] = nxt
            else:
                self.open.insert(0, "next", nxt)
        return nxt

    def raise_next(self, epic_norm: str, at_least: int) -> None:
        """`next` never decreases: store max(what is stored, at_least)."""
        stored = self.stored_next(epic_norm)
        self._next_map()[epic_norm] = max(stored or 0, at_least)

    def allocate(self, epic_norm: str) -> str:
        n = max(self.stored_next(epic_norm) or 1, self.highest_suffix(epic_norm) + 1)
        if n > 999:
            raise PMError(2, f"epic {epic_norm} has used every backlog key: BL-E{epic_norm}-999 "
                             f"is the last a three-digit suffix can name, and keys are never "
                             f"reused -- nothing written")
        self.raise_next(epic_norm, n + 1)
        return f"BL-E{epic_norm}-{n:03d}"

    def save_open(self) -> None:
        core._atomic_dump(self.y, self.open, self.open_path)

    def save_resolved(self) -> None:
        core._atomic_dump(self.yr, self.res, self.resolved_path)


def _issue_event(state_root, event, item, session=None, cause="cli", **fields) -> None:
    payload = {"ts": _now_iso(), "event": event, "key": str(item.get("key", "")),
               "epic": str(item.get("epic", "")), "session": session, "cause": cause}
    payload.update(fields)
    append_event(state_root, payload)


def _norm_issue_title(title) -> str:
    """Strip, collapse internal whitespace, and casefold -- for duplicate MATCHING
    only. The stored title is never rewritten to this normalized form."""
    return " ".join(str(title).split()).casefold()


SOURCE_PHASE_RE = re.compile(r"^[A-Za-z][\w-]*$")


def resolve_source(args):
    """Return (source_string, phase, ref) for an append-issue call.

    `--source` is free text stored verbatim and validated nowhere, and it is the only link an
    issue has back to the artifact that raised it. A real backlog grew 100+ distinct shapes,
    and audit-backlog.py accumulated five regexes trying to read them -- every one of which
    has been wrong about some shape. This package's own step-03-dev-loop.md even emits a
    source its own primary reader rejects, surviving only because an earlier regex uses
    .search rather than .match.

    So the structured form DERIVES the string rather than sitting beside it: a caller cannot
    produce a phase/ref pair that disagrees with the text, because it does not write the text.
    Validation here guarantees the result parses as `{phase} ({ref})`, which is the invariant
    the readers depend on.

    `--source` stays accepted and stored byte-for-byte: _content_matches compares it exactly
    as one of four duplicate-detection keys, deliberately, because over-matching loses a real
    finding.
    """
    raw = getattr(args, "source", None)
    phase = getattr(args, "source_phase", None)
    ref = getattr(args, "source_ref", None)
    note = getattr(args, "source_note", "") or ""

    if raw and phase:
        _die_usage("--source and --source-phase are alternatives -- pass one, not both")
    if not raw and not phase:
        _die_usage("append-issue needs --source, or --source-phase with --source-ref")
    if note and not phase:
        _die_usage("--source-note applies only to --source-phase")
    if raw:
        return raw, None, None

    if not ref:
        _die_usage("--source-phase requires --source-ref")
    if not SOURCE_PHASE_RE.match(phase):
        _die_usage(f"--source-phase {phase!r} must match {SOURCE_PHASE_RE.pattern} -- the "
                   f"derived source has to parse as '{{phase}} ({{ref}})', which a space or a "
                   f"punctuation character breaks")
    if "(" in ref or ")" in ref:
        _die_usage(f"--source-ref {ref!r} must not contain parentheses -- they delimit the ref "
                   f"in the derived source string")

    derived = f"{phase} ({ref})" + (f" — {note}" if note else "")
    return derived, phase, ref


def _content_matches(item, epic_norm: str, sprint_norm: str, source: str, norm_title: str) -> bool:

    return (isinstance(item, dict)
            and _norm_num(item.get("epic", ""), 3) == epic_norm
            and _norm_num(item.get("sprint", "") or "", 2) == sprint_norm
            and str(item.get("source", "")) == source
            and _norm_issue_title(item.get("title", "")) == norm_title)


def _find_issue_by_content(backlog, epic_norm: str, sprint_norm: str, source: str, norm_title: str):
    """Match on all four of normalized title + epic + sprint + source, deliberately.
    Over-matching (e.g. title alone) loses a real finding; under-matching leaves
    noise. Losing data is the worse failure, so this only catches near-certain
    repeats -- a re-run of the same story re-deferring the same finding."""
    for item in backlog:
        if _content_matches(item, epic_norm, sprint_norm, source, norm_title):
            return item
    return None


def _last_resolved_match(resolved, epic_norm, sprint_norm, source, norm_title):
    """The NEWEST resolved item with the same content. issues-resolved.yaml is appended
    in resolution order, so the last match is the newest."""
    hits = [r for r in resolved if _content_matches(r, epic_norm, sprint_norm, source, norm_title)]
    return hits[-1] if hits else None


def cmd_append_issue(args) -> int:
    """Append a BL item to the backlog list in state/issues.yaml.

    The whole load -> allocate-key -> dedupe-check -> mutate -> save cycle runs
    under one exclusive lock (`issues_lock`): `issues.yaml` is a shared append
    target across every epic and every parallel subagent, and locking only the
    write (as this used to) lets two concurrent callers read the same pre-write
    backlog, allocate the same next number, and have the second save silently
    drop the first's item -- the same collision class production ADR numbers
    hit (three parallel agents, one directory listing, two agents each picking
    0013 and 0014).

    `--key` is optional. Omitted, the next number for `--epic` is allocated
    here (never by the caller -- nothing bound `{nnn}` anywhere, which is
    exactly how two callers used to invent the same one). Given, and it
    already names an existing item, that is refused (exit 2) rather than
    silently renumbered: a caller naming a key means it. Either way, a content
    duplicate (same normalized title + epic + sprint + source) is skipped --
    the caller's desired end state, "this finding is recorded", already holds
    -- unless `--allow-duplicate` forces a second entry.

    Keys come from `IssueStore.allocate`: `max(next[epic], highest suffix in
    either issue file + 1)`, so a deleted or resolved item's key is never
    handed out again.
    """
    return _run_core(lambda: _append_issue(args))


def _issues_open_path(args) -> str:
    """The open issues file from --state-root, or from --file (compatibility)."""
    sr = getattr(args, "state_root", "") or ""
    f = getattr(args, "file", "") or ""
    if sr:
        p = issues_paths(sr)[0]
        if f and os.path.abspath(f) != os.path.abspath(p):
            raise PMError(2, f"append-issue: --file {f} is not {p} -- pass --state-root "
                             f"alone (--file is kept only for compatibility)")
        return p
    if f:
        return f
    raise PMError(2, "append-issue: pass --state-root (or, for compatibility, --file)")


def _append_issue(args) -> int:
    from ruamel.yaml.comments import CommentedMap
    # Resolved before the lock: a usage error should not hold issues.yaml while it exits.
    source_str, source_phase, source_ref = resolve_source(args)
    open_path = _issues_open_path(args)
    epic_norm = _norm_num(args.epic, 3)
    sprint_norm = _norm_num(args.sprint, 2) if args.sprint else ""
    norm_title = _norm_issue_title(args.title)
    kind = getattr(args, "kind", None) or "defect"
    ref = (getattr(args, "ref", None) or "").strip()
    if kind in SPEC_ISSUE_KINDS and not ref:
        raise PMError(2, f"append-issue: --kind {kind} needs --ref (the docs(spec) commit SHA, "
                         f"or the proposal file's path)")
    if kind == "spec-change" and not _SHA_RE.match(ref):
        raise PMError(2, f"append-issue: --kind spec-change needs --ref to be a commit SHA, "
                         f"not {ref!r}")
    explicit = None
    if args.key:
        explicit = canonical_bl_key(args.key)
        if explicit is None:
            raise PMError(2, f"append-issue: --key {args.key!r} is not a backlog key "
                             f"(expected BL-E{{nnn}}-{{nnn}})")
        if explicit[4:7] != epic_norm:
            raise PMError(2, f"append-issue: --key {explicit} belongs to epic "
                             f"{explicit[4:7]}, not --epic {epic_norm}")
    with issues_lock(open_path, bare_file=not (getattr(args, "state_root", "") or "")):
        store = IssueStore(open_path)
        if explicit is not None:
            clash = store.open_items(explicit) + store.resolved_items(explicit)
            if clash:
                raise PMError(2, f"append-issue: --key {explicit!r} already exists "
                                 f"(title: {clash[0].get('title', '')!r}) -- refusing to "
                                 f"silently assign a different key; pick a key that is not "
                                 f"already taken, or omit --key to auto-allocate the next "
                                 f"one for this epic")
        note = ""
        if not args.allow_duplicate:
            dup = _find_issue_by_content(store.backlog, epic_norm, sprint_norm,
                                         source_str, norm_title)
            if dup is not None:
                sys.stdout.write(
                    f"OK append-issue skipped -- matches existing {dup.get('key', '')} "
                    f"(same title/epic/sprint/source); nothing written. Pass "
                    f"--allow-duplicate to force a second entry.\n")
                return 0
            prior = _last_resolved_match(store.resolved, epic_norm, sprint_norm,
                                         source_str, norm_title)
            if prior is not None:
                res, psev = str(prior.get("resolution", "")), str(prior.get("severity", ""))
                if res == "fixed":
                    note = f" (recurrence of {prior.get('key')})"
                elif SEVERITY_RANK.get(args.severity, 0) > SEVERITY_RANK.get(psev, 0):
                    note = f" (re-raised above {prior.get('key')} {res} at {psev})"
                else:
                    sys.stdout.write(
                        f"OK append-issue skipped -- matches {prior.get('key')} resolved as "
                        f"{res} (severity {psev}); nothing written. Pass --allow-duplicate "
                        f"to force a second entry.\n")
                    return 0
        if explicit is not None:
            key = explicit
            store.raise_next(epic_norm, int(explicit[-3:]) + 1)
        else:
            key = store.allocate(epic_norm)
        item = CommentedMap()
        item["key"] = key
        # epic_norm/sprint_norm, not args.*: both are computed at the top of this function
        # and already trusted for the key, the --key cross-check, dedupe matching and
        # store.allocate(). Storing the caller's spelling instead let one epic appear as
        # '3', '03', '003', 'E3', 'E003' and 'e003' in one file -- all six accepted, all
        # six producing the same correct key.
        item["epic"] = epic_norm
        item["sprint"] = sprint_norm
        item["title"] = args.title
        item["source"] = source_str
        if source_phase:
            item["source_phase"] = source_phase
            item["source_ref"] = source_ref
        item["severity"] = args.severity
        item["status"] = "backlog"
        if kind != "defect":
            item["kind"] = kind
        if ref:
            item["ref"] = ref
        if args.description:
            item["description"] = args.description
        store.backlog.append(item)
        store.save_open()
    _issue_event(store.state_root, "issue_opened", item,
                 getattr(args, "session_id", None), "cli", severity=args.severity)
    sys.stdout.write(f"OK append-issue {key} -> {open_path}{note}\n")
    return 0


_STORY_KEY_RE = re.compile(r"^E\d{3}-S\d{2}-\d{3}$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

# The backlog fields holding a STORY key, and so the fields a re-key invalidates: `story`
# (an open item's scheduling target, copied through to its resolved entry) and `ref` (what
# resolved it). `ref` is overloaded -- on a spec-change/spec-proposal item it is a commit
# SHA or a proposal path -- so every reader must match _STORY_KEY_RE before treating a
# value as a story pointer. `story` is named first in messages: its loss costs more.
STORY_REF_FIELDS = ("story", "ref")


def _validate_resolution_flags(resolution, ref, note) -> None:
    # DEFENSIVE, and unreachable from every current caller -- do not write a fixture for it.
    # argparse constrains --resolution to `choices=list(RESOLUTIONS)`, and the two in-process
    # callers pass the literals "fixed" and "deferred". It guards the next caller, which is a
    # real risk here because resolve_issue_core is invoked internally as well as from the CLI.
    if resolution not in RESOLUTIONS:
        raise PMError(2, f"--resolution must be one of {', '.join(RESOLUTIONS)}")
    if resolution == "fixed":
        if not ref:
            raise PMError(2, "--resolution fixed needs --ref (a story key or a commit SHA)")
        if not (_STORY_KEY_RE.match(ref) or _SHA_RE.match(ref)):
            raise PMError(2, f"--ref {ref!r} is neither a story key (E{{nnn}}-S{{nn}}-{{nnn}}) "
                             f"nor a commit SHA")
    elif resolution == "duplicate":
        if not ref:
            raise PMError(2, "--resolution duplicate needs --ref naming the surviving BL key")
    elif not (note or "").strip():
        raise PMError(2, f"--resolution {resolution} needs --note saying why")


def resolve_issue_core(store, key, resolution, ref=None, note=None,
                       session=None, cause="cli") -> str:
    """Resolve one open item. The caller holds issues_lock(store.open_path).

    Order is the contract (spec §2.2): a key already in the resolved file has any
    stale open copy removed BEFORE the idempotent return, so a crash between the
    two writes below is always cleared by a rerun; otherwise the item is appended
    to the resolved file first and removed from the open file second, so a crash
    can duplicate it but never lose it."""
    from ruamel.yaml.comments import CommentedMap
    _validate_resolution_flags(resolution, ref, note)
    k = canonical_bl_key(key)
    if k is None:
        raise PMError(2, f"{key!r} is not a backlog key")
    item, done = store.single_open(k), store.resolved_items(k)
    if done:
        prior = done[-1].get("resolution")
        if item is not None:
            _remove_identity(store.backlog, item)
            store.save_open()
            return f"{k} already resolved ({prior}); removed the stale open copy"
        return f"{k} already resolved ({prior})"
    if item is None:
        raise PMError(3, f"{k} is in neither {store.open_path} nor {store.resolved_path}")
    if resolution == "duplicate":
        r = canonical_bl_key(ref)
        if r is None or r == k:
            raise PMError(2, f"--ref {ref!r} must name a different BL key")
        t_open, t_res = store.open_items(r), store.resolved_items(r)
        if not t_open and not t_res:
            raise PMError(2, f"--ref {r} does not exist")
        if not t_open and all(str(t.get("resolution")) == "duplicate" for t in t_res):
            raise PMError(2, f"--ref {r} is itself resolved as a duplicate -- point at the "
                             f"item it duplicates")
        ref = r
    entry = CommentedMap()
    for kk, vv in item.items():
        entry[kk] = vv
    entry["status"] = "resolved"
    entry["resolution"] = resolution
    entry["resolved_at"] = _now_iso()
    if ref:
        entry["ref"] = ref
    if note:
        entry["note"] = note
    store.resolved.append(entry)
    store.save_resolved()
    _remove_identity(store.backlog, item)
    store.save_open()
    _issue_event(store.state_root, "issue_resolved", entry, session, cause,
                 resolution=resolution, ref=ref)
    tail = ""
    if str(item.get("status")) == "scheduled" and cause != "set-status":
        tail = f"; story {item.get('story')} still lists it in resolves"
    return f"{k} ({resolution}{', ref ' + ref if ref else ''}){tail}"


def cmd_resolve_issue(args) -> int:
    def run():
        open_path = issues_paths(args.state_root)[0]
        with issues_lock(open_path):
            msg = resolve_issue_core(IssueStore(open_path), args.key, args.resolution,
                                     args.ref, args.note, args.session_id, args.cause)
        sys.stdout.write(f"OK resolve-issue {msg}\n")
        return 0
    return _run_core(run)


def update_issue_core(store, key, severity, note=None, session=None, cause="cli") -> str:
    """Change an open item's severity. The caller holds issues_lock(store.open_path)."""
    k = canonical_bl_key(key)
    if k is None:
        raise PMError(2, f"{key!r} is not a backlog key")
    done = store.resolved_items(k)
    if done:
        raise PMError(2, f"{k} is resolved ({done[-1].get('resolution')}) -- only open "
                         f"items can be re-severitied")
    item = store.single_open(k)
    if item is None:
        raise PMError(3, f"{k} is in neither {store.open_path} nor {store.resolved_path}")
    before = str(item.get("severity", ""))
    if before == severity:
        # No change is not an update: no save, and no issue_updated event with from == to.
        # A --note lives only in that event, so say it was dropped rather than drop it silently.
        return (f"{k} severity {severity} unchanged"
                f"{' (note not recorded)' if note is not None else ''}")
    item["severity"] = severity
    store.save_open()
    _issue_event(store.state_root, "issue_updated", item, session, cause,
                 **{"from": before, "to": severity, "note": note})
    return f"{k} severity {before} -> {severity}"


def cmd_update_issue(args) -> int:
    def run():
        open_path = issues_paths(args.state_root)[0]
        with issues_lock(open_path):
            msg = update_issue_core(IssueStore(open_path), args.key, args.severity,
                                    args.note, args.session_id, args.cause)
        sys.stdout.write(f"OK update-issue {msg}\n")
        return 0
    return _run_core(run)


# A story FILE in either tree. The optional `-slug` is the documented artifact shape
# (CLAUDE.md gives `E032-S01-001-centralized-file-config.md` as its own example), and it was
# not matched here -- so a slugged document did NOT count toward the allocator's disk floor,
# and its key could be handed out again. `story_doc_path` only ever generates the UNSLUGGED
# name, so promote-issue's existence check could not see the collision either. One consumer
# (the disk floor), and widening it can only ever ADD to that floor, which is the safe
# direction: more things reserve a key, nothing releases one.
_STORY_FILE_RE = re.compile(r"^E\d{3}-S\d{2}-(\d{3})(?:-[^.]*)?\.(yaml|md)$")


def _unevaluable_lock_reason(lock, session_id):
    """Why promote cannot evaluate a present `_lock`, or None when it can (Ruling 24).

    promote is a write verb, like set-lock, so it fails safe: a foreign lock whose shape it
    cannot read refuses, even where check-lock (a read) reports such a lock FREE. A lock
    naming this session is this session's own and is not refused -- set-lock re-claims its
    own lock the same way, whatever else the block holds. Everything this returns None for
    is exactly what `_check_lock_verdict` can judge without raising.

    The holder is compared to the caller EXACTLY (Ruling F2), as `_check_lock_verdict` and
    cmd_set_lock compare it: a hand-edited 'me ' is foreign to `me` in all three paths, so a
    padded id fails safe. Only the presence check strips, reading a whitespace-only
    session_id as missing."""
    if not isinstance(lock, dict):
        return "not a mapping"
    holder = str(lock.get("session_id", "") or "")
    if not holder.strip():
        return "no session_id"
    if session_id and holder == session_id:
        return None
    claimed = _parse_iso(str(lock.get("claimed_at", "")))
    if claimed is None:
        return "claimed_at is missing or unparseable"
    if claimed.tzinfo is None:
        return "claimed_at has no timezone"
    try:
        int(lock.get("ttl_minutes", 30))
    except (TypeError, ValueError):
        return f"ttl_minutes {lock.get('ttl_minutes')!r} is not a whole number"
    return None


def _foreign_lock_error(epath: str, session_id, epic_key: str):
    """PMError(5) when the epic's `_lock` blocks this session, else None.

    A lock promote cannot evaluate (`_unevaluable_lock_reason`) refuses, naming the epic
    and clear-lock for an abandoned one (Ruling 24). A well-formed lock gets check-lock's
    own verdict (`_check_lock_verdict`, carryover 16), so promote shares its TTL semantics:
    a stale lock -- including any `ttl_minutes: 0` -- does not block. An absent or null
    `_lock` is no lock, as set-lock reads it."""
    _, data = load_node(epath)
    lock = (data or {}).get("_lock")
    if lock is None:
        return None
    why = _unevaluable_lock_reason(lock, session_id)
    if why:
        return PMError(5, f"epic {epic_key} holds a _lock that cannot be evaluated ({why}) "
                          f"-- refusing to write; if the lock is abandoned, remove it with "
                          f"clear-lock --epic {epic_key}")
    code, line = _check_lock_verdict(lock, session_id)
    if code == 0:
        return None
    return PMError(5, f"epic {epic_key} is {line} -- pass that --session-id, or wait for the "
                      f"lock to expire")


def _highest_story_on_disk(state_root, artifacts_root, epic_key, sprint_key) -> int:
    """Highest story number present in the sprint, across the state directory AND the
    artifact stories/ directory. A document without a state node still owns its key."""
    prefix = f"{epic_key}-{sprint_key}-"
    epic_dir = find_epic_dir(state_root, epic_key)
    dirs = [os.path.join(artifacts_root, epic_dirname(epic_key), sprint_dirname(sprint_key),
                         "stories")]
    if epic_dir is not None:
        dirs.insert(0, os.path.join(epic_dir, sprint_dirname(sprint_key)))
    highest = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            m = _STORY_FILE_RE.match(name)
            if m and name.startswith(prefix):
                highest = max(highest, int(m.group(1)))
    return highest


def _next_story_key(state_root, artifacts_root, epic_key, sprint_key) -> str:
    """Allocate the sprint's next story key: `max(sprint.next, highest-on-disk + 1)`.

    WHY A HIGH-WATER AND NOT JUST THE DISK. Deriving from the disk alone makes a vacated
    number immediately reusable. That is harmless while stories only ever appear, but it is a
    live defect the moment one can MOVE: a story leaving E032-S01-001 frees that key, the next
    story takes it, and `l3io-sync`'s mapping still points that key's remote issue at what is
    now DIFFERENT WORK. Nothing errors -- the issue is silently retargeted. `issues.yaml`
    carries a per-epic `next:` for exactly this reason, documented there as "a high-water mark
    that never decreases, so a deleted or resolved key is never reused".

    WHY STILL CONSULT THE DISK. Taking the max of both, rather than trusting `next` alone, is
    what keeps this small. An absent `next` (every project today) behaves exactly as before,
    so there is no migration. A `next` that is somehow too LOW cannot cause a reuse, because
    the disk floor still applies -- it is self-healing, which is why this needs no audit
    finding and no reseed verb, unlike the allocator it is modelled on. A `next` that is too
    high is honoured: it wastes a number, which is the safe direction.

    The only consequence for an ordinary project is that keys become sparse where a story is
    deleted, instead of the next one backfilling the hole.

    Callers hold the epic write lock (see cmd_promote_issue), so the read-modify-write below
    is already serialised; it takes no lock of its own.
    """
    prefix = f"{epic_key}-{sprint_key}-"
    floor = _highest_story_on_disk(state_root, artifacts_root, epic_key, sprint_key) + 1

    spath = sprint_file(state_root, epic_key, sprint_key)
    y = node = None
    stored = 0
    if spath is not None:
        y, node = load_node(spath)
        if isinstance(node, dict):
            try:
                stored = int(node.get("next") or 0)
            except (TypeError, ValueError):
                stored = 0          # unparseable is treated as absent; the disk floor holds

    number = max(stored, floor)
    if isinstance(node, dict):
        node["next"] = number + 1   # never decreases: number >= stored, so this only grows
        nodes.save_node(y, node, spath)
    return f"{prefix}{number:03d}"


def _yaml_error_reason(e) -> str:
    """One line from a ruamel parse error: its problem and where, not the multi-line dump."""
    problem = getattr(e, "problem", None) or (str(e).splitlines() or [type(e).__name__])[0]
    mark = getattr(e, "problem_mark", None)
    if mark is None:
        return problem
    return f"{problem} (line {mark.line + 1}, column {mark.column + 1})"


def _walk_story_nodes(state_root):
    """Yield (story_key, status_dir, node, path) for every story node in every status folder.

    A node that does not parse, is not valid UTF-8, or is not a mapping (Ruling F4) is
    PMError(2) naming the file (Ruling F1): every caller is a
    verb that must refuse before its first write rather than exit 1 with a traceback.
    audit-issues maps it onto its existing error channel (exit 4), not a new finding id."""
    from ruamel.yaml.error import YAMLError
    for sdir in STATUS_DIRS:
        base = os.path.join(state_root, sdir)
        if not os.path.isdir(base):
            continue
        for ename in sorted(os.listdir(base)):
            edir = os.path.join(base, ename)
            if not (ename.startswith("epic-") and os.path.isdir(edir)):
                continue
            for sname in sorted(os.listdir(edir)):
                spd = os.path.join(edir, sname)
                if not (sname.startswith("sprint-") and os.path.isdir(spd)):
                    continue
                for fname in sorted(os.listdir(spd)):
                    if not fname.endswith(".yaml") or fname == "sprint.yaml":
                        continue
                    path = os.path.join(spd, fname)
                    try:
                        node = load_node(path)[1]
                    except YAMLError as e:
                        raise PMError(2, f"{path} does not parse: {_yaml_error_reason(e)} -- "
                                         f"fix the file by hand")
                    except UnicodeDecodeError as e:
                        raise PMError(2, f"{path} is not valid UTF-8 ({e.reason} at byte "
                                         f"{e.start}) -- fix the file by hand")
                    if node is None:
                        continue
                    if not isinstance(node, dict):
                        held = "a list" if isinstance(node, list) else "a scalar"
                        raise PMError(2, f"{path} is not a mapping (it holds {held}) -- fix "
                                         f"the file by hand")
                    yield str(node.get("key") or fname[:-5]), sdir, node, path


def _dead_claim(status_dir, node) -> bool:
    """A story under archived/ that is not `done` is ignored as a claimant, because its
    epic is closed: promote's resume and audit 1d/1h skip it. If that story is later marked
    `done` (cmd_set_status has no archived guard, and pm-sync pull runs `set-status done`),
    the claim revives, and audit 1h reports the double listing; audit 1g still reports an
    item SCHEDULED to it (1g is keyed on the item's `story:`)."""
    return status_dir == "archived" and str(node.get("status", "")) != "done"


def _partial_promotion(state_root, keys):
    """The story (if any) that already claims these `keys` via its `resolves`, across EVERY
    epic -- keys spread across stories, or a story listing a superset/subset of what was
    asked for, are both claims that must refuse rather than silently mint a second story
    (audit-issues 1d/1h). Resumes only the exact match: exactly one claimant, whose
    `resolves` set equals `keys` exactly, and whose status is not `done`. Anything else --
    no exact claimant, more than one claimant, or a lone claimant whose resolves is a
    superset/subset or who is already done -- refuses (PMError 2) rather than guess.
    A dead claim (`_dead_claim`) is not a claimant at all: after the 1g repair the item is
    backlog again and a re-promotion must mint a new story, not resume the archived one.
    The caller refuses a returned claimant outside its own --epic/--sprint, which parses the
    claimant's key -- so a malformed one is refused here, naming the node, before any write."""
    keyset = set(keys)
    claimants = {}
    for story_key, sdir, node, path in _walk_story_nodes(state_root):
        if _dead_claim(sdir, node):
            continue
        resolves = {str(k) for k in (node.get("resolves") or [])}
        if resolves & keyset:
            claimants[story_key] = (node, path)
    if not claimants:
        return None
    if len(claimants) == 1:
        (story_key, (node, path)), = claimants.items()
        resolves = {str(k) for k in (node.get("resolves") or [])}
        if resolves == keyset and str(node.get("status", "")) != "done":
            try:
                parse_story_key(story_key)
            except ValueError:
                raise PMError(2, f"story node {path} has a malformed key {story_key!r} -- fix "
                                 f"it by hand, then rerun")
            return story_key
    raise PMError(2, f"{', '.join(keys)} already claimed by {sorted(claimants)} -- run "
                     f"/l3io-doctor triage (audit-issues 1d/1h)")


def _promotable_items(store, keys):
    """Resolved is checked FIRST, then the single-open guard (Ruling 8 + Ruling 5): a
    key present in issues-resolved.yaml is resolved even if a stale open copy remains
    (resolve's crash window), and IssueStore.single_open raises PMError(2) itself for
    an ambiguous key (audit-issues finding 1i)."""
    items = []
    for k in keys:
        done = store.resolved_items(k)
        if done:
            raise PMError(2, f"{k} is already resolved ({done[-1].get('resolution')})")
        item = store.single_open(k)
        if item is None:
            raise PMError(2, f"{k} is not an open backlog item")
        if str(item.get("status", "backlog")) == "scheduled":
            raise PMError(2, f"{k} is already scheduled to story {item.get('story')}")
        kind = str(item.get("kind") or "defect")
        if kind != "defect":
            raise PMError(2, f"{k} is a {kind} item -- spec items are confirmed or rejected in "
                             f"/l3io-doctor triage, never promoted to a story")
        items.append(item)
    return items


def _promotion_context(items) -> str:
    lines = ["## Context", "", "Promoted from deferred finding(s):"]
    for it in items:
        desc = str(it.get("description", "") or "").strip()
        lines.append(f"- {it.get('key')} ({it.get('severity')}, {it.get('source')})"
                     + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


def _promote_target(sr, epic_key, sprint_key):
    """(epic path, sprint path) for promote-issue, refusing an absent (3) or archived (2)
    epic and an absent (3) or already-started (2) sprint. Run once before the epic lock, to
    refuse fast, and again under it, where the answer is decisive."""
    epath = nodes.epic_file(sr, epic_key)
    if epath is None:
        raise PMError(3, f"epic {epic_key} not found under {sr}")
    if os.path.basename(os.path.dirname(os.path.dirname(epath))) == "archived":
        raise PMError(2, f"epic {epic_key} is archived -- promote into a planned or active epic")
    spath = sprint_file(sr, epic_key, sprint_key)
    if spath is None:
        raise PMError(3, f"sprint {epic_key}-{sprint_key} not found")
    sstatus = str((load_node(spath)[1] or {}).get("status", ""))
    if sstatus != "backlog":
        raise PMError(2, f"sprint {epic_key}-{sprint_key} is {sstatus!r}, not backlog -- "
                         f"promote into a sprint that has not started")
    return epath, spath


def cmd_promote_issue(args) -> int:
    """Turn open BL items into a new story (spec §2.4). Every refusal is checked before
    the first write. An early advisory `issues_lock` check refuses fast, before the epic
    lock is even taken. Then, under `epic_node_lock`, a decisive foreign-lock re-check is
    followed by ONE `issues_lock` hold spanning the decisive item check through the
    schedule save: the item check, partial-promotion detection, the story-document
    pre-check, the story node + estimate save, the story document, both roll-ups, and
    finally marking the items scheduled and saving -- all under that single nested
    `issues_lock`, so a concurrent `resolve-issue` on the same key can never land between
    the check and the write (Ruling 12a). Story first among the writes, so a failure after
    it (e.g. the scheduling save itself failing) leaves a story whose `resolves` still
    names the items, and a retry resumes it via `_partial_promotion`."""
    return _run_core(lambda: _promote_issue(args))


def _promote_issue(args) -> int:
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
    sr, ar = args.state_root, args.artifacts_root
    keys = []
    for raw in args.key:
        k = canonical_bl_key(raw)
        if k is None:
            raise PMError(2, f"--key {raw!r} is not a backlog key")
        # REFUSED, not deduped. The --title rule below reads len(keys), so collapsing a
        # repeat would disarm the one guard that makes a multi-item promotion deliberate:
        # the call asks for two items, yields one, and is never prompted for the title two
        # distinct keys would demand. The caller here is usually an agent assembling this
        # list from a user's prose (steps/plan/step-backlog-intake.md §3), which is exactly
        # the caller that can name one item twice.
        #
        # schedule-issue keeps the dedup on purpose: nothing downstream of it reads the key
        # count, so a repeat there changes nothing observable. Same shape, different
        # decision, because the consequence differs -- not an inconsistency to tidy up.
        if k in keys:
            raise PMError(2, f"--key {k} was given twice. Promoting several items into one "
                             f"story needs --title, and a repeated key would skip that "
                             f"check by collapsing to one. Drop the duplicate, or name the "
                             f"other key you meant.")
        keys.append(k)
    if len(keys) > 1 and not args.title:
        raise PMError(2, "promoting several items into one story needs --title")
    model = args.model or DEFAULT_ESTIMATE_MODEL
    overrides = rate_overrides(args)                      # bad JSON exits 2 here, pre-write
    try:
        rates = resolve_rates(model, overrides)
    except KeyError as e:
        raise PMError(2, e.args[0])
    missing = [c for c in TOKEN_CLASSES if c not in rates]
    if missing:
        raise PMError(2, f"model {model!r} has no rate for {missing}")
    epic_key = "E" + _norm_num(args.epic, 3)
    sprint_key = "S" + _norm_num(args.sprint, 2)
    epath, spath = _promote_target(sr, epic_key, sprint_key)
    open_path = issues_paths(sr)[0]
    with issues_lock(open_path):
        _promotable_items(IssueStore(open_path), keys)     # advisory: refuse fast, no epic lock yet
    err = _foreign_lock_error(epath, args.session_id, epic_key)          # advisory
    if err:
        raise err
    with epic_node_lock(sr, epic_key):
        # Resolve again under the lock: move-epic holds it too, so a move that landed while
        # this call waited has moved the directory the paths above name, and writing
        # through them would recreate the old directory as a ghost.
        epath, spath = _promote_target(sr, epic_key, sprint_key)
        err = _foreign_lock_error(epath, args.session_id, epic_key)      # decisive
        if err:
            raise err
        # One issues_lock hold spans the decisive item check through the schedule save
        # (Ruling 12a): nothing in between (compute_story_estimate, init_story_doc,
        # rollup_parent_estimate/save_node) takes issues_lock itself, so a concurrent
        # resolve-issue on the same key blocks here rather than landing between this
        # check and the write that would otherwise orphan an estimated story.
        with issues_lock(open_path):
            store = IssueStore(open_path)
            items = _promotable_items(store, keys)             # decisive
            story_key = _partial_promotion(sr, keys)
            resumed = story_key is not None
            if resumed:
                # Resume only the interrupted call itself (spec §2.4, "a story in the target
                # epic"): a claimant elsewhere was never locked or foreign-lock-checked here,
                # and the roll-ups below would target --epic, not the claimant's epic.
                c_epic, c_sprint, _ = parse_story_key(story_key)
                if (c_epic, c_sprint) != (epic_key, sprint_key):
                    raise PMError(2, f"{', '.join(keys)} were partly promoted into {story_key} "
                                     f"-- retry with --epic {c_epic[1:]} --sprint {c_sprint[1:]}")
            else:
                story_key = _next_story_key(sr, ar, epic_key, sprint_key)
                # DEFENSIVE, and deliberately kept without a fixture. `_next_story_key` above
                # already skips a key whose artifact document exists, so the key it just
                # returned cannot have one -- this arm is unreachable from inside the call.
                # It is not dead, though: it guards against a writer outside our locks, and
                # agents in this system do author story documents directly. The two locks
                # held here exclude another promote, never an external author.
                if os.path.exists(story_doc_path(ar, story_key)):
                    raise PMError(2, f"story document for {story_key} already exists -- "
                                     f"refusing to adopt it")
                node = CommentedMap()
                node["key"] = SQ(story_key)
                node["epic"] = SQ(epic_key)
                node["sprint"] = SQ(sprint_key)
                node["title"] = args.title or str(items[0].get("title", ""))
                node["status"] = "backlog"
                node["classification"] = args.classification
                seq = CommentedSeq(keys)
                seq.fa.set_flow_style()
                node["resolves"] = seq
                metrics.estimates.compute_story_estimate(
                    sr, node, args.classification, model, overrides)
                core._atomic_dump(_yaml(), node,
                            os.path.join(os.path.dirname(spath), f"{story_key}.yaml"))
            init_story_doc(sr, ar, story_key, context_md=_promotion_context(items),
                           ac_lines=[f"The deferred finding {i.get('key')} is resolved: "
                                     f"{i.get('title')}" for i in items],
                           must_not_exist=not resumed)
            _, story_sprint, _ = parse_story_key(story_key)
            metrics.estimates.rollup_parent_estimate(sr, epic_key, story_sprint,
                                                     model, overrides)
            metrics.estimates.rollup_parent_estimate(sr, epic_key, None,
                                                     model, overrides)
            for it in items:
                it["status"] = "scheduled"
                it["story"] = story_key
                it["scheduled_at"] = _now_iso()
            store.save_open()
    for it in items:
        _issue_event(sr, "issue_scheduled", it, args.session_id, args.cause, story=story_key)
    sys.stdout.write(f"OK promote-issue {', '.join(keys)} -> {story_key}"
                     f"{' (resumed)' if resumed else ''}\n")
    return 0


def _schedulable_items(store, keys, story_key):
    """Split `keys` into (to_schedule, already_here) for a named existing story.

    Gate order mirrors `_promotable_items`: resolved FIRST (Ruling 8), because a key in
    issues-resolved.yaml is resolved even if a stale open copy survives resolve's crash
    window, then the single-open guard (Ruling 5, finding 1i). It differs in exactly one
    place. An item already scheduled to THIS story is a skip rather than a refusal,
    because the mapping that drives this verb is executed as a batch and re-running the
    whole batch has to be safe -- the alternative is asking the operator to track which
    of 28 rows applied. An item scheduled to a DIFFERENT story is still a refusal:
    moving it silently would rewrite a scheduling decision somebody made and leave the
    old story's `resolves` naming an item it no longer owns, which is audit finding 1e.
    """
    to_schedule, already_here = [], []
    for k in keys:
        done = store.resolved_items(k)
        if done:
            raise PMError(2, f"{k} is already resolved ({done[-1].get('resolution')})")
        item = store.single_open(k)
        if item is None:
            raise PMError(2, f"{k} is not an open backlog item")
        kind = str(item.get("kind") or "defect")
        if kind != "defect":
            raise PMError(2, f"{k} is a {kind} item -- spec items are confirmed or rejected "
                             f"in /l3io-doctor triage, never scheduled to a story")
        if str(item.get("status", "backlog")) == "scheduled":
            at = str(item.get("story") or "")
            if at == story_key:
                already_here.append(item)
                continue
            raise PMError(2, f"{k} is already scheduled to story {at} -- unschedule it first "
                             f"(repair-issue --action unschedule --key {k}) rather than "
                             f"moving it silently")
        to_schedule.append(item)
    return to_schedule, already_here


def _schedule_target(sr, epic_key, story_key):
    """(epic path, story path, story node) for schedule-issue, refusing a home the work
    will never reach. Run once before the epic lock to refuse fast, and again under it,
    where the answer is decisive.

    Deliberately NOT `_promote_target`: that one also requires the sprint to be
    `backlog`, which is right for allocating a new story and wrong here -- attaching a
    finding to an existing story in a sprint already under way is the ordinary case.

    The two refusals are the failure this verb exists to avoid: an item silently
    acquiring a home nobody will work. `done` and `archived` are checked separately
    because neither implies the other -- a story under `archived/` can still read
    `status: backlog`, which is how 34 open items on one consumer tree came to be keyed
    to an epic that had been archived out from under them.
    """
    epath = nodes.epic_file(sr, epic_key)
    if epath is None:
        raise PMError(3, f"epic {epic_key} not found under {sr}")
    if os.path.basename(os.path.dirname(os.path.dirname(epath))) == "archived":
        raise PMError(2, f"epic {epic_key} is archived -- schedule into a planned or active "
                         f"epic, or move the epic back first (move-epic)")
    spath = story_file(sr, story_key)
    if spath is None:
        raise PMError(3, f"story {story_key} not found under {sr} -- schedule-issue attaches "
                         f"to a story that exists; use promote-issue to create one")
    node = load_node(spath)[1]
    if node is None:
        raise PMError(3, f"story {story_key} -- file {spath} is empty")
    ek, sk, _ = parse_story_key(story_key)
    problems = check_backrefs(node, ek, sk)
    if problems:
        raise PMError(4, f"back-reference mismatch for story {story_key}: "
                         f"{'; '.join(problems)}")
    status = str(node.get("status", ""))
    if status == "done":
        raise PMError(2, f"story {story_key} is done -- its acceptance criteria are already "
                         f"closed, so an unfixed finding attached here is lost. Schedule it "
                         f"to an open story, or promote-issue a new one")
    return epath, spath, node


def cmd_schedule_issue(args) -> int:
    """Attach open BL items to a story that ALREADY EXISTS (the counterpart to
    promote-issue, which only ever creates one).

    Locking mirrors promote-issue exactly, including the nesting order, so the two
    cannot deadlock against each other: an advisory `issues_lock` check to refuse fast,
    an advisory foreign-lock check, then `epic_node_lock`, a re-resolve under it because
    move-epic holds the same lock and may have moved the directory while this call
    waited, a decisive foreign-lock re-check, and ONE `issues_lock` hold spanning the
    decisive item check through the schedule save (Ruling 12a) so a concurrent
    resolve-issue on the same key cannot land between the check and the write.

    Story node first among the writes, matching promote: a failure after it leaves a
    story whose `resolves` names the items while they still read `backlog`, which is
    audit finding 1d -- the state `repair-issue --action link` exists to repair. The
    reverse order would leave items pointing at a story that never claimed them, which
    is finding 1e and has no single-key repair.

    It does NOT re-estimate the story or re-roll-up its parents. The story's estimate was
    set when it was written, by whoever sized it; attaching a finding whose fix its
    acceptance criteria already imply is not a resize, and overwriting a human's estimate
    as a side effect of a bookkeeping verb would be worse than leaving it stale.
    """
    return _run_core(lambda: _schedule_issue(args))


def _schedule_issue(args) -> int:
    from ruamel.yaml.comments import CommentedSeq
    sr = args.state_root
    keys = []
    for raw in args.key:
        k = canonical_bl_key(raw)
        if k is None:
            raise PMError(2, f"--key {raw!r} is not a backlog key")
        if k not in keys:
            keys.append(k)
    try:
        epic_key, _sprint_key, _ = parse_story_key(args.story)
    except ValueError as e:
        raise PMError(2, str(e)) from None

    open_path = issues_paths(sr)[0]
    _schedule_target(sr, epic_key, args.story)                    # advisory: refuse fast
    with issues_lock(open_path):
        _schedulable_items(IssueStore(open_path), keys, args.story)   # advisory
    err = _foreign_lock_error(nodes.epic_file(sr, epic_key), args.session_id, epic_key)
    if err:
        raise err
    with epic_node_lock(sr, epic_key):
        # Re-resolve under the lock: move-epic holds it too, so a move that landed while
        # this call waited has moved the directory the paths above name.
        epath, spath, node = _schedule_target(sr, epic_key, args.story)
        err = _foreign_lock_error(epath, args.session_id, epic_key)    # decisive
        if err:
            raise err
        with issues_lock(open_path):
            store = IssueStore(open_path)
            items, already = _schedulable_items(store, keys, args.story)   # decisive
            if items:
                existing = [str(x) for x in (node.get("resolves") or [])]
                seq = node.get("resolves")
                if not isinstance(seq, CommentedSeq):
                    seq = CommentedSeq(existing)
                    seq.fa.set_flow_style()
                    node["resolves"] = seq
                for it in items:
                    k = str(it.get("key"))
                    if k not in existing:        # a story may already claim it (finding 1d)
                        seq.append(k)
                nodes.save_node(_yaml(), node, spath)
                stamp = _now_iso()
                for it in items:
                    it["status"] = "scheduled"
                    it["story"] = args.story
                    it["scheduled_at"] = stamp
                store.save_open()
    for it in items:
        # via: a third route to `scheduled`. promote-issue writes no via, repair-link
        # writes "repair-link"; without a distinct value the log cannot say how an item
        # got its story, which is the only record of whether a human chose it.
        _issue_event(sr, "issue_scheduled", it, args.session_id, args.cause,
                     story=args.story, via="schedule")
    done_keys = [str(i.get("key")) for i in items]
    skipped = [str(i.get("key")) for i in already]
    parts = []
    if done_keys:
        parts.append(f"{', '.join(done_keys)} -> {args.story}")
    if skipped:
        parts.append(f"{', '.join(skipped)} already scheduled to {args.story} (skipped)")
    sys.stdout.write(f"OK schedule-issue {'; '.join(parts)}\n")
    return 0


# BL keys run 001-999, so next[epic] -- the NEXT key to hand out -- is at most 1000.
_BL_NEXT_MAX = 1000


def _stale_story_refs(item, stories, moved) -> list:
    """The (field, old_key, new_key | None) triples on one backlog item whose story key no
    longer exists AND is recorded in some story's `previous_keys`. `new_key` is that story
    when exactly one records it, and None when more than one does (ambiguous: reported,
    never guessed at).

    A dangling key that NO story records is deliberately not reported here: that is the
    ordinary shape of a story whose directory was removed or whose epic was retired, no
    verb here can repair it, and the one actionable case -- an open item scheduled to a
    story that no longer exists -- is finding 1b, whose `unschedule` repair is correct
    precisely because there is no key to point at instead.

    A field is only considered when its value PARSES as a story key: `ref` also carries a
    commit SHA or a proposal path for a spec-change item, and neither is a broken pointer.
    A key that still names a live story is never stale -- including the case where the key
    was re-issued to different work, which reads as resolved and is indistinguishable from
    here. The allocator's high-water is what prevents that, not this check.
    """
    out = []
    for field in STORY_REF_FIELDS:
        v = str(item.get(field) or "")
        if not _STORY_KEY_RE.match(v) or v in stories:
            continue
        heirs = moved.get(v, [])
        if heirs:
            out.append((field, v, heirs[0] if len(heirs) == 1 else None))
    return out


def _story_index(state_root):
    """One walk of every story node, as the four maps the backlog checks read.

    stories: key -> (status folder, status).
    claims:  BL key -> every story listing it in `resolves` (1b and 1j read it).
    live:    the same minus dead claims (`_dead_claim`) -- 1d and 1h read only live claims,
             so the 1g repair leaves a clean audit.
    moved:   old story key -> the stories that now carry it in `previous_keys`, which is how
             a reference orphaned by reparent-story is told apart from one that never
             resolved at all (1l).
    """
    stories, claims, live, moved = {}, {}, {}, {}
    for skey, sdir, node, _ in _walk_story_nodes(state_root):
        stories[skey] = (sdir, str(node.get("status", "")))
        dead = _dead_claim(sdir, node)
        for k in node.get("resolves") or []:
            claims.setdefault(str(k), []).append(skey)
            if not dead:
                live.setdefault(str(k), []).append(skey)
        for pk in node.get("previous_keys") or []:
            moved.setdefault(str(pk), []).append(skey)
    return stories, claims, live, moved


def _story_key_maps(state_root):
    """`(stories, moved)` -- the two maps `_stale_story_refs` needs. The repoint repair
    re-derives them from the same walk audit-issues used, so the gate and the write can
    never disagree about which story carries an old key."""
    stories, _claims, _live, moved = _story_index(state_root)
    return stories, moved


def _audit_findings(state_root, store) -> list:
    """Structural integrity findings 1a-1l (spec §3.1). The caller holds issues_lock."""
    findings = []

    def add(fid, key, detail, repair, story=None, epic=None):
        findings.append({"id": fid, "key": key, "story": story, "epic": epic,
                         "detail": detail, "repair": repair})

    stories, claims, live, moved = _story_index(state_root)
    open_by, res_by = {}, {}
    for lst, by in ((store.backlog, open_by), (store.resolved, res_by)):
        for it in lst:
            if isinstance(it, dict):
                by.setdefault(str(it.get("key", "")), []).append(it)

    for by, fname in ((open_by, ISSUES_FILENAME), (res_by, RESOLVED_FILENAME)):
        for k, its in by.items():
            if len(its) > 1:
                add("1i", k, f"appears {len(its)} times in {fname}",
                    "report only -- rekey or merge by hand")
            elif canonical_bl_key(k) != k:
                add("1i", k, f"non-canonical key in {fname}", "report only -- rekey by hand")
    for k in open_by:
        if k in res_by:
            add("1a", k, "present in both issue files",
                "resolve-issue rerun -- it clears the open copy")

    # 1l -- a story-key field pointing at a key a re-key moved. Computed before the loops
    # below because 1b defers to it: a scheduled item with a repointable heir must be
    # repointed, and 1b's `unschedule` would discard the scheduling instead. A dangling key
    # no story records is not 1l at all (see `_stale_story_refs`), so 1b still owns every
    # case where unschedule is the right answer.
    stale = {}
    for by, fname in ((open_by, ISSUES_FILENAME), (res_by, RESOLVED_FILENAME)):
        for k, its in by.items():
            if len(its) != 1:
                continue        # 1i: an ambiguous key is never evaluated
            if by is open_by and k in res_by:
                continue        # Ruling 8, resolved first: the open copy is 1a, and the
                                # rerun that clears it would discard any repoint done here
            for fld, old, new in _stale_story_refs(its[0], stories, moved):
                stale.setdefault(k, []).append((fld, old, new, fname))
    for k in sorted(stale):
        for fld, old, new, fname in stale[k]:
            if new is not None:
                add("1l", k, f"{fld}: {old} in {fname} names no story; {new} records it in "
                             f"previous_keys (it was re-keyed by reparent-story)",
                    f"repair-issue --action repoint --key {k}", story=new)
            else:
                add("1l", k, f"{fld}: {old} in {fname} names no story, and {len(moved[old])} "
                             f"stories record it in previous_keys "
                             f"({', '.join(sorted(moved[old]))})",
                    "report only -- which story this means is not derivable; the duplicate "
                    "previous_keys entry is the defect, so fix that and rerun repoint")

    def repointable(k) -> bool:
        return any(f == "story" and n is not None for f, _o, n, _fn in stale.get(k, []))

    for k in open_by:
        if k in res_by:
            continue            # Ruling 8, resolved first: the stale open copy is 1a only
        try:
            it = store.single_open(k)
        except PMError:
            continue            # 1i (reported above): an ambiguous key is never evaluated
        st = str(it.get("status", ""))
        if st in LEGACY_OPEN_STATUSES:
            add("1f", k, f"open item has legacy status {st!r} (pre-3.0 resting state)",
                f"run: pm-status.py repair-issue --state-root S --key {k} "
                f"--action normalize-status  # -> {LEGACY_OPEN_STATUSES[st]}")
        elif st not in OPEN_ISSUE_STATUSES:
            add("1f", k, f"open item has status {st!r}", "report only")
        kind = it.get("kind")
        if kind is not None and str(kind) not in ISSUE_KINDS:
            add("1k", k, f"unknown kind {kind!r}", "report only -- fix the kind by hand")
        elif str(kind) in SPEC_ISSUE_KINDS and not str(it.get("ref") or "").strip():
            add("1k", k, f"{kind} item has no ref",
                "report only -- add the commit SHA or the proposal path by hand")
        if st == "scheduled" and repointable(k):
            pass                # 1l owns it: repoint, do not unschedule
        elif st == "scheduled":
            sk = str(it.get("story", "") or "")
            if sk not in stories or sk not in claims.get(k, []):
                add("1b", k, f"scheduled to {sk or '(none)'}, which is missing or does not "
                             f"list it", "repair-issue --action unschedule", story=sk or None)
            elif stories[sk][0] == "archived" and stories[sk][1] != "done":
                add("1g", k, f"scheduled to {sk}, which is archived and not done",
                    "repair-issue --action unschedule", story=sk)
    for k, sks in claims.items():
        lsks = live.get(k, [])
        if len(lsks) > 1:
            add("1h", k, f"listed in resolves of {', '.join(lsks)}",
                "report only -- decide which story owns it")
        if k not in open_by and k not in res_by:
            add("1b", k, f"named in resolves of {', '.join(sks)} but in neither issue file",
                "report only -- remove it from resolves by hand", story=sks[0])
            continue
        if k not in open_by or k in res_by:     # Ruling 8: resolved first
            continue
        try:
            it = store.single_open(k)
        except PMError:
            continue                            # 1i: an ambiguous key is never evaluated
        for sk in lsks:
            if sk not in stories:
                continue
            if stories[sk][1] == "done":
                add("1c", k, f"story {sk} is done but {k} is still open",
                    f"resolve-issue --key {k} --resolution fixed --ref {sk}", story=sk)
            elif str(it.get("status", "")) == "backlog":
                add("1d", k, f"story {sk} lists {k}, which is still backlog",
                    f"repair-issue --action link --story {sk}", story=sk)
    nxt = store.open.get("next")
    by_hand = f"fix it by hand; reseed refuses a value above {_BL_NEXT_MAX}"
    hand_fix = f"report only -- {by_hand}"
    if nxt is not None and not isinstance(nxt, dict):
        add("1e", "next", f"next is malformed ({nxt!r})", "repair-issue --action reseed")
    elif nxt:
        # Sort on the normalised epic: a hand-edited unquoted key (`1: 5`) is an int, and
        # sorting it against the string keys raised TypeError.
        for e in sorted(nxt, key=lambda e: (_norm_num(str(e), 3), str(e))):
            en = _norm_num(str(e), 3)
            stored, highest = _int_or_none(nxt.get(e)), store.highest_suffix(en)
            beyond = stored is not None and stored > _BL_NEXT_MAX
            if e != en:
                # User decision: allocate reads only the canonical key, so an alias (`1` or
                # '1' for '001') is 1e whatever its value; reseed folds it in by max -- except
                # past the key space, which reseed refuses (exit 2), so that alias gets the
                # same hand-fix repair as its key-space finding below, not a reseed it can't run.
                advice = by_hand if beyond else "run repair-issue --action reseed"
                # Name the raw bytes, not just the parsed key. The parsed key can differ
                # from what is in the file in two ways at once -- an unquoted `019` loads
                # as `19`, losing both the quoting AND the leading zero -- so an operator
                # shown only `19` goes looking for a writer that emits integers and finds
                # none. The usual cause is an external YAML round-trip rather than any
                # pm-status verb: PyYAML's safe_dump quotes `001`-`007` and `012`, whose
                # digits resolve as octal, but emits `008`, `009`, `018`, `019` bare
                # because 8 and 9 are not octal digits -- so a project can round-trip this
                # file for weeks and only corrupt the epics with an 8 or 9 behind the
                # leading zero. Cost a consumer project a wrongly-filed defect against
                # append-issue, which normalises correctly in every spelling.
                add("1e", f"BL-E{en}", f"next has a non-canonical key {e!r} for epic {en} "
                                      f"(= {nxt.get(e)!r}); allocate reads only the quoted "
                                      f"{en!r}. Check the raw bytes -- a bare (unquoted) "
                                      f"{en} in the file parses as {e!r}, and an external "
                                      f"YAML round-trip is a likelier cause than any "
                                      f"pm-status write -- {advice}",
                    hand_fix if beyond else "repair-issue --action reseed", epic=en)
            elif stored is None or stored <= highest:
                add("1e", f"BL-E{en}", f"next[{e}] = {nxt.get(e)!r} but the highest key is "
                                      f"{highest:03d}", "repair-issue --action reseed", epic=en)
            if beyond:
                add("1e", f"BL-E{en}", f"next[{e!r}] = {stored} exceeds the BL key space (keys "
                                      f"stop at 999, so next is at most {_BL_NEXT_MAX})",
                    hand_fix, epic=en)
    for k, its in res_by.items():
        it = its[-1]
        ref = str(it.get("ref", "") or "")
        # Only a ref story whose resolves: lists the key: a legitimate `--ref <story in
        # progress>` never claimed it, and reopening it would manufacture a 1b.
        if (str(it.get("resolution")) == "fixed" and ref in stories
                and stories[ref][1] != "done" and ref in claims.get(k, [])):
            add("1j", k, f"resolved fixed by {ref}, which is now {stories[ref][1]!r}",
                "repair-issue --action reopen", story=ref)
    return findings


def cmd_audit_issues(args) -> int:
    """Structural integrity of the backlog (spec §3.1). Read-only. Both issue files are
    read under issues_lock whenever either one exists, so a concurrent resolve cannot
    fake a finding. When neither exists, no lock is taken -- a read-only command must
    not create issues.yaml.lock -- and the story walk still runs, unlocked, over an
    empty store, so finding 1b can still report a resolves: key that names neither
    file. Exit 4 when anything is found. A malformed issue file, or a story node that
    does not parse, is not valid UTF-8 or is not a mapping (Rulings F1/F4: the existing
    channel, not a new finding id), also exits 4; under
    --format json it still prints a parseable document, {"findings": [], "error": MSG},
    because triage and the health check parse it. Heuristic checks live in
    l3io-doctor/scripts/audit-backlog.py."""
    findings = []
    open_path, res_path = issues_paths(args.state_root)
    try:
        if os.path.exists(open_path) or os.path.exists(res_path):
            with issues_lock(open_path):
                findings = _audit_findings(args.state_root, IssueStore(open_path))
        elif os.path.isdir(args.state_root):
            findings = _audit_findings(args.state_root, IssueStore(open_path))
    except PMError as e:
        sys.stderr.write(f"pm-status.py: {e.msg}\n")
        if args.format == "json":   # triage T2 and health-check Check 13 parse this document
            sys.stdout.write(json.dumps({"findings": [], "error": e.msg}, indent=2) + "\n")
        return 4
    if args.format == "json":
        sys.stdout.write(json.dumps({"findings": findings}, indent=2) + "\n")
    elif not findings:
        sys.stdout.write("audit-issues: no integrity findings\n")
    else:
        for f in findings:
            sys.stdout.write(f"{f['id']}  {f['key']}  {f['detail']}\n"
                             f"      repair: {f['repair']}\n")
    return 4 if findings else 0


def cmd_repair_issue(args) -> int:
    """Narrow structural repairs (spec §3.4). Each action refuses (exit 2) unless its
    audit finding holds for --key, so it can only move the backlog toward a state
    audit-issues accepts -- never invent one it would flag. `unschedule` and `link` act on
    an open item, so they also refuse a key with a resolved entry (Ruling 8, resolved
    first): a stale open copy is finding 1a, cleared by a resolve-issue rerun. `repoint`
    acts on whichever file holds the item -- the resolved entry when there is one, for the
    same reason: repointing an open copy a resolve-issue rerun is about to delete is work
    thrown away."""
    return _run_core(lambda: _repair_issue(args))


def _epic_is_archived(state_root, item) -> bool | None:
    """True/False for an item's epic, or None when its status cannot be established.

    None matters: an item whose epic has no state node cannot be classified, and guessing
    either way is the error this whole path exists to avoid.
    """
    epic = str(item.get("epic", "")).strip()
    if not epic:
        return None
    d = find_epic_dir(state_root, f"E{_norm_num(epic, 3)}")
    if d is None:
        return None
    return os.path.basename(os.path.dirname(d)) == "archived"


def _normalize_one_legacy(store, state_root, item, session, cause):
    """Apply the epic-aware rule to one legacy-status item. Returns a verb string for the
    report: 'resolved', 'normalized', or 'skipped'.

    The rule, and why it is not a flat mapping: `deferred` was a DISPOSITION -- "we looked at
    this and decided not now". `backlog` means open and undecided, and neither open status
    carries a decision, so mapping every `deferred` to `backlog` erases one.

      behind an OPEN epic      -> backlog. The loss is harmless: the item is open either way.
      behind an ARCHIVED epic  -> resolved `deferred`. It will not be picked up in that epic,
                                  and issues-resolved.yaml is where a resolution can actually
                                  hold the decision.
      epic status unknown      -> skipped, reported, untouched.

    Measured on the project that found this: 518 of 520 open items sat behind archived epics,
    and mapping them to `backlog` made 444 undecided findings behind closed epics, reddening
    that project's guard against exactly that.
    """
    was = str(item.get("status", ""))
    archived = _epic_is_archived(state_root, item)
    key = str(item.get("key", ""))
    if archived is None:
        return "skipped"
    if archived:
        resolve_issue_core(store, key, "deferred",
                           note=f"migrated from the pre-3.0 open status {was!r}; the epic was "
                                f"already closed, so the deferral is recorded as a resolution "
                                f"rather than reopened as undecided",
                           session=session, cause=cause)
        return "resolved"
    item["status"] = LEGACY_OPEN_STATUSES[was]
    _issue_event(store.state_root, "issue_status_normalized", item, session, cause,
                 note=f"{was} -> {item['status']}")
    return "normalized"


def _normalize_all_legacy(args) -> int:
    """Normalize every legacy open status in one pass, under one lock.

    Measured on a real upgrade: 452 items. One-at-a-time that is 452 subprocesses, each
    taking the issues lock, inside a triage step that confirms per item -- reported back as
    impractical, and it is. Batching adds no judgement: the mapping is mechanical, and the
    same LEGACY_OPEN_STATUSES membership test gates each item exactly as the single-key path
    does, so anything unrecognised is left alone rather than swept along.
    """
    open_path = issues_paths(args.state_root)[0]
    with issues_lock(open_path):
        store = IssueStore(open_path)
        # Snapshot first: resolve_issue_core mutates the open list, so iterating it live
        # would skip items.
        legacy = [it for it in list(store.open.get("backlog") or [])
                  if isinstance(it, dict) and str(it.get("status", "")) in LEGACY_OPEN_STATUSES]
        if not legacy:
            sys.stdout.write("OK normalize-status --all-legacy: no legacy status found\n")
            return 0
        tally = {"resolved": 0, "normalized": 0, "skipped": 0}
        skipped_keys = []
        for it in legacy:
            verb = _normalize_one_legacy(store, args.state_root, it,
                                         args.session_id, args.cause)
            tally[verb] += 1
            if verb == "skipped":
                skipped_keys.append(str(it.get("key", "")))
        store.save_open()
    sys.stdout.write(
        f"OK normalize-status --all-legacy: {tally['normalized']} normalized to backlog "
        f"(open epic), {tally['resolved']} resolved as deferred (closed epic), "
        f"{tally['skipped']} skipped\n")
    if skipped_keys:
        sys.stdout.write(
            f"  skipped -- epic status could not be established, left untouched: "
            f"{', '.join(skipped_keys)}\n")
    return 0


def _normalize_keys(args) -> int:
    """Rewrite every stored epic/sprint to its canonical form, wherever one is stored.

    Fixes records written before the write sites normalised: --epic accepted '3', '03',
    '003', 'E3', 'E003' and 'e003', all six produced the same correct key, and all six were
    stored verbatim. One consuming project measured 116 bare-digit against 7 E-prefixed in
    one file. No verb could repair them -- update-issue changes severity only and the other
    repair actions do not touch these fields -- and hand-editing is forbidden by the state
    contract, so they were simply stuck.

    Whole-file by default with no --key, because unlike normalize-status there is no
    per-item judgement: the canonical form of a key is not a decision. Two files, each kept
    in the form it already uses (see canonical_epic_key): issues.yaml stores bare digits,
    adr-register.yaml stores key form.
    """
    changed = {"issues": 0, "register": 0}
    open_path = issues_paths(args.state_root)[0]
    with issues_lock(open_path):
        store = IssueStore(open_path)
        for lst in (store.backlog, store.resolved):
            for it in lst:
                if not isinstance(it, dict):
                    continue
                for field, width in (("epic", 3), ("sprint", 2)):
                    cur = it.get(field)
                    if cur in (None, ""):
                        continue
                    want = _norm_num(cur, width)
                    if str(cur) != want:
                        it[field] = want
                        changed["issues"] += 1
        if changed["issues"]:
            store.save_open()
            store.save_resolved()

    with adr_register_lock(args.state_root):
        y, reg = load_adr_register(args.state_root)
        for entry in reg.get("reserved") or []:
            if not isinstance(entry, dict) or not entry.get("epic"):
                continue
            want = canonical_epic_key(entry["epic"])
            if str(entry["epic"]) != want:
                entry["epic"] = want
                changed["register"] += 1
        if changed["register"]:
            core._atomic_dump(y, reg, adr_register_path(args.state_root))

    total = changed["issues"] + changed["register"]
    if total == 0:
        sys.stdout.write("OK normalize-keys: every stored epic/sprint is already canonical\n")
        return 0
    sys.stdout.write(
        f"OK normalize-keys: {changed['issues']} field(s) in issues.yaml, "
        f"{changed['register']} in adr-register.yaml\n")
    return 0


def _repair_issue(args) -> int:
    from ruamel.yaml.comments import CommentedMap
    if getattr(args, "all_legacy", False):
        if args.action != "normalize-status":
            raise PMError(2, "--all-legacy applies only to --action normalize-status")
        return _normalize_all_legacy(args)
    # normalize-keys is whole-file by construction: the canonical form of a key is not a
    # judgement call, so there is nothing for a --key to scope and nothing to confirm.
    if args.action == "normalize-keys":
        return _normalize_keys(args)
    if not args.key:
        raise PMError(2, "--key is required, or --all-legacy with --action normalize-status, "
                         "or --action normalize-keys")
    k = canonical_bl_key(args.key)
    if k is None:
        raise PMError(2, f"--key {args.key!r} is not a backlog key")
    epic = k[4:7]
    act = args.action
    open_path = issues_paths(args.state_root)[0]
    with issues_lock(open_path):
        store = IssueStore(open_path)
        findings = _audit_findings(args.state_root, store)

        def holds(ids, story=None):
            return any(f["id"] in ids and f["key"] == k and (story is None or f["story"] == story)
                       for f in findings)

        if act == "link" and not args.story:
            raise PMError(2, "--action link needs --story")
        if act in ("unschedule", "link"):
            done = store.resolved_items(k)      # Ruling 8: resolved first
            if done:
                raise PMError(2, f"{act}: {k} is already resolved "
                                 f"({done[-1].get('resolution')}) -- audit finding 1a: rerun "
                                 f"resolve-issue --key {k} (any valid --resolution; the "
                                 f"recorded one is kept) to clear a stale open copy")
        if act == "unschedule":
            opens = store.open_items(k)
            if not (holds({"1b", "1g"}) and len(opens) == 1
                    and str(opens[0].get("status")) == "scheduled"):
                raise PMError(2, f"unschedule: audit finding 1b/1g does not hold for {k}")
            it = opens[0]
            story = it.get("story")
            it["status"] = "backlog"
            it.pop("story", None)
            it.pop("scheduled_at", None)
            store.save_open()
            # scheduled -> backlog is a status transition; the events are its history
            _issue_event(store.state_root, "issue_unscheduled", it, args.session_id,
                         args.cause, story=str(story) if story is not None else None)
            msg = f"{k} unscheduled -> backlog"
        elif act == "link":
            if not holds({"1d"}, story=args.story):
                raise PMError(2, f"link: audit finding 1d does not hold for {k} and {args.story}")
            it = store.single_open(k)           # 1i refusal, never an arbitrary copy
            it["status"] = "scheduled"
            it["story"] = args.story
            it["scheduled_at"] = _now_iso()
            store.save_open()
            # via: tells a repaired scheduling apart from promote's, which has no via field
            _issue_event(store.state_root, "issue_scheduled", it, args.session_id, args.cause,
                         story=args.story, via="repair-link")
            msg = f"{k} scheduled to {args.story}"
        elif act == "normalize-status":
            # Gated like every other action: only a status this schema once used, and only
            # to its documented equivalent. An unrecognised status has no safe mapping, so
            # it stays 1f/report-only rather than being guessed into backlog.
            opens = store.open_items(k)
            if len(opens) != 1:
                raise PMError(2, f"normalize-status: {k} does not resolve to one open item")
            it = opens[0]
            was = str(it.get("status", ""))
            if was not in LEGACY_OPEN_STATUSES:
                raise PMError(2, f"normalize-status: {k} has status {was!r}, which is not a "
                                 f"known legacy status ({', '.join(sorted(LEGACY_OPEN_STATUSES))})"
                                 f" -- audit finding 1f does not hold in its legacy form")
            verb = _normalize_one_legacy(store, args.state_root, it,
                                         args.session_id, args.cause)
            store.save_open()
            if verb == "skipped":
                msg = (f"{k} left at {was!r} -- its epic has no state node, so whether the "
                       f"epic is closed cannot be established and the mapping would be a guess")
            elif verb == "resolved":
                msg = f"{k} {was} -> resolved as deferred (its epic is closed)"
            else:
                msg = f"{k} {was} -> {it['status']} (legacy status normalized)"
        elif act == "repoint":
            # Gated like the rest, but on 1l AND on there being exactly one heir to point
            # at: a key no story records is reported, never guessed at. The heir is
            # re-derived here rather than read off the finding, so the gate and the write
            # cannot disagree about which story that is.
            if not holds({"1l"}):
                raise PMError(2, f"repoint: audit finding 1l does not hold for {k}")
            opens, done = store.open_items(k), store.resolved_items(k)
            # Ruling 8, resolved first: repointing an open copy that a resolve-issue rerun
            # is about to delete would be work thrown away, and 1l skips it for that reason.
            items = [done[-1]] if done else opens
            if len(items) != 1:
                raise PMError(2, f"repoint: {k} does not resolve to one item")
            stories, moved = _story_key_maps(args.state_root)
            fixes = [(f, o, n) for f, o, n in _stale_story_refs(items[0], stories, moved)
                     if n is not None]
            if not fixes:
                raise PMError(2, f"repoint: {k} has a stale story key, but no story records "
                                 f"it in previous_keys -- there is nothing to repoint it to")
            for field, old, new in fixes:
                items[0][field] = new
            if done:
                store.save_resolved()
            else:
                store.save_open()
            _issue_event(store.state_root, "issue_repointed", items[0], args.session_id,
                         args.cause, story=str(items[0].get("story") or "") or None,
                         fields={f: [o, n] for f, o, n in fixes})
            msg = f"{k} " + ", ".join(f"{f} {o} -> {n}" for f, o, n in fixes)
        elif act == "reseed":
            if not any(f["id"] == "1e" and (f["epic"] == epic or f["key"] == "next")
                       for f in findings):
                raise PMError(2, f"reseed: audit finding 1e does not hold for epic {epic}")
            nxt = store.open.get("next")
            if not isinstance(nxt, dict):
                nxt = CommentedMap()
                store.open["next"] = nxt
                epics = sorted({canonical_bl_key(str(i.get("key", "")))[4:7]
                                for i in list(store.backlog) + list(store.resolved)
                                if isinstance(i, dict) and canonical_bl_key(str(i.get("key", "")))})
                for e in epics:
                    nxt[e] = store.highest_suffix(e) + 1
            else:
                # Drop non-canonical aliases of the epic (a hand-edited `1:`), which audit
                # would otherwise keep reporting as 1e -- folding their values into the max,
                # so `next` never decreases.
                aliases = [a for a in nxt if _norm_num(str(a), 3) == epic]
                # ...but never fold a value past the key space into the canonical key: that
                # is a hand edit gone wrong, and the max would make it permanent.
                for a in aliases:
                    v = _int_or_none(nxt.get(a))
                    if v is not None and v > _BL_NEXT_MAX:
                        raise PMError(2, f"reseed: next[{a!r}] = {v} exceeds the BL key space "
                                         f"(keys stop at 999, so next is at most "
                                         f"{_BL_NEXT_MAX}) -- fix it by hand; nothing written")
                known = [v for v in (_int_or_none(nxt.get(a)) for a in aliases) if v is not None]
                for a in aliases:
                    if a != epic:
                        del nxt[a]
                nxt[epic] = max([store.highest_suffix(epic) + 1] + known)
            store.save_open()
            msg = f"next reseeded ({', '.join(f'{e}={v}' for e, v in nxt.items())})"
        else:  # reopen
            if not holds({"1j"}):
                raise PMError(2, f"reopen: audit finding 1j does not hold for {k}")
            entry = store.resolved_items(k)[-1]
            ref = str(entry.get("ref"))
            if not store.open_items(k):        # absent unless a previous reopen was interrupted
                item = CommentedMap()
                for kk, vv in entry.items():
                    if kk not in ("resolution", "resolved_at", "ref", "note"):
                        item[kk] = vv
                item["status"] = "scheduled"
                item["story"] = ref
                item["scheduled_at"] = _now_iso()
                store.backlog.append(item)
                store.save_open()               # add first: an item is never lost
            _remove_identity(store.resolved, entry)
            store.save_resolved()
            _issue_event(store.state_root, "issue_reopened", entry, args.session_id,
                         args.cause, story=ref)
            msg = f"{k} reopened, scheduled to {ref}"
    sys.stdout.write(f"OK repair-issue {msg}\n")
    return 0


def _origin_archived(state_root, epic) -> bool:
    try:
        d = find_epic_dir(state_root, "E" + _norm_num(epic, 3))
    except ValueError:
        return False
    return d is not None and os.path.basename(os.path.dirname(d)) == "archived"


def cmd_list_issues(args) -> int:
    """List (with optional filters) the open items in issues.yaml; with --resolved, the
    resolved items in issues-resolved.yaml; with --all (JSON only), both.

    A missing issues.yaml and a filter set that matches nothing are both success
    (exit 0) — an empty backlog is a normal project state, not a failure. Filters
    combine with AND; a repeated --severity ORs the given severities together.

    --all reads both files under one issues_lock so a concurrent resolve cannot
    tear the snapshot.
    """
    return _run_core(lambda: _list_issues(args))


def _list_issues(args) -> int:
    if args.resolution and not args.resolved:
        raise PMError(2, "--resolution filters resolved items; add --resolved")
    if args.status and (args.resolved or args.all):
        raise PMError(2, "--status filters open items; drop --resolved/--all")
    if args.all and args.format != "json":
        raise PMError(2, "--all is JSON only; add --format json")
    open_path, res_path = issues_paths(args.state_root)
    if args.all:
        if not (os.path.exists(open_path) or os.path.exists(res_path)):
            opened, resolved = [], []
        else:
            with issues_lock(open_path):
                od, rd = core._load(open_path)[1] or {}, core._load(res_path)[1] or {}
            for name, data, path in (("backlog", od, open_path), ("resolved", rd, res_path)):
                if data.get(name) is not None and not isinstance(data.get(name), list):
                    raise PMError(2, f"{path} has a malformed '{name}' field")
            opened = list(od.get("backlog") or [])
            resolved = list(rd.get("resolved") or [])
    else:
        src = res_path if args.resolved else open_path
        items = list((core._load(src)[1] or {}).get("resolved" if args.resolved else "backlog") or [])

    epic_filter = _norm_num(args.epic, 3) if args.epic else None
    sprint_filter = _norm_num(args.sprint, 2) if args.sprint else None
    severity_filter = set(args.severity) if args.severity else None

    def matches(item) -> bool:
        if not isinstance(item, dict):
            return False
        if epic_filter is not None and _norm_num(item.get("epic", ""), 3) != epic_filter:
            return False
        if sprint_filter is not None:
            item_sprint = str(item.get("sprint", "") or "").strip()
            # empty sprint = epic-level item; it never satisfies a --sprint filter
            if not item_sprint or _norm_num(item_sprint, 2) != sprint_filter:
                return False
        if severity_filter is not None and item.get("severity") not in severity_filter:
            return False
        if args.status and str(item.get("status", "")) != args.status:
            return False
        if args.resolution and str(item.get("resolution", "")) != args.resolution:
            return False
        return not (getattr(args, "kind", None) and str(item.get("kind") or "defect") != args.kind)

    def as_json(item):
        d = dict(item)
        d["origin_archived"] = _origin_archived(args.state_root, item.get("epic", ""))
        return d

    if args.all:
        sys.stdout.write(json.dumps({"open": [as_json(i) for i in opened if matches(i)],
                                     "resolved": [as_json(i) for i in resolved if matches(i)]},
                                    indent=2) + "\n")
        return 0
    filtered = [i for i in items if matches(i)]
    if args.format == "json":
        sys.stdout.write(json.dumps([as_json(i) for i in filtered], indent=2) + "\n")
        return 0
    if not filtered:
        sys.stdout.write("(no matching issues)\n")
        return 0
    state_col = "RESOLUTION" if args.resolved else "STATUS"
    headers = ["KEY", "EPIC", "SPRINT", "SEVERITY", state_col, "ORIGIN", "TITLE"]
    rows = [[str(i.get("key", "")), str(i.get("epic", "")), str(i.get("sprint", "")) or "-",
             str(i.get("severity", "")),
             str(i.get("resolution" if args.resolved else "status", "")),
             "archived" if _origin_archived(args.state_root, i.get("epic", "")) else "-",
             str(i.get("title", ""))] for i in filtered]
    widths = [max(len(headers[c]), *(len(r[c]) for r in rows)) for c in range(len(headers))]

    def _fmt_row(cells):
        last = len(cells) - 1
        return "  ".join(c if idx == last else c.ljust(widths[idx]) for idx, c in enumerate(cells))

    sys.stdout.write(_fmt_row(headers) + "\n")
    for r in rows:
        sys.stdout.write(_fmt_row(r) + "\n")
    return 0


def move_epic(state_root: str, epic_key: str, to_status: str) -> str:
    """Move an epic directory between status folders, preferring `git mv`.

    The directory name never changes — only its parent folder — so git records a
    rename and `git log --follow` keeps working on every file in the tree.

    Every path handed to `git mv` is absolutized first, and so is its `cwd`. A relative
    `state_root` would otherwise be resolved twice — once by the caller's process cwd when
    the operands were built, and again by `cwd=state_root` inside the subprocess — so git
    would be told to move a path that does not exist, fail, and drop silently through to
    the `shutil.move` fallback with exit 0 and no rename recorded. Preserving history via
    `git mv` is the entire reason this function moves directories instead of collapsing
    them, so that degradation must not be silent: the fallback now warns on stderr.

    The move and the epic.yaml status write run under the epic's epic_node_lock. Its lock
    file lives outside the directory being moved (epic_lock_path), so the move cannot carry
    it away from a waiter; every waiter resolves the epic again once it holds the lock, and
    so finds the moved directory. Two movers serialize the same way.
    """
    if to_status not in STATUS_DIRS:
        raise ValueError(f"bad status folder {to_status!r} — expected one of {list(STATUS_DIRS)}")
    state_root = os.path.abspath(state_root)
    if find_epic_dir(state_root, epic_key) is None:          # before any lock file exists
        raise FileNotFoundError(f"epic {epic_key} not found under {state_root}")
    with epic_node_lock(state_root, epic_key):
        return _move_epic_locked(state_root, epic_key, to_status)


def _move_epic_locked(state_root: str, epic_key: str, to_status: str) -> str:
    """move_epic's body; the caller holds the epic's lock and passes an absolute root."""
    src = find_epic_dir(state_root, epic_key)
    if src is None:
        raise FileNotFoundError(f"epic {epic_key} not found under {state_root}")
    src = os.path.abspath(src)
    dest_parent = os.path.join(state_root, to_status)
    dest = os.path.abspath(os.path.join(dest_parent, epic_dirname(epic_key)))
    if src == dest:
        return dest
    if os.path.exists(dest):
        raise FileExistsError(f"destination already exists: {dest}")
    os.makedirs(dest_parent, exist_ok=True)

    moved = False
    reason = "git mv was not attempted"
    try:
        import subprocess
        r = subprocess.run(["git", "mv", src, dest], cwd=state_root,
                           capture_output=True, check=False, text=True)
        moved = r.returncode == 0
        if not moved:
            reason = (r.stderr.strip() or r.stdout.strip()
                      or f"git mv exited {r.returncode}").replace("\n", " ")
    except (OSError, ImportError) as e:
        moved = False
        reason = f"could not run git: {e}"
    if not moved:
        import shutil
        sys.stderr.write(
            f"pm-status.py: WARNING — `git mv` failed ({reason}); falling back to a plain "
            f"filesystem move of {src} -> {dest}. Git will see this as delete+add, not a "
            f"rename, so `git log --follow` will not cross it for these files.\n"
        )
        shutil.move(src, dest)

    p = os.path.join(dest, "epic.yaml")
    if os.path.exists(p):
        y, node = load_node(p)
        if node is not None:
            node["status"] = STATUS_FOR_DIR[to_status]
            node["updated_at"] = _now_iso()
            nodes.save_node(y, node, p)
    return dest


def _story_doc_on_disk(artifacts_root: str, story_key: str):
    """The story's document path, whatever its filename shape, or None.

    `story_doc_path` only ever GENERATES the unslugged name, but the documented artifact
    shape allows an optional trailing slug (`E032-S01-001-centralized-file-config.md`). A
    re-parent must find and move whichever shape is actually there, and must preserve the
    slug across the rename -- the key prefix is canonical, the slug is UX.
    """
    try:
        epic_key, sprint_key, _ = parse_story_key(story_key)
    except ValueError:
        return None
    d = os.path.join(artifacts_root, epic_dirname(epic_key), sprint_dirname(sprint_key),
                     "stories")
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d)):
        if not name.endswith(".md"):
            continue
        # Exactly the key, or the key followed by a slug separator. `startswith(story_key)`
        # alone would also match a longer key sharing this one's prefix, which cannot happen
        # with fixed-width keys today but costs nothing to exclude.
        if name == f"{story_key}.md" or name.startswith(f"{story_key}-"):
            return os.path.join(d, name)
    return None


def _doc_slug(path: str, story_key: str) -> str:
    """The `-slug` part of a story document filename, or '' -- preserved across a re-parent."""
    base = os.path.basename(path)
    stem = base.removesuffix(".md")
    return stem[len(story_key):] if stem.startswith(story_key) else ""


def _rewrite_references(state_root: str, old_key: str, new_key: str) -> None:
    """Repoint every reference to `old_key` at `new_key`.

    A re-key invalidates references the moving node does not own, and they are the half of
    this operation most likely to rot silently: a `depends_on` naming a key that no longer
    exists does not fail until something tries to order it, and a backlog `ref` pointing at
    a vanished story reads as an unlinked promotion in `audit-issues` rather than as damage
    this operation did.

    Two kinds: `depends_on` lists on story nodes, and the two story-key fields on backlog
    items -- `ref` (what fixed it) and `story` (what it is scheduled to) -- in BOTH issue
    files. Both fields in both files, because a resolved entry carries `story` as well
    (`resolve_issue_core` copies every field of the open item), and a `story` left on the
    old key reads as audit finding 1b, whose repair discards the scheduling rather than
    restoring it.
    """
    for _k, _sdir, node, path in _walk_story_nodes(state_root):
        # deps_list, not an isinstance guard: a guard would skip a malformed `depends_on`
        # silently, leaving the stale key behind. reparent_story pre-flights the same check
        # before its first write, so this cannot raise mid-move.
        if old_key in deps_list(node, path):
            y, n = load_node(path)
            n["depends_on"] = [new_key if v == old_key else v for v in deps_list(n, path)]
            nodes.save_node(y, n, path)

    # Either file, not just the open one: a project whose every issue is closed still has
    # resolved refs to repoint. cmd_audit_issues takes no lock when neither exists because
    # it is read-only; this is a write path, so creating the lock file is correct.
    open_path, res_path = issues_paths(state_root)
    if os.path.exists(open_path) or os.path.exists(res_path):
        with issues_lock(open_path):
            store = IssueStore(open_path)
            hit = False
            for lst in (store.backlog, store.resolved):
                for item in lst:
                    if not isinstance(item, dict):
                        continue
                    for field in STORY_REF_FIELDS:
                        if item.get(field) == old_key:
                            item[field] = new_key
                            hit = True
            if hit:
                store.save_open()
                store.save_resolved()


def _raise_sprint_high_water(state_root: str, epic_key: str, sprint_key: str,
                             at_least: int) -> None:
    """Raise a sprint's story-key high-water, so a departing key is never reissued.

    WHY THIS IS NEEDED ON TOP OF THE ALLOCATOR. `_next_story_key`'s high-water only protects
    keys it ISSUED. Every story that exists today predates it, so its sprint carries no
    `next:` at all -- and once such a story moves away, nothing on disk or in the node
    remembers its number and the floor drops back. The departure is the moment we learn the
    key was in use, so that is where it gets recorded.

    Monotonic by construction: it only ever raises. The caller holds the sprint's epic lock,
    because a lost update here WOULD matter -- two concurrent departures raising to 5 and 7
    could leave 5, and 6 would then be reissued to different work.
    """
    spath = sprint_file(state_root, epic_key, sprint_key)
    if spath is None:
        return                                   # no sprint node to record it on
    y, node = load_node(spath)
    if not isinstance(node, dict):
        return
    try:
        stored = int(node.get("next") or 0)
    except (TypeError, ValueError):
        stored = 0
    if stored >= at_least:
        return
    node["next"] = at_least
    nodes.save_node(y, node, spath)


def reparent_story(state_root: str, artifacts_root: str, story_key: str,
                   to_epic: str, to_sprint: str) -> str:
    """Move one planned story to another sprint, re-keying it. Returns the new key.

    BOTH TREES MOVE TOGETHER. The state node and the story document are siblings with an
    identical path suffix, and a re-parent that moved one without the other would break the
    mirror the whole layout depends on. The document may not exist yet (a story planned but
    not elaborated), which is fine; what is not fine is moving one of two that both exist.

    GATE BEFORE WRITE. Everything that can refuse -- scope, existence, destination, key
    availability -- is checked before the first byte moves. `migrate-engine.py` runs its
    completeness checks after the write once, and an empty parse passed vacuously and then
    deleted the source; this orders it the other way for the same reason.

    PLANNED WORK ONLY. A story under `active/` or `archived/` carries actuals, calibration
    samples and `events.jsonl` history keyed to its current key, none of which this moves.
    Refusing is the scope rule, not a limitation to work around.
    """
    state_root = os.path.abspath(state_root)
    artifacts_root = os.path.abspath(artifacts_root)
    from_epic, from_sprint, _ = parse_story_key(story_key)
    to_epic = canonical_epic_key(to_epic)
    to_sprint = canonical_sprint_key(to_sprint)

    # TWO LOCKS, SEQUENTIALLY, NEVER NESTED. `epic_node_lock` refuses to hold two epics at
    # once and that guard is right: its re-entrancy counter is per lock FAMILY rather than per
    # epic, so a nested acquire would silently skip the second flock and hand back the illusion
    # of a lock. Taking them one after the other respects it and needs nothing widened.
    #
    # Phase 1 records the departing key in the SOURCE sprint's high-water. Between the phases
    # another process can only read a source whose high-water is already raised, or race the
    # same move and fail on a missing source -- both safe.
    src_probe = story_file(state_root, from_epic + "-" + from_sprint + "-" + story_key[-3:])
    if src_probe is not None and os.sep + "planned" + os.sep in src_probe + os.sep:
        with epic_node_lock(state_root, from_epic):
            _raise_sprint_high_water(state_root, from_epic, from_sprint,
                                     int(story_key[-3:]) + 1)

    # THE DESTINATION EPIC'S LOCK FOR THE REST.
    #
    # `epic_node_lock` refuses to hold two epics at once, rightly: its re-entrancy counter is
    # per lock FAMILY, so a nested acquire of a second epic would silently skip its flock. The
    # answer is to need less of it. What this operation read-modify-writes is the DESTINATION
    # sprint's allocator; the source epic's `epic.yaml` is untouched and its sprint's `next` is
    # a never-decreasing high-water, and `_require_epic_lock` guards `epic.yaml` writes, of
    # which a re-parent makes none. The source side needs no lock because the move is a single
    # rename: a concurrent second re-parent finds the source gone and fails cleanly.
    with epic_node_lock(state_root, to_epic):
        # --- GATE -------------------------------------------------------------------
        src_node = story_file(state_root, story_key)
        if src_node is None:
            raise PMError(3, f"story {story_key} not found under {state_root}")
        if os.sep + "planned" + os.sep not in src_node + os.sep:
            raise PMError(2, f"{story_key} is not in planned/ — reorg writes planned work "
                             f"only; its actuals, calibration samples and events.jsonl "
                             f"history are keyed to its current key and are not moved")
        dest_sprint_node = sprint_file(state_root, to_epic, to_sprint)
        if dest_sprint_node is None:
            raise PMError(3, f"destination sprint {to_epic}-{to_sprint} does not exist — "
                             f"create it before moving work into it")
        # BOTH ENDS MUST BE PLANNED, not just the source. `sprint_file` resolves through
        # `find_epic_dir`, which searches every bucket, so without this a planned story
        # could be moved INTO an active or archived epic -- past the placement rule, which
        # says an epic's directory lives in the folder named for its status and its stories
        # travel with it. The story would then sit in `archived/` while still reading
        # `status: backlog`, and the next `move-epic` would carry it somewhere nobody chose.
        if os.sep + "planned" + os.sep not in dest_sprint_node + os.sep:
            raise PMError(2, f"destination {to_epic}-{to_sprint} is not in planned/ — reorg "
                             f"writes planned work only, at both ends of a move")
        if (from_epic, from_sprint) == (to_epic, to_sprint):
            return story_key                      # already there; a no-op, not an error

        new_key = _next_story_key(state_root, artifacts_root, to_epic, to_sprint)
        dest_node = os.path.join(os.path.dirname(dest_sprint_node), f"{new_key}.yaml")
        if os.path.exists(dest_node):
            raise PMError(2, f"allocator handed out {new_key} but {dest_node} exists")

        src_doc = _story_doc_on_disk(artifacts_root, story_key)
        dest_doc = None
        if src_doc is not None:
            slug = _doc_slug(src_doc, story_key)
            dest_doc = os.path.join(artifacts_root, epic_dirname(to_epic),
                                    sprint_dirname(to_sprint), "stories",
                                    f"{new_key}{slug}.md")
            if os.path.exists(dest_doc):
                raise PMError(2, f"destination document already exists: {dest_doc}")

        # Every node `_rewrite_references` will read, validated before the first move: it
        # runs after the node and document have been renamed, so a refusal raised there
        # would leave the move half-applied.
        for _k, _sd, _n, _p in _walk_story_nodes(state_root):
            deps_list(_n, _p)

        # --- WRITE ------------------------------------------------------------------
        _git_or_plain_move(src_node, dest_node, state_root)
        if src_doc is not None:
            os.makedirs(os.path.dirname(dest_doc), exist_ok=True)
            _git_or_plain_move(src_doc, dest_doc, artifacts_root)

        from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
        y, node = load_node(dest_node)
        if not isinstance(node, dict):
            raise PMError(2, f"{dest_node} did not parse after the move")
        node["key"] = SQ(new_key)
        node["epic"] = SQ(to_epic)
        node["sprint"] = SQ(to_sprint)
        prev = node.get("previous_keys")
        if not isinstance(prev, list):
            prev = []
        prev.append(story_key)                     # ordered, oldest first; never replaced
        node["previous_keys"] = prev
        node["updated_at"] = _now_iso()
        nodes.save_node(y, node, dest_node)

        if dest_doc is not None:
            _rewrite_doc_key(dest_doc, story_key, new_key)

        _rewrite_references(state_root, story_key, new_key)

        # --- VERIFY -----------------------------------------------------------------
        if story_file(state_root, story_key) is not None:
            raise PMError(2, f"{story_key} still resolves after the move")
        if story_file(state_root, new_key) is None:
            raise PMError(2, f"{new_key} does not resolve after the move")
        return new_key


def _rewrite_doc_key(path: str, old_key: str, new_key: str) -> None:
    """Repoint the story document's frontmatter `key:` at the new key.

    Touches that one field and nothing else: the document is human-authored and everything
    below the frontmatter belongs to its author.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return                                    # a doc we cannot read is not ours to fix
    out = re.sub(rf"^(key:\s*['\"]?){re.escape(old_key)}(['\"]?\s*)$",
                 rf"\g<1>{new_key}\g<2>", text, count=1, flags=re.MULTILINE)
    if out != text:
        core._atomic_text_write(path, out)


def _git_or_plain_move(src: str, dest: str, cwd: str) -> None:
    """`git mv`, falling back to a filesystem move with a LOUD warning.

    Same contract as move_epic's: preserving history is why this moves files rather than
    rewriting them, so a silent degradation to delete+add would defeat the point.
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    moved = False
    reason = "git mv was not attempted"
    try:
        import subprocess
        r = subprocess.run(["git", "mv", os.path.abspath(src), os.path.abspath(dest)],
                           cwd=os.path.abspath(cwd), capture_output=True, check=False,
                           text=True)
        moved = r.returncode == 0
        if not moved:
            reason = (r.stderr.strip() or r.stdout.strip()
                      or f"git mv exited {r.returncode}").replace("\n", " ")
    except (OSError, ImportError) as e:
        reason = f"could not run git: {e}"
    if not moved:
        import shutil
        sys.stderr.write(
            f"pm-status.py: WARNING — `git mv` failed ({reason}); falling back to a plain "
            f"move of {src} -> {dest}. Git will see this as delete+add, not a rename, so "
            f"`git log --follow` will not cross it.\n")
        shutil.move(src, dest)


def dump_plan(state_root: str) -> dict:
    """The planned tree plus its read-only context, as one JSON-able structure.

    WHY THIS VERB EXISTS. The reorg analyzer lives in `l3io-plan`'s own `scripts/` (ADR-0001:
    single-consumer code lives in its skill), and check 26 forbids any file under `skills/`
    from assembling a state path -- `pm-status.py` is the only place that resolves a key to a
    location. So the analyzer cannot walk the tree; it asks for it. One read verb is the whole
    interface between the resolver and every consumer that wants the shape of a plan.

    WHAT IS AND IS NOT INCLUDED. `planned` carries the writable set, with the fields an
    analyzer reasons over: `depends_on`, `estimate`, `classification` and `previous_keys`
    (the last for `l3io-sync`, which needs it to distinguish re-keyed from deleted).
    `active` carries
    only KEYS and their dependencies -- enough to constrain ordering, nothing more, because
    active work is read-only input and a consumer that could see its estimates would be
    tempted to re-plan it. Archived work appears only as keys, for dependency satisfaction.

    Read-only: takes no lock and writes nothing.
    """
    out = {"planned": [], "active": [], "archived": []}
    for bucket, epic_key, epic_dir in iter_epic_dirs(state_root):
        epath = os.path.join(epic_dir, "epic.yaml")
        enode = {}
        if os.path.exists(epath):
            _, n = load_node(epath)
            if isinstance(n, dict):
                enode = n
        if bucket != "planned":
            out[bucket].append({
                "key": epic_key,
                "status": str(enode.get("status") or ""),
                "depends_on": [str(v) for v in deps_list(enode, epath)],
            })
            continue

        epic = {
            "key": epic_key,
            "status": str(enode.get("status") or ""),
            "depends_on": [str(v) for v in deps_list(enode, epath)],
            # Absent when lanes are not in use, which is the normal single-developer state.
            # Consumers cannot read state directly (check 26), so this is the only way the
            # partition reaches plan-graph.py.
            "lane": str(enode["lane"]) if enode.get("lane") is not None else None,
            "estimate": _plain(enode.get("estimate")),
            "sprints": [],
        }
        for sname in sorted(os.listdir(epic_dir)):
            sdir = os.path.join(epic_dir, sname)
            spath = os.path.join(sdir, "sprint.yaml")
            if not os.path.isdir(sdir) or not os.path.exists(spath):
                continue
            _, sn = load_node(spath)
            sn = sn if isinstance(sn, dict) else {}
            sprint = {
                "key": str(sn.get("key") or ""),
                "status": str(sn.get("status") or ""),
                "estimate": _plain(sn.get("estimate")),
                "stories": [],
            }
            for fname in sorted(os.listdir(sdir)):
                if fname == "sprint.yaml" or not fname.endswith(".yaml"):
                    continue
                stpath = os.path.join(sdir, fname)
                _, st = load_node(stpath)
                if not isinstance(st, dict):
                    continue
                sprint["stories"].append({
                    "key": str(st.get("key") or ""),
                    "status": str(st.get("status") or ""),
                    "classification": str(st.get("classification") or ""),
                    # stpath, not spath: a refusal must name the file that holds the defect,
                    # and the sprint.yaml beside it is not where anyone would look.
                    "depends_on": [str(v) for v in deps_list(st, stpath)],
                    # The whole chain, oldest first. `l3io-sync` reads this to tell a
                    # RE-KEYED story from a DELETED one: without it a reorg produces a
                    # `missing_local` for the old key AND an `unmapped_local` for the new,
                    # which pushes as a duplicate issue plus an orphaned one.
                    "previous_keys": [str(v) for v in (st.get("previous_keys") or [])],
                    "estimate": _plain(st.get("estimate")),
                })
            epic["sprints"].append(sprint)
        out["planned"].append(epic)
    return out


def _plain(v):
    """ruamel's CommentedMap/Seq -> plain dict/list/scalar, so json.dumps can take it."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def cmd_dump_plan(args) -> int:
    # COMPACT, and `--pretty` when a human is reading it.
    #
    # Every consumer of this is a script that parses it — the reorg analyzer, the validator,
    # the derivation, and the two plan-run advisories — and it is piped on every plan run.
    # `indent=2` measured 16,895 B against 8,349 B compact on the same 10-epic/40-story tree:
    # 2.09x the raw YAML it came from, versus 1.03x. Same data, half the bytes, and the only
    # thing lost is readability for a person running it by hand, which `--pretty` restores.
    pretty = bool(getattr(args, "pretty", False))
    sep = None if pretty else (",", ":")

    # Through _run_core: dump_plan refuses a malformed `depends_on` (deps_list). Every
    # consumer is a script reading stdout, so a refusal has to be exit 2 with stdout empty
    # -- parseable -- rather than a traceback.
    def run():
        sys.stdout.write(json.dumps(dump_plan(args.state_root),
                                    indent=2 if pretty else None, separators=sep) + "\n")
        return 0
    return _run_core(run)


def retire_epic(state_root: str, epic_key: str, reason: str) -> str:
    """Retire an epic: move it to `archived/` and record why. Returns the destination.

    RETIREMENT IS EPIC-LEVEL, and that is the layout's doing rather than a simplification.
    `planned/`, `active/` and `archived/` are folders of EPIC directories; sprints and stories
    live inside one and have nowhere else to be. There is no place to put a single retired
    story, so there is no verb for it.

    A THIN WRAPPER OVER `move_epic`, deliberately. The move itself -- git mv, the lock, the
    status write -- is already correct there and must not be reimplemented; this adds only the
    two fields that distinguish "retired by a reorg, for this reason" from "archived because it
    finished". Without them an undo could restore the directory but not the fact that a human
    was told why it went.

    NEVER DELETES. The spec is explicit: retire moves, and only an explicit request deletes.
    """
    if not str(reason or "").strip():
        raise PMError(2, "retire-epic requires a --reason: an epic retired without one leaves "
                         "nobody able to judge later whether it should come back")
    dest = move_epic(state_root, epic_key, "archived")
    with epic_node_lock(state_root, epic_key):
        p = os.path.join(dest, "epic.yaml")
        if os.path.exists(p):
            from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
            y, node = load_node(p)
            if isinstance(node, dict):
                node["retired_reason"] = SQ(str(reason).strip())
                node["retired_at"] = SQ(_now_iso())
                nodes.save_node(y, node, p)
    return dest


def cmd_retire_epic(args) -> int:
    try:
        dest = retire_epic(args.state_root, args.epic, args.reason)
    except PMError:
        raise
    except FileNotFoundError as e:
        _die_notfound(str(e))
    except (ValueError, FileExistsError) as e:
        _die_usage(str(e))
    sys.stdout.write(f"OK retire-epic {args.epic} -> {dest}\n")
    return 0


def cmd_reparent_story(args) -> int:
    # Through _run_core, like every other verb: main() has no PMError handler, so a
    # re-raise here would reach the caller as a traceback and exit 1 rather than one stderr
    # line and exit 2. This verb's refusals are usage errors and must read as such.
    def run():
        try:
            new_key = reparent_story(args.state_root, args.artifacts_root, args.story,
                                     args.to_epic, args.to_sprint)
        except FileNotFoundError as e:
            _die_notfound(str(e))
        except (ValueError, FileExistsError) as e:
            _die_usage(str(e))
        sys.stdout.write(f"OK reparent-story {args.story} -> {new_key}\n")
        return 0
    return _run_core(run)


# --------------------------------------------------------------------------------------
# The reorg journal: what was done, why, and enough to put it back.
# --------------------------------------------------------------------------------------

REORG_LOG_FILENAME = "reorg-log.yaml"
_REORG_OP_FIELDS = {
    "reparent-story": {"story", "new_key", "from_epic", "from_sprint",
                       "to_epic", "to_sprint"},
    "retire-epic": {"epic", "reason", "from_status"},
    "create-sprint": {"epic", "sprint"},
}


def reorg_log_path(state_root: str) -> str:
    return os.path.join(state_root, REORG_LOG_FILENAME)


_REORG_LOG_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def reorg_log_lock(state_root: str):
    """Exclusive lock over a whole reorg-log read-modify-write cycle.

    Same reasoning as issues_lock: allocate an id -> append -> save is not atomic, and the
    log is a single shared append target. The log file itself is COMMITTED -- it is the
    traceback record a human reads months later -- so only its `.lock` sidecar is ignored,
    which `_ensure_lock_ignore`'s existing `*.lock` rule already covers.

    NEVER HELD ACROSS A MOVE. `reparent_story` and `move_epic` take `epic_node_lock`, and
    the enforced order is epic-lock-first. `reorg-undo` therefore takes this lock to claim
    an entry, RELEASES it, performs the moves, and takes it again to record the result.
    """
    with _file_lock(reorg_log_path(state_root) + ".lock", _REORG_LOG_LOCK, state_root):
        yield


def plan_shape_hash(state_root: str) -> str:
    """A digest of WHERE planned work sits -- epic, sprint and story placement, nothing else.

    THE GUARD UNDO RESTS ON. An undo computed against a tree that has moved on since the
    reorg would put stories somewhere neither the user nor the journal intended: it replays
    placements derived from a plan that no longer exists. Comparing this digest before acting
    turns that from a silent wrong answer into a refusal.

    PLACEMENT ONLY, DELIBERATELY. Estimates, titles, statuses and dependencies are excluded
    because an undo moves nodes and nothing else -- re-estimating a story between the reorg
    and the undo is ordinary work, and refusing over it would make the guard fire constantly
    for a change it does not care about. Adding or removing a story DOES change placement,
    and that is exactly the case the guard must catch.
    """
    plan = dump_plan(state_root)
    rows = []
    for e in plan.get("planned", []):
        rows.append(f"E\t{e['key']}")
        for sp in e.get("sprints", []):
            rows.append(f"S\t{e['key']}\t{sp['key']}")
            for st in sp.get("stories", []):
                rows.append(f"T\t{e['key']}\t{sp['key']}\t{st['key']}")
    body = "\n".join(sorted(rows))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _load_reorg_log(state_root: str):
    y, node = core._load(reorg_log_path(state_root))
    if not isinstance(node, dict):
        node = {"version": 1, "next": 1, "entries": []}
    node.setdefault("version", 1)
    node.setdefault("next", 1)
    if not isinstance(node.get("entries"), list):
        node["entries"] = []
    return y, node


def _validate_reorg_record(rec) -> list:
    """Every reason to refuse a record. Empty means accept.

    AN OP WE CANNOT INVERT MUST NOT BE JOURNALED. The log's only purpose is to make an undo
    possible, so recording an operation of a kind undo does not understand would hand a user
    an entry that looks undoable and is not. Unknown kinds and missing fields are refusals.
    """
    errs = []
    if not isinstance(rec, dict):
        return ["the record must be a mapping with `rationale`, `pre_hash` and `operations`"]
    if not str(rec.get("rationale") or "").strip():
        errs.append("`rationale` is required and must be the proposal the user accepted, "
                    "verbatim — an entry nobody can read is not a traceback record")
    if not str(rec.get("pre_hash") or "").strip():
        errs.append("`pre_hash` is required — capture it with `reorg-log --hash` BEFORE "
                    "applying the first operation")
    ops = rec.get("operations")
    if not isinstance(ops, list) or not ops:
        errs.append("`operations` must be a non-empty list")
        return errs
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            errs.append(f"operations[{i}]: each operation must be a mapping")
            continue
        kind = str(op.get("op") or "")
        if kind not in _REORG_OP_FIELDS:
            errs.append(f"operations[{i}]: unknown op {kind!r} — undo would not know how to "
                        f"invert it, so journaling it would promise an undo that cannot run")
            continue
        missing = _REORG_OP_FIELDS[kind] - set(op)
        if missing:
            errs.append(f"operations[{i}] ({kind}): missing {sorted(missing)}")
    return errs


def record_reorg(state_root: str, rec: dict) -> str:
    """Append one reorg to the journal. Returns the new entry id."""
    errs = _validate_reorg_record(rec)
    if errs:
        raise PMError(2, "refusing this reorg record:\n  " + "\n  ".join(errs))
    from ruamel.yaml.scalarstring import LiteralScalarString as LS
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
    post = plan_shape_hash(state_root)
    # A block scalar, not an escaped one-liner. The rationale is the proposal a human reads
    # months later to decide whether to undo; `"...\n...\n"` is technically the same text and
    # unreadable in the file it lives in. Block style needs every line to end in one.
    rationale = str(rec["rationale"])
    if "\n" in rationale:
        rationale = LS(rationale if rationale.endswith("\n") else rationale + "\n")
    with reorg_log_lock(state_root):
        y, log = _load_reorg_log(state_root)
        try:
            n = int(log.get("next") or 1)
        except (TypeError, ValueError):
            n = 1
        n = max(n, 1)
        entry_id = f"R{n:04d}"
        log["next"] = n + 1
        log["entries"].append({
            "id": SQ(entry_id),
            "at": SQ(_now_iso()),
            "rationale": rationale,
            "pre_hash": SQ(str(rec["pre_hash"])),
            "post_hash": SQ(post),
            "operations": _plain(rec["operations"]),
        })
        core._atomic_dump(y, log, reorg_log_path(state_root))
    return entry_id


def _find_entry(log: dict, entry_id: str):
    for e in log.get("entries", []):
        if isinstance(e, dict) and str(e.get("id")) == entry_id:
            return e
    return None


def undo_reorg(state_root: str, artifacts_root: str, entry_id: str,
               check_only: bool = False) -> dict:
    """Put a recorded reorg back. Returns a result mapping.

    UNDO IS THE FORWARD PATH RUN BACKWARDS, not a special restore. Each operation is inverted
    with the same `reparent_story` / `move_epic` primitives that applied it, so an undo takes
    the same locks, the same gates and the same git-mv handling. A bespoke restore path would
    be a second implementation of the riskiest code in the file, exercised only in the rare
    case nobody tests by hand.

    REVERSE ORDER, for the same reason the forward order exists: a story that left a retiring
    epic has to come back AFTER that epic is un-archived, or it has nowhere to land.

    KEYS ARE NOT RESTORED, AND CANNOT BE. The allocator's high-water never decreases -- that
    is what stops a freed key being reissued to different work and silently retargeting its
    remote issue. So an undone story returns to its original SPRINT with a new number, and the
    chain of `previous_keys` records the whole journey. Undo restores placement, not keys; the
    result mapping names every key that changed so the caller can say so.

    A CREATED SPRINT IS LEFT STANDING. Undoing it would mean deleting a directory, and
    deletion is the one thing this feature never does unasked. An empty sprint is inert; the
    result reports it so a user can remove it deliberately.
    """
    with reorg_log_lock(state_root):
        y, log = _load_reorg_log(state_root)
        entry = _find_entry(log, entry_id)
        if entry is None:
            raise PMError(3, f"no reorg journal entry {entry_id} in "
                             f"{reorg_log_path(state_root)}")
        if entry.get("undone_at"):
            raise PMError(2, f"{entry_id} was already undone at {entry['undone_at']}")
        if entry.get("undo_started_at") and not check_only:
            raise PMError(2, f"{entry_id} has an undo in flight since "
                             f"{entry['undo_started_at']} — if it failed part way, the "
                             f"journal and `dump-plan` together say how far it got")
        now_hash = plan_shape_hash(state_root)
        want = str(entry.get("post_hash") or "")
        if now_hash != want:
            raise PMError(2,
                          f"refusing to undo {entry_id}: the planned tree has changed since "
                          f"the reorg was applied (recorded {want}, now {now_hash}). An undo "
                          f"replays placements derived from a plan that no longer exists, so "
                          f"it would move work somewhere nobody chose. Re-plan instead.")
        if check_only:
            return {"id": entry_id, "undoable": True, "hash": now_hash,
                    "operations": len(entry.get("operations") or [])}
        from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
        entry["undo_started_at"] = SQ(_now_iso())
        core._atomic_dump(y, log, reorg_log_path(state_root))

    # --- the moves, with NO journal lock held: they take epic locks, which come first ---
    restored, left_standing = {}, []
    for op in reversed(list(entry.get("operations") or [])):
        kind = str(op.get("op") or "")
        if kind == "retire-epic":
            move_epic(state_root, str(op["epic"]), str(op.get("from_status") or "planned"))
            with epic_node_lock(state_root, str(op["epic"])):
                p = nodes.epic_file(state_root, str(op["epic"]))
                if p:
                    ey, en = load_node(p)
                    if isinstance(en, dict):
                        en.pop("retired_reason", None)
                        en.pop("retired_at", None)
                        nodes.save_node(ey, en, p)
        elif kind == "reparent-story":
            back = reparent_story(state_root, artifacts_root, str(op["new_key"]),
                                  str(op["from_epic"]), str(op["from_sprint"]))
            restored[str(op["new_key"])] = back
        elif kind == "create-sprint":
            left_standing.append(f"{op['epic']}-{op['sprint']}")

    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
    after = plan_shape_hash(state_root)
    with reorg_log_lock(state_root):
        y, log = _load_reorg_log(state_root)
        entry = _find_entry(log, entry_id) or {}
        entry["undone_at"] = SQ(_now_iso())
        entry["undo_restored"] = {str(k): SQ(v) for k, v in sorted(restored.items())}
        entry["post_undo_hash"] = SQ(after)
        core._atomic_dump(y, log, reorg_log_path(state_root))
    return {"id": entry_id, "undone": True, "restored": restored,
            "sprints_left_standing": left_standing, "hash": after}


def cmd_reorg_log(args) -> int:
    if args.hash:
        sys.stdout.write(plan_shape_hash(args.state_root) + "\n")
        return 0
    if args.record:
        from ruamel.yaml.error import YAMLError
        y = _yaml()
        try:
            with open(args.record, encoding="utf-8") as fh:
                rec = y.load(fh)
        except FileNotFoundError:
            _die_notfound(f"record file {args.record}")
        except (OSError, UnicodeDecodeError, YAMLError) as e:
            _die_usage(f"could not read the record file {args.record}: {e}")
        entry_id = record_reorg(args.state_root, _plain(rec))
        sys.stdout.write(f"OK reorg-log recorded {entry_id}\n")
        return 0

    _, log = _load_reorg_log(args.state_root)
    entries = [e for e in log.get("entries", []) if isinstance(e, dict)]
    if args.show:
        e = _find_entry(log, args.show)
        if e is None:
            _die_notfound(f"reorg journal entry {args.show}")
        entries = [e]
    if args.format == "json":
        sys.stdout.write(json.dumps({"entries": [_plain(e) for e in entries]},
                                    indent=2) + "\n")
        return 0
    if not entries:
        sys.stdout.write("no reorgs recorded\n")
        return 0
    for e in entries:
        state = "undone" if e.get("undone_at") else "applied"
        sys.stdout.write(f"{e.get('id')}  {e.get('at')}  {state}  "
                         f"{len(e.get('operations') or [])} operation(s)\n")
        if args.show:
            sys.stdout.write("\n" + str(e.get("rationale") or "").rstrip() + "\n\n")
            for op in e.get("operations") or []:
                sys.stdout.write(f"  - {json.dumps(_plain(op), sort_keys=True)}\n")
    return 0


def cmd_reorg_undo(args) -> int:
    try:
        res = undo_reorg(args.state_root, args.artifacts_root, args.id, args.check)
    except PMError:
        raise
    except FileNotFoundError as e:
        _die_notfound(str(e))
    except (ValueError, FileExistsError) as e:
        _die_usage(str(e))
    if args.check:
        sys.stdout.write(f"OK {res['id']} can be undone "
                         f"({res['operations']} operation(s))\n")
        return 0
    sys.stdout.write(f"OK reorg-undo {res['id']} — {len(res['restored'])} story(ies) "
                     f"restored\n")
    for old, new in sorted(res["restored"].items()):
        sys.stdout.write(f"  {old} -> {new}\n")
    if res["sprints_left_standing"]:
        sys.stdout.write("  sprints created by the reorg were left in place (empty, never "
                         "deleted unasked): " + ", ".join(res["sprints_left_standing"]) + "\n")
    return 0


def cmd_move_epic(args) -> int:
    to = getattr(args, "to", None) or "archived"
    try:
        dest = move_epic(args.state_root, args.epic, to)
    except FileNotFoundError as e:
        _die_notfound(str(e))
    except (ValueError, FileExistsError) as e:
        _die_usage(str(e))
    sys.stdout.write(f"OK move-epic {args.epic} -> {to} ({dest})\n")
    return 0


def cmd_list_epics(args) -> int:
    """Enumerate every epic in the state tree with its status bucket.

    Read-only. A missing state root prints nothing and exits 0 -- the shape of a
    project with no state yet, which is the same silent shape the old
    `ls -d ... 2>/dev/null` probe gave callers.

    --format keys (default): one E{nnn} per line, sorted, buckets flattened. Cheap.
    --format json: a list of {key, bucket, status}, sorted by (bucket, key) with
    STATUS_DIRS order preserved so active/planned/archived is a stable read.
    """
    rows = list(iter_epic_dirs(args.state_root))
    if args.format == "json":
        out = [{"key": k, "bucket": b, "status": STATUS_FOR_DIR[b]} for b, k, _ in rows]
        sys.stdout.write(json.dumps(out) + "\n")
    else:
        for _b, k, _p in rows:
            sys.stdout.write(f"{k}\n")
    return 0


def cmd_list_stories(args) -> int:
    """Enumerate story keys for an epic, optionally scoped to one sprint.

    Read-only. A missing epic exits 3 -- absent-vs-empty matters for the caller,
    and the resolver already distinguishes them. A sprint that does not exist
    yields nothing and exits 0: a project can ask about a sprint it has not
    created yet, and the answer is not an error, it is an empty list.

    Filters out sprint.yaml/epic.yaml and anything whose name does not parse as
    a story key -- callers get story keys, no post-processing required.
    """
    if find_epic_dir(args.state_root, args.epic) is None:
        _die_notfound(f"epic {args.epic}")
    sprint = args.sprint if args.sprint else None
    rows = list(iter_story_files(args.state_root, args.epic, sprint))
    if args.format == "json":
        out = []
        for k, _p in rows:
            _e, sk, _ = parse_story_key(k)
            out.append({"key": k, "sprint": sk})
        sys.stdout.write(json.dumps(out) + "\n")
    else:
        for k, _p in rows:
            sys.stdout.write(f"{k}\n")
    return 0


def cmd_show(args) -> int:
    """Render a computed sprint or epic roll-up. Exits 3 if the epic (or,
    when --sprint is given, that sprint within it) does not resolve — an
    empty roll-up must never be printed for a node that doesn't exist."""
    d = find_epic_dir(args.state_root, args.epic)
    if d is None:
        _die_notfound(f"epic {args.epic}")

    if args.sprint:
        sd = os.path.join(d, sprint_dirname(args.sprint))
        if not os.path.isdir(sd):
            _die_notfound(f"epic {args.epic} sprint {args.sprint}")
        r = rollup_sprint(args.state_root, args.epic, args.sprint)
        # Cosmetic wart named in the design (§13): a sprint whose stories are
        # ALL blocked reads as "actively being worked" when its status is
        # still in-progress. Surface it in the header rather than promote it to
        # a status transition (that would need its own transition table).
        header_status = r["status"]
        n_blocked = r.get("blocked_stories", 0)
        if n_blocked and n_blocked == r["story_count"] and r["story_count"] > 0:
            header_status = f"{r['status']} (all {n_blocked} stories blocked)"
        sys.stdout.write(f"{args.epic}/{r['key']}  status={header_status}  "
                         f"stories={r['story_count']}\n")
        for s in r["stories"]:
            suffix = ""
            if s["status"] == "blocked":
                reason = s.get("blocked_reason", "")
                suffix = f"  [blocked: {reason}]" if reason else "  [blocked]"
            sys.stdout.write(f"  {s['key']:<20} {s['status']}{suffix}\n")
        sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
        _write_spend(r["spend"])
        return 0

    r = rollup_epic(args.state_root, args.epic)
    sys.stdout.write(f"{r['key']}  status={r['status']}  sprints={r['sprint_count']}  "
                     f"stories={r['story_count']}\n")
    for sp in r["sprints"]:
        sys.stdout.write(f"  {sp['key']:<8} status={sp['status']:<12} stories={sp['story_count']}\n")
    sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
    n_blocked = r.get("blocked_stories", 0)
    if n_blocked > 0:
        cumul = r.get("blocks_seen_cumulative", 0)
        cumul_note = f", {cumul} cumulative block events" if cumul else ""
        sys.stdout.write(f"  blocked_stories: {n_blocked}{cumul_note}\n")
    _write_spend(r["spend"])
    return 0


def cmd_verify(args) -> int:
    kind = args.scope  # story | sprint | epic
    if kind == "epic":
        _y, node, _path, label = _load_checked(args.state_root, args, kind)
        failures: list[str] = []
        for sd in list_sprint_dirs(args.state_root, args.epic):
            skey = _sprint_key_from_dir(sd)
            sp = sprint_file(args.state_root, args.epic, skey)
            if sp is None:
                failures.append(f"{skey}: sprint.yaml missing")
            else:
                _, snode = load_node(sp)
                failures += [f"{skey}: {p}" for p in check_backrefs(snode, args.epic)]
            for stf in list_story_files(args.state_root, args.epic, skey):
                _, stnode = load_node(stf)
                if stnode is None:
                    failures.append(f"{os.path.basename(stf)}: empty")
                    continue
                failures += [f"{stnode.get('key', '?')}: {p}"
                             for p in check_backrefs(stnode, args.epic, skey)]
        if failures:
            for f in failures:
                sys.stderr.write(f"FAIL {f}\n")
            return 4
        sys.stdout.write(f"PASS epic {args.epic}\n")
        return 0

    _y, node, _path, label = _load_checked(args.state_root, args, kind)

    problems: list[str] = []
    if node.get("status") != "done":
        problems.append(f"status={node.get('status')!r} (expected done)")

    actual = node.get("actual") or {}
    required = list(METRIC_FIELDS)
    for m in required:
        if m not in actual:
            problems.append(f"actual.{m} absent")
            continue
        val = actual[m]
        # Numeric fields must be numeric; token/cost may be N/A only under non-claude runtime.
        if m in ("elapsed_hours", "man_hours", "hitl_hours"):
            if _is_na(val) or not _is_number(val):
                problems.append(f"actual.{m}={val!r} (must be numeric)")
        else:  # tokens_k, cost
            if _is_na(val):
                copilot_cost_na = (args.runtime == "copilot" and m == "cost")
                if not copilot_cost_na and (
                    args.require_tokens or args.runtime in ("claude", "codex", "copilot")
                ):
                    problems.append(
                        f"actual.{m}=N/A (forbidden under runtime={args.runtime} "
                        f"/ --require-tokens)")

    # tokens_k, once structured, is self-verifying: its total must equal the sum
    # of its four classes, and its cost must equal what those tokens price out to
    # under its own recorded model. A hand-edited cost is exactly the failure
    # this closes — without it, a bogus number survives in committed state
    # indefinitely because nothing ever recomputes it.
    tk = actual.get("tokens_k")
    if hasattr(tk, "get"):
        parts = sum(_num_or_none(tk.get(c)) or 0.0 for c in TOKEN_CLASSES)
        total = _num_or_none(tk.get("total"))
        # Unlike cost (below), total and parts are NOT on the same rounding grid:
        # `total` was rounded to 2dp once at write time (tokens_block), but
        # `parts` here is an unrounded re-sum of the class values. That write-time
        # rounding alone can separate a legitimate total from its exact sum by up
        # to half the last decimal place (0.005) with no error involved at all —
        # so tightening this to cost's 0.005 would risk failing correctly-rounded
        # data. 0.01 keeps a safe margin above that rounding noise while still
        # catching any genuine (typically integer-scale, since counts are whole
        # thousands of tokens) divergence.
        if total is None or abs(total - parts) > 0.01:
            problems.append(f"actual.tokens_k.total={total!r} != sum of classes ({parts})")
        model = actual.get("model")
        if not model:
            problems.append("actual.model absent (cost cannot be verified)")
        else:
            try:
                expect = cost_from_tokens(tk, str(model), rate_overrides(args))
            except KeyError as e:
                # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
                # which would double-wrap a message that already reads as prose.
                problems.append(e.args[0])
            else:
                got = _num_or_none(actual.get("cost"))
                # Both got and expect are already rounded to cents (the smallest
                # unit either can carry), so the smallest genuine divergence is
                # exactly one cent (0.01). A tolerance of 0.01 would not fire on
                # it — the tolerance would be exactly the size of the error it
                # exists to catch. Half the discrete unit still absorbs true
                # float-summation noise (~1e-9 to 1e-14) with enormous margin
                # while catching any one-cent divergence.
                if got is None or abs(got - expect) > 0.005:
                    problems.append(f"actual.cost={got!r} != derived {expect} "
                                    f"for model {model}")
    elif "tokens_k" in actual and not _is_na(tk):
        # A bare scalar tokens_k has no class split, so the cost invariant above
        # cannot run at all — `tokens_k: 500` next to `cost: 9999.99` used to
        # return PASS. Design §4.3 says a hand-edited cost cannot survive verify;
        # keeping the pre-rework scalar shape was a one-line way around it. The
        # scalar form stays legitimate under runtime=other (set-estimate writes
        # it, and a runtime with no per-class visibility has nothing better), so
        # this fires only where exact per-class capture is required.
        if args.require_tokens or args.runtime in ("claude", "codex"):
            problems.append(
                f"actual.tokens_k={tk!r} is not the per-class mapping — cost cannot be "
                f"verified against it. Re-capture with set-actual "
                f"--tokens-input/--tokens-output/--tokens-cache-write/--tokens-cache-read "
                f"and --model (metrics-contract.md §3)")

    if kind == "story" and "completion_evidence" not in node:
        problems.append("completion_evidence absent")

    est_model = (node.get("estimate") or {}).get("model")
    act_model = actual.get("model")
    if est_model and act_model and est_model != act_model:
        sys.stdout.write(
            f"WARN {label}: estimate.model={est_model!r} ≠ actual.model={act_model!r}"
            f" — estimate cost denominated in {est_model} rates\n"
        )
    if problems:
        sys.stdout.write(f"FAIL {label}: " + "; ".join(problems) + "\n")
        return 4
    sys.stdout.write(f"PASS {label}\n")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pm-status.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def node_args(sp):
        sp.add_argument("--story", help="story key (addresses a story node)")
        sp.add_argument("--epic", help="zero-paddable epic id")
        sp.add_argument("--sprint", help="zero-paddable sprint id")

    s = sub.add_parser("set-status", help="set a node's status atomically")
    s.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    node_args(s)
    s.add_argument("--status", required=True)
    s.add_argument("--title")
    s.add_argument("--reason", default="",
                   help="required when --status blocked; free-text why the story halted. "
                        "Rejected on any other status (a --reason for review would only "
                        "confuse the record).")
    s.add_argument("--resolution", default="",
                   help="required when a story transitions blocked -> done; free-text "
                        "why the story shipped as-is rather than resumed (e.g. \"spec "
                        "change removed the need for this story\").")
    s.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    s.add_argument("--no-events", dest="no_events", action="store_true",
                   help="skip the events.jsonl append for this call")
    s.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
    s.set_defaults(func=cmd_set_status)

    sd = sub.add_parser("sync-story-doc",
                        help="write status into the story markdown's frontmatter")
    sd.add_argument("--artifacts-root", required=True,
                    help="implementation_artifacts root (NOT the state root)")
    sd.add_argument("--story", required=True)
    sd.add_argument("--status", required=True)
    sd.add_argument("--quiet", action="store_true")
    sd.set_defaults(func=cmd_sync_story_doc)

    di = sub.add_parser("story-doc-init",
                        help="create a story document skeleton from its state node")
    di.add_argument("--state-root", required=True)
    di.add_argument("--artifacts-root", required=True,
                    help="implementation_artifacts root (NOT the state root)")
    di.add_argument("--story", required=True)
    di.set_defaults(func=cmd_story_doc_init)

    sdo = sub.add_parser("set-depends-on",
                         help="add or remove dependency keys on an epic or story node's depends_on list")
    sdo.add_argument("--state-root", required=True)
    sdo.add_argument("--epic")
    sdo.add_argument("--story", help="a story node's depends_on takes story keys")
    sdo.add_argument("--sprint")
    sdo.add_argument("--add", action="append", metavar="KEY",
                     help="repeatable; idempotent, order preserved. Epic keys for an epic "
                          "node, story keys for a story node")
    sdo.add_argument("--remove", action="append", metavar="KEY",
                     help="repeatable; idempotent. Refused while story edges still cross "
                          "that boundary, unless --force")
    sdo.add_argument("--force", action="store_true",
                     help="remove even while story edges justify it — for a sequencing "
                          "decision no story edge expresses")
    sdo.set_defaults(func=cmd_set_depends_on)

    imp = sub.add_parser("import-node",
                         help="create a state node from a migration record")
    imp.add_argument("--state-root", required=True)
    imp.add_argument("--epic")
    imp.add_argument("--sprint")
    imp.add_argument("--story")
    imp.add_argument("--status", required=True)
    imp.add_argument("--title", default="")
    imp.add_argument("--classification", default="unknown")
    imp.add_argument("--origin", choices=["inferred"],
                     help="mark the node as reconstructed rather than read")
    imp.add_argument("--origin-note", default="",
                     help="why the node was inferred; recorded beside --origin")
    imp.add_argument("--reason", default="",
                     help="required when importing a story at --status blocked; "
                          "recorded on the node as blocked_reason and in the paired "
                          "block_open event so a future exit-from-blocked can derive "
                          "duration. Rejected on any other kind or status.")
    imp.add_argument("--no-events", action="store_true")
    imp.add_argument("--session-id")
    imp.set_defaults(func=cmd_import_node)

    a = sub.add_parser("set-actual", help="write a validated actual block")
    a.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    a.add_argument("--node", required=True, choices=["story", "sprint", "epic"])
    node_args(a)
    a.add_argument("--block", choices=["actual", "orchestration"], default="actual",
                   help="which metric block to write (orchestration: sprint/epic only)")
    a.add_argument("--elapsed-hours", dest="elapsed_hours")
    a.add_argument("--man-hours", dest="man_hours")
    a.add_argument("--hitl-hours", dest="hitl_hours",
                   help="human attention actually spent supervising (hours)")
    a.add_argument("--tokens-input", dest="tokens_input")
    a.add_argument("--tokens-output", dest="tokens_output")
    a.add_argument("--tokens-cache-write", dest="tokens_cache_write")
    a.add_argument("--tokens-cache-read", dest="tokens_cache_read")
    a.add_argument("--tokens-na", dest="tokens_na", action="store_true",
                   help="record tokens/cost as N/A (runtime=other only)")
    a.add_argument("--model", default="", help="model id that priced these tokens")
    a.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    a.add_argument("--cost", default=None, help=argparse.SUPPRESS)
    a.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")
    a.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    a.add_argument("--no-calibrate", dest="no_calibrate", action="store_true",
                   help="skip calibration sampling (backfills, replays)")
    a.add_argument("--no-events", dest="no_events", action="store_true",
                   help="skip the events.jsonl append for this call")
    a.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
    a.set_defaults(func=cmd_set_actual)

    ia = sub.add_parser("import-actual",
                        help="record an actual observed elsewhere (migration); runtime=other, "
                             "tokens=N/A and no calibration sample are FIXED, not optional")
    ia.add_argument("--state-root", required=True)
    ia.add_argument("--node", required=True, choices=["story", "sprint", "epic"])
    ia.add_argument("--story")
    ia.add_argument("--epic")
    ia.add_argument("--sprint")
    ia.add_argument("--elapsed-hours", dest="elapsed_hours")
    ia.add_argument("--man-hours", dest="man_hours")
    ia.add_argument("--hitl-hours", dest="hitl_hours")
    ia.add_argument("--flock", action="store_true")
    ia.add_argument("--no-events", dest="no_events", action="store_true")
    ia.add_argument("--session-id", dest="session_id", default=None)
    ia.set_defaults(func=cmd_import_actual)

    v = sub.add_parser("verify", help="read-back gate; nonzero exit on any gap")
    v.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    v.add_argument("--scope", required=True, choices=["story", "sprint", "epic"])
    node_args(v)
    v.add_argument("--require-tokens", action="store_true")
    v.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")
    v.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    v.set_defaults(func=cmd_verify)

    le = sub.add_parser("list-epics",
                        help="list every epic key in the state tree with its status bucket")
    le.add_argument("--state-root", required=True)
    le.add_argument("--format", choices=["keys", "json"], default="keys")
    le.set_defaults(func=cmd_list_epics)

    ls_ = sub.add_parser("list-stories",
                         help="list story keys for an epic, optionally scoped to one sprint")
    ls_.add_argument("--state-root", required=True)
    ls_.add_argument("--epic", required=True)
    ls_.add_argument("--sprint", default="")
    ls_.add_argument("--format", choices=["keys", "json"], default="keys")
    ls_.set_defaults(func=cmd_list_stories)

    sh = sub.add_parser("show", help="render a computed sprint or epic roll-up")
    sh.add_argument("--state-root", required=True)
    sh.add_argument("--epic", required=True)
    sh.add_argument("--sprint", default="")
    sh.set_defaults(func=cmd_show)

    rp = sub.add_parser("report", help="plan-aware progress report (read-only unless --out)")
    rp.add_argument("--state-root", required=True)
    rp.add_argument("--plan", default="", help="path to plan-output-meta.yaml")
    rp.add_argument("--format", choices=["tree", "json", "md"], default="tree")
    rp.add_argument("--out", default="", help="write to this file instead of stdout")
    rp.add_argument("--all", action="store_true",
                    help="show every status folder (sugar for --status planned,active,archived)")
    rp.add_argument("--status", default="",
                    help="comma list of state folders to display: planned, active, archived "
                         "(default: planned,active). Counting is unaffected — phase "
                         "denominators always see the whole tree")
    rp.add_argument("--watch", type=int, default=0, metavar="SECS",
                    help="re-render on an interval (tree only in practice)")
    rp.add_argument("--stall-minutes", dest="stall_minutes", type=float,
                    default=DEFAULT_STALL_MINUTES,
                    help="flag dispatches open longer than this (default 15)")
    rp.set_defaults(func=cmd_report)

    dp = sub.add_parser("dispatch", help="record a subagent dispatch open/close")
    dp.add_argument("--state-root", required=True)
    dp.add_argument("--event", required=True, choices=["open", "close"])
    dp.add_argument("--agent", required=True)
    dp.add_argument("--epic", default="")
    dp.add_argument("--sprint", default="")
    dp.add_argument("--story", default="")
    dp.add_argument("--session-id", dest="session_id", default=None)
    dp.set_defaults(func=cmd_dispatch)

    si = sub.add_parser("self-install", help="install this package as pm-status/ beside --dest, content-guarded")
    si.add_argument("--dest", required=True, help="target path, e.g. {project-root}/_bmad/scripts/pm-status.py")
    si.add_argument("--force", action="store_true", help="overwrite even if dest is same/newer")
    si.set_defaults(func=cmd_self_install)

    sl = sub.add_parser("set-lock", help="write _lock block to a per-epic active file")
    sl.add_argument("--state-root", required=True)
    sl.add_argument("--epic", required=True, help="epic key, e.g. E001")
    sl.add_argument("--session-id", dest="session_id", required=True)
    sl.add_argument("--ttl-minutes", dest="ttl_minutes", type=int, default=30)
    sl.set_defaults(func=cmd_set_lock)

    cl = sub.add_parser("clear-lock", help="remove _lock block from a per-epic active file")
    cl.add_argument("--state-root", required=True)
    cl.add_argument("--epic", required=True, help="epic key, e.g. E001")
    cl.set_defaults(func=cmd_clear_lock)

    ck = sub.add_parser("check-lock", help="check if a per-epic file is free to claim; exit 5 if held")
    ck.add_argument("--state-root", required=True)
    ck.add_argument("--epic", required=True, help="epic key, e.g. E001")
    ck.add_argument("--session-id", dest="session_id", required=True, help="caller's session id")
    ck.set_defaults(func=cmd_check_lock)

    se = sub.add_parser("set-estimate", help="write estimate block to a story, sprint, or epic node")
    se.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    node_args(se)
    # Range fields (sprint/epic)
    se.add_argument("--man-hours-low", dest="man_hours_low")
    se.add_argument("--man-hours-high", dest="man_hours_high")
    se.add_argument("--hitl-hours-low", dest="hitl_hours_low")
    se.add_argument("--hitl-hours-high", dest="hitl_hours_high")
    se.add_argument("--elapsed-hours-low", "--time-hours-low", dest="elapsed_hours_low")
    se.add_argument("--elapsed-hours-high", "--time-hours-high", dest="elapsed_hours_high")
    se.add_argument("--tokens-k-min", dest="tokens_k_min")
    se.add_argument("--tokens-k-max", dest="tokens_k_max")
    # --cost / --cost-low / --cost-high are declared but SUPPRESSed from --help
    # and rejected in cmd_set_estimate: cost is derived from tokens x rates,
    # never accepted as direct input (see the rejection at the top of
    # cmd_set_estimate). Declaring them here — rather than leaving them
    # unrecognized — turns that rejection into a clear usage error instead of
    # argparse's generic "unrecognized arguments".
    se.add_argument("--cost-low", dest="cost_low", help=argparse.SUPPRESS)
    se.add_argument("--cost-high", dest="cost_high", help=argparse.SUPPRESS)
    # Single-value fields (story)
    se.add_argument("--man-hours", dest="man_hours")
    se.add_argument("--hitl-hours", dest="hitl_hours",
                    help="human attention actually spent supervising (hours)")
    se.add_argument("--elapsed-hours", "--time-hours", dest="elapsed_hours",
                    help="--time-hours is a deprecated alias")
    se.add_argument("--tokens-k", dest="tokens_k_min")  # alias to tokens_k_min for story use
    se.add_argument("--cost", dest="cost", help=argparse.SUPPRESS)
    se.add_argument("--confidence", choices=["low", "medium", "high"])
    se.add_argument("--fix-factor", dest="fix_factor",
                    help="fix multiplier applied; required for the scope/fix split")
    se.add_argument("--scope-ratio", dest="scope_ratio",
                    help="calibrated scope ratio applied (1.0 when cold-start)")
    se.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    se.set_defaults(func=cmd_set_estimate)

    sf = sub.add_parser("set-field", help="set a nested field at a dot-path within a node")
    sf.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    node_args(sf)
    sf.add_argument("--field", required=True, help="dot-path within the node, e.g. 'retrospective.summary'")
    sf.add_argument("--value", required=True, help="string value to set")
    sf.set_defaults(func=cmd_set_field)

    a = sub.add_parser("add-test-run", help="record one executed test command and its exit code")
    a.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    a.add_argument("--story", required=True)
    a.add_argument("--command", required=True, help="the test command actually executed")
    a.add_argument("--exit-code", dest="exit_code", type=int, required=True)
    a.set_defaults(func=cmd_add_test_run)

    ai = sub.add_parser("append-issue", help="append a BL item to state/issues.yaml")
    ai.add_argument("--state-root", dest="state_root", default="",
                    help="path to {implementation_artifacts}/state (preferred)")
    ai.add_argument("--file", default="",
                    help="compatibility alias for <state-root>/issues.yaml")
    ai.add_argument("--session-id", dest="session_id", default=None)
    ai.add_argument("--key", default="",
                    help="BL-E{nnn}-{nnn}; omit to auto-allocate the next number for "
                         "--epic under a lock. An explicit key that already exists "
                         "exits 2 rather than being silently reassigned.")
    ai.add_argument("--epic", required=True, help="zero-padded epic number, e.g. '001'")
    ai.add_argument("--sprint", default="", help="zero-padded sprint number; empty for epic-level")
    ai.add_argument("--title", required=True)
    ai.add_argument("--source", default=None,
                    help="free-text source, stored verbatim (legacy form; prefer --source-phase)")
    ai.add_argument("--source-phase", dest="source_phase", default=None,
                    help="structured source: the phase, e.g. code-review. With --source-ref it "
                         "DERIVES --source as '{phase} ({ref})', so the two cannot disagree")
    ai.add_argument("--source-ref", dest="source_ref", default=None,
                    help="structured source: the finding or story it points at; no parentheses")
    ai.add_argument("--source-note", dest="source_note", default="",
                    help="structured source: free text appended after the parens")
    ai.add_argument("--severity", required=True, choices=["Low", "Medium", "High", "Critical"])
    ai.add_argument("--description", default="")
    ai.add_argument("--kind", default="defect", choices=list(ISSUE_KINDS),
                    help="defect (default, not written) | spec-change | spec-proposal")
    ai.add_argument("--ref", default="",
                    help="spec kinds only: the docs(spec) commit SHA, or the proposal path")
    ai.add_argument("--allow-duplicate", dest="allow_duplicate", action="store_true",
                    help="append even if an existing item matches this title+epic+"
                         "sprint+source (default: skip and exit 0)")
    ai.set_defaults(func=cmd_append_issue)

    ri = sub.add_parser("resolve-issue",
                        help="resolve an open BL item into issues-resolved.yaml")
    ri.add_argument("--state-root", required=True)
    ri.add_argument("--key", required=True)
    ri.add_argument("--resolution", required=True, choices=list(RESOLUTIONS))
    ri.add_argument("--ref", default=None)
    ri.add_argument("--note", default=None)
    ri.add_argument("--session-id", dest="session_id", default=None)
    ri.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    ri.set_defaults(func=cmd_resolve_issue)

    ui = sub.add_parser("update-issue", help="change an open BL item's severity")
    ui.add_argument("--state-root", required=True)
    ui.add_argument("--key", required=True)
    ui.add_argument("--severity", required=True, choices=["Low", "Medium", "High", "Critical"])
    ui.add_argument("--note", default=None)
    ui.add_argument("--session-id", dest="session_id", default=None)
    ui.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    ui.set_defaults(func=cmd_update_issue)

    pi = sub.add_parser("promote-issue", help="turn open BL items into a new estimated story")
    pi.add_argument("--state-root", required=True)
    pi.add_argument("--artifacts-root", required=True,
                    help="implementation_artifacts root (NOT the state root)")
    pi.add_argument("--key", required=True, action="append", help="repeatable")
    pi.add_argument("--epic", required=True)
    pi.add_argument("--sprint", required=True)
    pi.add_argument("--classification", required=True, choices=list(CLASSIFICATIONS))
    pi.add_argument("--title", default="")
    pi.add_argument("--model", default="")
    pi.add_argument("--token-rates", dest="token_rates", default="")
    pi.add_argument("--session-id", dest="session_id", default=None)
    pi.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    pi.set_defaults(func=cmd_promote_issue)

    si = sub.add_parser("schedule-issue",
                        help="attach open BL items to a story that already exists")
    si.add_argument("--state-root", required=True)
    si.add_argument("--key", required=True, action="append", help="repeatable")
    si.add_argument("--story", required=True, help="an existing story key E{nnn}-S{nn}-{nnn}")
    si.add_argument("--session-id", dest="session_id", default=None)
    si.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    si.set_defaults(func=cmd_schedule_issue)

    au = sub.add_parser("audit-issues", help="structural integrity checks over the backlog")
    au.add_argument("--state-root", required=True)
    au.add_argument("--format", choices=["text", "json"], default="text")
    au.set_defaults(func=cmd_audit_issues)

    rp = sub.add_parser("repair-issue", help="structural repair gated on an audit-issues finding")
    rp.add_argument("--state-root", required=True)
    rp.add_argument("--key", default=None,
                    help="the item; for reseed, any key of the epic; omit with --all-legacy")
    rp.add_argument("--action", required=True,
                    choices=["unschedule", "link", "repoint", "reseed", "reopen",
                             "normalize-status", "normalize-keys"])
    rp.add_argument("--story", default=None, help="with --action link")
    rp.add_argument("--all-legacy", dest="all_legacy", action="store_true",
                    help="with --action normalize-status: every legacy status in one pass")
    rp.add_argument("--session-id", dest="session_id", default=None)
    rp.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    rp.set_defaults(func=cmd_repair_issue)

    li = sub.add_parser("list-issues", help="list (with filters) open BL items, resolved ones "
                                            "(--resolved), or both (--all, JSON)")
    li.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    li.add_argument("--epic", help="epic id — accepts 'E001' or '001'")
    li.add_argument("--sprint", help="sprint id — accepts 'S01' or '01'; never matches an epic-level (empty-sprint) item")
    li.add_argument("--severity", action="append", choices=["Low", "Medium", "High", "Critical"],
                    help="filter by severity; repeat to OR multiple severities")
    li.add_argument("--format", choices=["text", "json"], default="text")
    li.add_argument("--status", choices=["backlog", "scheduled"],
                    help="open items with this status")
    li.add_argument("--resolved", action="store_true", help="list issues-resolved.yaml instead")
    li.add_argument("--resolution", choices=list(RESOLUTIONS), help="with --resolved only")
    li.add_argument("--kind", choices=list(ISSUE_KINDS),
                    help="items of this kind; an item without `kind` is a defect")
    li.add_argument("--all", action="store_true",
                    help='JSON {"open": [...], "resolved": [...]} read under one lock')
    li.set_defaults(func=cmd_list_issues)

    mv = sub.add_parser("move-epic", help="move an epic directory between status folders")
    mv.add_argument("--state-root", required=True)
    mv.add_argument("--epic", required=True)
    mv.add_argument("--to", required=True, choices=list(STATUS_DIRS))
    mv.set_defaults(func=cmd_move_epic)

    ae = sub.add_parser("archive-epic", help="alias for move-epic --to archived")
    ae.add_argument("--state-root", required=True)
    ae.add_argument("--epic", required=True)
    ae.set_defaults(func=cmd_move_epic, to="archived")

    up = sub.add_parser("usage", help="sum a session transcript's token usage, by class")
    up.add_argument("transcript", nargs="*",
                    help="transcript .jsonl file(s) or directory(ies); omit to resolve this "
                         "session's own transcript from $" + CLAUDE_SESSION_ENV)
    up.add_argument("--claude-session", dest="claude_session", default="",
                    help="the Claude session id the transcript must belong to (NOT the l3io "
                         "run --session-id); defaults to $" + CLAUDE_SESSION_ENV)
    up.add_argument("--state-root", default="", help="state root, to read events.jsonl")
    up.add_argument("--agent", default="", help="scope to this agent's dispatch bracket")
    up.add_argument("--epic", default="", help="scope to this epic")
    up.add_argument("--sprint", default="", help="scope to this sprint")
    up.add_argument("--story", default="", help="scope to this story")
    up.add_argument("--since", default="", help="ISO timestamp lower bound")
    up.add_argument("--until", default="", help="ISO timestamp upper bound")
    up.add_argument("--allow-unidentified", action="store_true",
                    help="sum a file that cannot be confirmed as this session's transcript")
    up.add_argument("--model", default="", help="also price the total at this model's rates")
    up.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON overrides for the rate table")
    up.add_argument("--format", choices=["text", "json"], default="text")
    up.set_defaults(func=cmd_usage)

    cal = sub.add_parser("calibration", help="inspect the calibration file")
    cal.add_argument("action", choices=["show", "migrate-metrics", "redrive"])
    cal.add_argument("--state-root", required=True)
    cal.add_argument("--format", choices=["text", "json"], default="text")
    cal.set_defaults(func=cmd_calibration)

    es = sub.add_parser("estimate-story", help="compute and write a story estimate")
    es.add_argument("--state-root", required=True)
    es.add_argument("--story", required=True)
    es.add_argument("--classification", required=True, choices=list(CLASSIFICATIONS))
    es.add_argument("--confidence", choices=["low", "medium", "high"])
    es.add_argument("--model", default="",
                    help="model id to price the derived cost; falls back to DEFAULT_ESTIMATE_MODEL")
    es.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    es.set_defaults(func=cmd_estimate_story)

    er = sub.add_parser("estimate-rollup", help="roll child estimates up to a sprint or epic")
    er.add_argument("--state-root", required=True)
    er.add_argument("--epic", required=True)
    er.add_argument("--sprint", default="")
    er.add_argument("--model", default="",
                    help="model id to price the derived cost; falls back to DEFAULT_ESTIMATE_MODEL")
    er.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    er.set_defaults(func=cmd_estimate_rollup)

    rt = sub.add_parser("rates", help="print the effective token rate table (read-only)")
    rt.add_argument("--model", default="")
    rt.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    rt.set_defaults(func=cmd_rates)

    ar = sub.add_parser("adr-reserve",
                        help="reserve N sequential ADR numbers under a lock, before dispatch")
    ar.add_argument("--state-root", required=True)
    ar.add_argument("--epic", required=True)
    ar.add_argument("--slug", required=True)
    ar.add_argument("--count", type=int, default=1)
    ar.add_argument("--adr-dir", dest="adr_dir", default="",
                    help="the one ADR home to scan (default: <git top-level>/docs/adr)")
    ar.set_defaults(func=cmd_adr_reserve)

    dp = sub.add_parser("dump-plan",
                        help="the planned tree plus read-only context, as JSON (read-only)")
    dp.add_argument("--state-root", required=True)
    dp.add_argument("--pretty", action="store_true",
                    help="indent the JSON for reading by hand; the default is compact, "
                         "which halves the bytes every consumer pipes")
    dp.set_defaults(func=cmd_dump_plan)

    re_ = sub.add_parser("retire-epic",
                         help="move an epic to archived/ and record why (never deletes)")
    re_.add_argument("--state-root", required=True)
    re_.add_argument("--epic", required=True)
    re_.add_argument("--reason", required=True)
    re_.set_defaults(func=cmd_retire_epic)

    rp = sub.add_parser("reparent-story",
                        help="move a planned story to another sprint, re-keying it")
    rp.add_argument("--state-root", required=True)
    rp.add_argument("--artifacts-root", required=True)
    rp.add_argument("--story", required=True)
    rp.add_argument("--to-epic", required=True)
    rp.add_argument("--to-sprint", required=True)
    rp.set_defaults(func=cmd_reparent_story)

    rl = sub.add_parser("reorg-log",
                        help="the reorg journal: hash the plan, record a reorg, list or show")
    rl.add_argument("--state-root", required=True)
    rl.add_argument("--hash", action="store_true",
                    help="print the planned tree's placement digest and exit (read-only); "
                         "capture this BEFORE applying, as the record's pre_hash")
    rl.add_argument("--record", default="",
                    help="a YAML record (rationale, pre_hash, operations) to append")
    rl.add_argument("--list", action="store_true", help="list recorded reorgs (the default)")
    rl.add_argument("--show", default="", help="show one entry in full, by id")
    rl.add_argument("--format", choices=("text", "json"), default="text")
    rl.set_defaults(func=cmd_reorg_log)

    ru = sub.add_parser("reorg-undo",
                        help="put a recorded reorg back, if the plan has not moved on since")
    ru.add_argument("--state-root", required=True)
    ru.add_argument("--artifacts-root", required=True)
    ru.add_argument("--id", required=True, help="the journal entry id, e.g. R0001")
    ru.add_argument("--check", action="store_true",
                    help="test the guard and report, without moving anything")
    ru.set_defaults(func=cmd_reorg_undo)

    nt = sub.add_parser("notice",
                        help="record a one-time-ever advisory notice; exit 1 if already shown")
    nt.add_argument("--state-root", required=True)
    nt.add_argument("--key", required=True)
    nt.set_defaults(func=cmd_notice)

    ai = sub.add_parser("sync-agent-instructions",
                        help="create, replace or remove the l3io block in the running "
                             "harness's AI instruction file")
    ai.add_argument("--runtime", required=True,
                    choices=("claude", "codex", "copilot", "other"))
    ai.add_argument("--project-root", required=True)
    ai.add_argument("--body-file")
    ai.add_argument("--version")
    g = ai.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply", action="store_true")
    g.add_argument("--remove", action="store_true")
    g.add_argument("--check", action="store_true")
    ai.set_defaults(func=cmd_sync_agent_instructions)

    p.add_argument("--version", action="version", version=f"pm-status.py {PM_STATUS_VERSION}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
