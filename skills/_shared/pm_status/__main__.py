#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
# pm-status-version: 3.6.0   (machine-readable marker; `self-install` compares this across copies — keep at top)
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
import importlib.util
import os
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
# SIX of the seven are imported for a LIVE caller again, and that is new: `build_parser`
# calls `<module>.register(sub)` on each of core, instructions, issues, metrics, plan and
# verbs, so none of them carries a `noqa` any more. That is the honest state -- a `noqa`
# over a module ruff can see used is a justification that reads as true and is not -- and it
# means ruff now reports the one failure mode distributed registration introduces from this
# side: delete a `register()` call and its import goes unused and FAILS `check:lint:py`,
# before TestSubcommandRegistration is even reached.
#
# `nodes` is the exception and keeps its own `noqa`: it owns no verb (the node layer, not a
# verb bucket), so nothing here calls it and it is bound purely for the suite's
# `pm.nodes.<name>` patch targets. Its directive is its own, not shared, so if another
# module later loses its caller that is reported separately rather than absorbed.
from . import (
    core,
    instructions,
    issues,
    metrics,
    nodes,  # noqa: F401 -- re-export only
    plan,
    verbs,
)
from .core import (
    _EPIC_NODE_LOCK,  # noqa: F401 -- re-export only
    _LOCK_IGNORE_CHECKED,  # noqa: F401 -- re-export only
    # Facade-only, and PINNED: test_dir_for_status_is_the_inverse_of_status_for_dir
    # reads pm.DIR_FOR_STATUS. `nodes` imports it from core directly, so dropping it
    # here would error that test rather than go quiet.
    DIR_FOR_STATUS,  # noqa: F401 -- re-export only
    METRIC_FIELDS,  # noqa: F401 -- re-export only
    PM_STATUS_VERSION,
    STATUS_FOR_DIR,  # noqa: F401 -- re-export only
    PMError,  # noqa: F401 -- re-export only
    _hashable_field,  # noqa: F401 -- re-export only
    _indexable_key,  # noqa: F401 -- re-export only
    _is_na,  # noqa: F401 -- re-export only
    _iter_count,  # noqa: F401 -- re-export only
    _now_iso,  # noqa: F401 -- re-export only
    _parse_iso,  # noqa: F401 -- re-export only
    _parse_version_line,  # noqa: F401 -- re-export only
    _yaml,  # noqa: F401 -- re-export only
    adr_register_path,  # noqa: F401 -- re-export only
    append_event,  # noqa: F401 -- re-export only
    calibration_lock,  # noqa: F401 -- re-export only
    calibration_path,  # noqa: F401 -- re-export only
    epic_dirname,  # noqa: F401 -- re-export only
    epic_lock_path,  # noqa: F401 -- re-export only
    epic_node_lock,  # noqa: F401 -- re-export only
    events_path,  # noqa: F401 -- re-export only
    issues_lock,  # noqa: F401 -- re-export only
    package_root,  # noqa: F401 -- re-export only
    parse_story_key,  # noqa: F401 -- re-export only
    sprint_dirname,  # noqa: F401 -- re-export only
    sweep_stale,  # noqa: F401 -- re-export only
    tree_digest,  # noqa: F401 -- re-export only
)

# The instruction-block leaf, re-exported by name: nothing in the suite patches a name it
# defines. It reaches `core` as a module object itself.
from .instructions import (
    BlockError,  # noqa: F401 -- re-export only
    apply_block,  # noqa: F401 -- re-export only
    find_block,  # noqa: F401 -- re-export only
    remove_block,  # noqa: F401 -- re-export only
)
from .issues.adr import (
    load_adr_register,  # noqa: F401 -- re-export only
)
from .issues.promote import (
    _next_story_key,  # noqa: F401 -- re-export only
)

# `resolve_issue_core` is deliberately absent from this list. It is a mock.patch target, so
# it is reached as `issues.store.resolve_issue_core(...)` -- see `verbs/__init__.py`
# (`_resolve_story_items`) and `issues/audit.py`. A re-export here would be a private copy
# a patch on `pm.issues.store` could not reach, and the patch would silently guard nothing.
# `IssueStore` is re-exported because the suite patches a CLASS ATTRIBUTE on it, which
# mutates the one class object every binding names.
from .issues.store import (
    IssueStore,  # noqa: F401 -- re-export only
    issues_paths,  # noqa: F401 -- re-export only
)
from .metrics.actuals_usage import (
    CLAUDE_SESSION_ENV,  # noqa: F401 -- re-export only
    discover_session_transcript,  # noqa: F401 -- re-export only
    read_transcript_usage,  # noqa: F401 -- re-export only
    resolve_session_transcript,  # noqa: F401 -- re-export only
)
from .metrics.calibration import (
    CALIBRATION_MARKER,  # noqa: F401 -- re-export only
    CALIBRATION_METRICS_MARKER,  # noqa: F401 -- re-export only
    CALIBRATION_SCHEMA_VERSION,  # noqa: F401 -- re-export only
    CLASSIFICATIONS,  # noqa: F401 -- re-export only
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
    derive_closure_sample,  # noqa: F401 -- re-export only
    derive_story_sample,  # noqa: F401 -- re-export only
    load_calibration,  # noqa: F401 -- re-export only
    migrate_calibration,  # noqa: F401 -- re-export only
    migrate_calibration_metrics,  # noqa: F401 -- re-export only
    migrate_calibration_token_basis,  # noqa: F401 -- re-export only
    new_calibration,  # noqa: F401 -- re-export only
    record_closure_sample,  # noqa: F401 -- re-export only
    record_story_sample,  # noqa: F401 -- re-export only
    redrive_story_samples,  # noqa: F401 -- re-export only
    save_calibration,  # noqa: F401 -- re-export only
    weighted_ratio,  # noqa: F401 -- re-export only
)
from .metrics.estimates import (
    BASE_BANDS,  # noqa: F401 -- re-export only
    DEFAULT_ESTIMATE_MODEL,  # noqa: F401 -- re-export only
    observed_mix,  # noqa: F401 -- re-export only
    split_tokens,  # noqa: F401 -- re-export only
)

# The measurement layer's exports, by name. The three mock.patch targets --
# `compute_story_estimate`, `rollup_parent_estimate` (metrics/estimates) and
# `dispatch_window` (metrics/actuals_usage) -- are deliberately absent, so a patch
# repointed to `pm.metrics.<mod>.<name>` without the matching call-style change here
# is a NameError rather than a patch that quietly reaches nobody.
from .metrics.events import (
    _total_blocked_hours,  # noqa: F401 -- re-export only
    build_events_index,  # noqa: F401 -- re-export only
    compute_flags,  # noqa: F401 -- re-export only
    dwell_hours,  # noqa: F401 -- re-export only
    open_dispatches,  # noqa: F401 -- re-export only
)
from .metrics.rates import (
    COLD_START_TOKEN_MIX,  # noqa: F401 -- re-export only
    FRESH_TOKEN_CLASSES,  # noqa: F401 -- re-export only
    TOKEN_CLASSES,  # noqa: F401 -- re-export only
    TOKEN_RATES,  # noqa: F401 -- re-export only
    cost_from_tokens,  # noqa: F401 -- re-export only
)
from .metrics.report import (
    build_progress_model,  # noqa: F401 -- re-export only
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
    ensure_node_path,  # noqa: F401 -- re-export only
    find_epic_dir,  # noqa: F401 -- re-export only
    init_story_doc,  # noqa: F401 -- re-export only
    list_story_files,  # noqa: F401 -- re-export only
    load_node,  # noqa: F401 -- re-export only
    sprint_file,  # noqa: F401 -- re-export only
    story_doc_path,  # noqa: F401 -- re-export only
    story_file,  # noqa: F401 -- re-export only
)

# The plan operations, by name: only the CLI handlers `build_parser` wires. Nothing here is
# a mock.patch target; `plan/__init__.py` reaches the patched names through their module
# objects.
from .plan import (
    _load_reorg_log,  # noqa: F401 -- re-export only
    move_epic,  # noqa: F401 -- re-export only
    plan_shape_hash,  # noqa: F401 -- re-export only
    record_reorg,  # noqa: F401 -- re-export only
    reorg_log_path,  # noqa: F401 -- re-export only
    reparent_story,  # noqa: F401 -- re-export only
    retire_epic,  # noqa: F401 -- re-export only
    undo_reorg,  # noqa: F401 -- re-export only
)

# The status verbs, by name. Nothing here is a mock.patch target: the patched names the
# verbs touch are reached from `verbs/__init__.py` through their module objects.
from .verbs import (
    cmd_set_status,  # noqa: F401 -- re-export only
)


# CLI
#
# REGISTRATION IS DISTRIBUTED (design §3.2). Each module registers its OWN verbs through
# its `register(subparsers)`; this function creates the root parser and the subparsers
# object and calls them in the fixed order below. The 4.0.0 v7 cut then removes a bucket's
# verbs by deleting its directory and one line here, instead of hand-editing a 520-line
# function and hoping no neighbouring verb is caught in the edit.
#
# THE ORDER IS THE SURFACE. argparse lists subcommands in registration order, so this tuple
# decides what `pm-status.py --help` prints. It is the order of each module's FIRST verb in
# the pre-split function — verbs led, then metrics, core, issues, plan, instructions — so
# the listing stays as close to the shipped one as a per-module grouping can be. Every
# individual subcommand's `--help` is byte-identical to the pre-split capture in
# `.superpowers/sdd/2026-10-23-pm-status-package-split/cli-surface-before.txt`; what the
# split necessarily changes is the ORDER of the top-level listing, because the pre-split
# function interleaved the buckets (verbs held positions 1-5, 8-11, 15-20 and 42) and no
# contiguous per-module grouping can reproduce that.
#
# `nodes` has no `register`: it is the node layer, and owns no verb. It is not called here
# and must not grow an empty `register` to look symmetrical — an empty hook is a place for a
# verb to be registered by accident.
#
# TestSubcommandRegistration is the standing guard: it pins all 43 names, and attributes a
# shortfall to the module whose call went missing.
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pm-status.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    verbs.register(sub)
    metrics.register(sub)
    core.register(sub)
    issues.register(sub)
    plan.register(sub)
    instructions.register(sub)

    p.add_argument("--version", action="version", version=f"pm-status.py {PM_STATUS_VERSION}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
