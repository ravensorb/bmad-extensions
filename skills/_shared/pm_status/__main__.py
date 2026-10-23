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
import hashlib
import importlib.util
import json
import os
import re
import sys

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
# `metrics` and `issues` are DIRECTORIES of modules (metrics: events, rates, calibration,
# estimates, spend, report, actuals_usage; issues: adr, store, promote, audit -- see each
# package's __init__.py), so their patch targets are two levels down.
# `metrics.estimates.compute_story_estimate` and `metrics.estimates.rollup_parent_estimate`
# are called module-qualified from `issues/promote.py`; `metrics.actuals_usage.
# dispatch_window` has no caller outside its own module; and `issues.store.
# resolve_issue_core` is called module-qualified from `verbs/__init__.py` and from
# `issues/audit.py`. None of the four is re-exported, here or by either `__init__.py`.
# `metrics` and `issues` have no caller left in this file -- `_promote_issue` and
# `_resolve_story_items`, their last ones, moved to `issues/promote.py` and `verbs/` -- but
# both must stay bound here: the suite reaches its patch targets as `pm.metrics.<mod>.<name>`
# and `pm.issues.store.<name>`, and `pm` is this module's globals. Each carries its OWN
# `noqa`, not one shared directive, so a later loss of `core`'s or `nodes`'s last caller
# is still reported.
from . import (
    core,
    issues,  # noqa: F401 -- re-export only
    metrics,  # noqa: F401 -- re-export only
    nodes,
)
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
    METRIC_FIELDS,  # noqa: F401 -- re-export only
    NOTICES_FILENAME,  # noqa: F401 -- re-export only
    PM_STATUS_VERSION,
    STATUS_DIRS,
    STATUS_FOR_DIR,
    PMError,
    _die_notfound,
    _die_usage,
    _drop_legacy_file,  # noqa: F401 -- re-export only
    _ensure_lock_ignore,  # noqa: F401 -- re-export only
    _file_lock,
    _file_sha,  # noqa: F401 -- re-export only
    _hashable_field,  # noqa: F401 -- re-export only
    _indexable_key,  # noqa: F401 -- re-export only
    _is_na,  # noqa: F401 -- re-export only
    _iter_count,  # noqa: F401 -- re-export only
    _lock_rule_present,  # noqa: F401 -- re-export only
    _missing_ignore_patterns,  # noqa: F401 -- re-export only
    _now_iso,
    _parse_iso,  # noqa: F401 -- re-export only
    _parse_version_line,  # noqa: F401 -- re-export only
    _require_epic_lock,  # noqa: F401 -- re-export only
    _run_core,
    _state_root_of_node,  # noqa: F401 -- re-export only
    _tree_files,  # noqa: F401 -- re-export only
    _yaml,
    adr_register_path,  # noqa: F401 -- re-export only
    append_event,  # noqa: F401 -- re-export only
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
from .issues.adr import (
    cmd_adr_reserve,
    load_adr_register,  # noqa: F401 -- re-export only
)
from .issues.audit import (
    cmd_audit_issues,
    cmd_list_issues,
    cmd_repair_issue,
)
from .issues.promote import (
    _next_story_key,
    _walk_story_nodes,
    cmd_promote_issue,
    cmd_schedule_issue,
)

# `resolve_issue_core` is deliberately absent from this list. It is a mock.patch target, so
# it is reached as `issues.store.resolve_issue_core(...)` -- see `verbs/__init__.py`
# (`_resolve_story_items`) and `issues/audit.py`. A re-export here would be a private copy
# a patch on `pm.issues.store` could not reach, and the patch would silently guard nothing.
# `IssueStore` is re-exported because the suite patches a CLASS ATTRIBUTE on it, which
# mutates the one class object every binding names.
from .issues.store import (
    ISSUE_KINDS,
    RESOLUTIONS,
    STORY_REF_FIELDS,
    IssueStore,
    cmd_append_issue,
    cmd_resolve_issue,
    cmd_update_issue,
    issues_paths,
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
    DEFAULT_ESTIMATE_MODEL,  # noqa: F401 -- re-export only
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
    TOKEN_CLASSES,  # noqa: F401 -- re-export only
    TOKEN_RATES,  # noqa: F401 -- re-export only
    cmd_rates,
    cost_from_tokens,  # noqa: F401 -- re-export only
)
from .metrics.report import (
    build_progress_model,  # noqa: F401 -- re-export only
    cmd_report,
    list_all_epics,  # noqa: F401 -- re-export only
    load_plan,  # noqa: F401 -- re-export only
    render_tree,  # noqa: F401 -- re-export only
)
from .metrics.spend import (
    SPEND_BUCKETS,  # noqa: F401 -- re-export only
    _spend_total,  # noqa: F401 -- re-export only
    rollup_epic,  # noqa: F401 -- re-export only
    rollup_sprint,  # noqa: F401 -- re-export only
)

# The node layer's exports, by name. `save_node` and `epic_file` are deliberately absent
# -- the suite patches them, so they are reached as `nodes.<name>` (see above).
from .nodes import (
    DERIVED_NODE_FIELDS,  # noqa: F401 -- re-export only
    check_backrefs,  # noqa: F401 -- re-export only
    deps_list,
    ensure_node_path,  # noqa: F401 -- re-export only
    find_epic_dir,
    init_story_doc,  # noqa: F401 -- re-export only
    iter_epic_dirs,
    list_story_files,  # noqa: F401 -- re-export only
    load_node,
    resolve_node_path,  # noqa: F401 -- re-export only
    sprint_file,
    story_doc_path,  # noqa: F401 -- re-export only
    story_file,
)

# The status verbs, by name. Nothing here is a mock.patch target: the patched names the
# verbs touch are reached from `verbs/__init__.py` through their module objects.
from .verbs import (
    _LANE_RE,  # noqa: F401 -- re-export only
    DEPENDS_ON_KEY_RE,  # noqa: F401 -- re-export only
    EPIC_KEY_RE,  # noqa: F401 -- re-export only
    STORY_KEY_RE,  # noqa: F401 -- re-export only
    _check_lane_value,  # noqa: F401 -- re-export only
    _justifying_story_edges,  # noqa: F401 -- re-export only
    _maybe_set,  # noqa: F401 -- re-export only
    _set_estimate,  # noqa: F401 -- re-export only
    _set_field,  # noqa: F401 -- re-export only
    cmd_add_test_run,
    cmd_check_lock,
    cmd_clear_lock,
    cmd_import_node,
    cmd_list_epics,
    cmd_list_stories,
    cmd_notice,
    cmd_set_depends_on,
    cmd_set_estimate,
    cmd_set_field,
    cmd_set_lock,
    cmd_set_status,
    cmd_show,
    cmd_story_doc_init,
    cmd_sync_story_doc,
    cmd_verify,
)


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
