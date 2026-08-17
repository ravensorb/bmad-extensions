# Plan-Aware Progress Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long-running `/l3io-pm-execute` progress visible — which phase, which epic, which sprint, which stories are in flight — from one computed model exposed through four surfaces.

**Architecture:** A single builder in `pm-status.py` walks the sharded state tree, joins it against the plan snapshot, and returns a plain dict. Three thin renderers (`tree`/`json`/`md`) consume that dict and nothing else. A new append-only `events.jsonl`, written automatically by `set-status`/`set-actual`, supplies the per-status dwell times that state alone cannot provide.

**Tech Stack:** Python 3.11 (PEP-723 header, `uv run`), `ruamel.yaml` round-trip, stdlib `json`/`fcntl`, `unittest`. Node.js for the payload sync script.

**Spec:** `docs/superpowers/specs/2026-08-17-plan-aware-progress-reporting-design.md`

## Global Constraints

- **Never edit per-skill payload copies.** `skills/_shared/pm-status.py` and `skills/_shared/tests/test-pm-status.py` are the only editable sources; `npm run sync:scripts` regenerates `skills/l3io-pm-{execute,plan,sync}/scripts/`. CI runs `npm run check:scripts`.
- **`pm-status.py` is the only component that resolves a node key to a path.** No step file, skill, or renderer may construct a state path.
- **Bump `PM_STATUS_VERSION` to `2.3.0`** in both places: the constant at line 92 and the `# pm-status-version:` marker on line 6. `self-install` compares them.
- **Timestamps** are `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`. Parsing requires `.replace("Z", "+00:00")` before `datetime.fromisoformat`.
- **`report` is read-only unless `--out` is passed.** `/l3io-util-doctor stats` calls it and is documented as changing no files.
- **Exit codes are fixed:** 0 success, 2 usage error, 3 node not found, 4 verification failure, 5 epic locked.
- **Stuck thresholds (hours):** story `in-progress` 4, story `review` 4, sprint `in-progress` 24, epic `in-progress` 72. Story `ready-for-dev` is never flagged.
- **Never fail a status write because of telemetry.** A failed event append warns on stderr and returns 0, matching the existing calibration contract.
- **Commits:** Conventional Commits with DCO sign-off (`git commit -s`). Scopes: `l3io-pm`, `l3io-util`, `infra`.

---

### Task 1: Event log writer, auto-wired into status and actuals writes

**Files:**
- Modify: `skills/_shared/pm-status.py` (imports ~line 71; new helpers after `_append_ledger` ~line 328; `cmd_set_status` ~line 1184; `cmd_set_actual` ~line 1204; parser ~line 1776)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `_now_iso()`, `find_epic_dir()`, `load_node()`, `STATUS_DIRS`
- Produces:
  - `EVENTS_FILENAME = "events.jsonl"`
  - `events_path(state_root: str) -> str`
  - `append_event(state_root: str, payload: dict) -> None` — never raises
  - `set-status` / `set-actual` gain `--no-events` and `--session-id`

- [ ] **Step 1: Write the failing tests**

Add to `skills/_shared/tests/test-pm-status.py`. `TestLayoutResolution` already builds a node tree — mirror its fixture setup for a new class:

```python
class TestEvents(Base):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        d = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(d)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as fh:
            fh.write("key: 'E001'\ntitle: 'Foundation'\nstatus: in-progress\n")
        with open(os.path.join(d, "sprint.yaml"), "w") as fh:
            fh.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(d, "E001-S01-001.yaml"), "w") as fh:
            fh.write("key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: in-progress\n")

    def read_events(self):
        p = pm.events_path(self.root)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_set_status_appends_event_with_from_and_to(self):
        code, _ = self.run_main(["set-status", "--state-root", self.root,
                                 "--story", "E001-S01-001", "--status", "review"])
        self.assertEqual(code, 0)
        evs = self.read_events()
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event"], "status")
        self.assertEqual(evs[0]["node"], "story")
        self.assertEqual(evs[0]["key"], "E001-S01-001")
        self.assertEqual(evs[0]["from"], "in-progress")
        self.assertEqual(evs[0]["to"], "review")
        self.assertEqual(evs[0]["epic"], "E001")
        self.assertEqual(evs[0]["sprint"], "S01")

    def test_no_events_flag_suppresses(self):
        self.run_main(["set-status", "--state-root", self.root,
                       "--story", "E001-S01-001", "--status", "review", "--no-events"])
        self.assertEqual(self.read_events(), [])

    def test_session_id_recorded_when_given(self):
        self.run_main(["set-status", "--state-root", self.root, "--story", "E001-S01-001",
                       "--status", "review", "--session-id", "sess-abc"])
        self.assertEqual(self.read_events()[0]["session"], "sess-abc")

    def test_session_is_null_by_default(self):
        self.run_main(["set-status", "--state-root", self.root,
                       "--story", "E001-S01-001", "--status", "review"])
        self.assertIsNone(self.read_events()[0]["session"])

    def test_set_actual_appends_actual_event(self):
        self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                       "--story", "E001-S01-001", "--elapsed-hours", "2",
                       "--man-hours", "3", "--tokens-k", "10", "--cost", "1.5",
                       "--no-calibrate"])
        evs = [e for e in self.read_events() if e["event"] == "actual"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["key"], "E001-S01-001")

    def test_append_failure_warns_but_write_succeeds(self):
        # Make the events path un-writable by planting a directory where the file goes.
        os.makedirs(pm.events_path(self.root))
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["set-status", "--state-root", self.root,
                                     "--story", "E001-S01-001", "--status", "review"])
        self.assertEqual(code, 0)
        self.assertIn("could not append event", buf.getvalue())
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-001"))
        self.assertEqual(node["status"], "review")

    def test_concurrent_appends_lose_no_lines(self):
        import threading
        def worker(i):
            pm.append_event(self.root, {"event": "status", "n": i})
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(self.read_events()), 40)
```

Add `import json` to the test file's imports.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestEvents -v
```

Expected: FAIL — `AttributeError: module 'pm_status' has no attribute 'events_path'`.

- [ ] **Step 3: Add `import json` and the event helpers**

Add `import json` to the import block (after `import contextlib`, keeping alphabetical order).

Insert after `_append_ledger` (~line 328):

```python
EVENTS_FILENAME = "events.jsonl"


def events_path(state_root: str) -> str:
    """The one project-level event log. A single log (not per-sprint) keeps the
    progress report a single read and makes cross-epic velocity computable."""
    return os.path.join(state_root, EVENTS_FILENAME)


def append_event(state_root: str, payload: dict) -> None:
    """Append one JSON line under flock. NEVER raises: telemetry must not be able
    to fail a status write, matching the calibration contract in set-actual."""
    try:
        p = events_path(state_root)
        os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
        line = json.dumps(payload, sort_keys=True) + "\n"
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX
            fcntl = None
        with open(p, "a", encoding="utf-8") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as e:  # noqa: BLE001 - deliberate: never fail the caller
        sys.stderr.write(f"pm-status.py: warning — could not append event: {e}\n")


def _event_keys(kind: str, args) -> dict:
    """Node-identifying fields for an event payload, by node kind."""
    if kind == "story":
        epic_key, sprint_key, _ = parse_story_key(args.story)
        return {"node": "story", "key": args.story, "epic": epic_key, "sprint": sprint_key}
    if kind == "sprint":
        return {"node": "sprint", "key": args.sprint, "epic": args.epic, "sprint": args.sprint}
    return {"node": "epic", "key": args.epic, "epic": args.epic, "sprint": None}
```

- [ ] **Step 4: Wire into `cmd_set_status`**

In `cmd_set_status`, capture the prior status before the overwrite and append after the save. The existing body becomes:

```python
    y, node, path, label = _load_checked(args.state_root, args, kind)
    prior = str(node.get("status", "")) or None
    node["status"] = args.status
    node["updated_at"] = _now_iso()
    if args.title:
        node["title"] = args.title
    save_node(y, node, path, getattr(args, "flock", False))

    if not getattr(args, "no_events", False):
        payload = {"ts": _now_iso(), "event": "status",
                   "from": prior, "to": args.status,
                   "session": getattr(args, "session_id", None)}
        payload.update(_event_keys(kind, args))
        append_event(args.state_root, payload)
```

- [ ] **Step 5: Wire into `cmd_set_actual`**

At the end of `cmd_set_actual`, after the actuals block is saved and before the return (and before or after the existing calibration call — order does not matter, both are non-fatal):

```python
    if not getattr(args, "no_events", False):
        payload = {"ts": _now_iso(), "event": "actual",
                   "from": None, "to": None,
                   "session": getattr(args, "session_id", None)}
        payload.update(_event_keys(kind, args))
        append_event(args.state_root, payload)
```

- [ ] **Step 6: Add the parser flags**

In `build_parser()`, on both the `set-status` (`s`) and `set-actual` (`a`) subparsers:

```python
    s.add_argument("--no-events", action="store_true",
                   help="skip the events.jsonl append for this call")
    s.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
```

```python
    a.add_argument("--no-events", action="store_true",
                   help="skip the events.jsonl append for this call")
    a.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestEvents -v
```

Expected: PASS, 7 tests.

- [ ] **Step 8: Run the full suite for regressions**

```bash
cd skills/_shared/tests && python3 test-pm-status.py -v 2>&1 | tail -5
```

Expected: OK — no pre-existing test broken. `TestProgress` (the legacy `--ledger` path) must still pass; `--ledger` is retained unchanged.

- [ ] **Step 9: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): record status and actuals transitions to events.jsonl

Adds an append-only project-level event log written automatically by
set-status/set-actual, under flock. The write is derived from --state-root
rather than flag-driven: the existing optional --ledger is precisely why the
old progress ledger was never populated. A failed append warns and never
fails the status write."
```

---

### Task 2: Dwell time and stuck flags

**Files:**
- Modify: `skills/_shared/pm-status.py` (helpers after `append_event`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `events_path()`, `_now_iso()`
- Produces:
  - `_parse_iso(ts) -> datetime | None`
  - `STUCK_THRESHOLDS: dict[tuple[str, str], float]`
  - `build_events_index(state_root) -> dict[str, dict]`
  - `dwell_hours(node, events_index, now=None) -> tuple[float | None, bool]` — returns `(hours, exact)`
  - `compute_flags(level, key, status, dwell, exact) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

```python
class TestDwellAndFlags(Base):
    def test_parse_iso_handles_z_suffix(self):
        dt = pm._parse_iso("2026-08-17T10:00:00Z")
        self.assertEqual(dt.year, 2026)
        self.assertIsNone(pm._parse_iso(None))
        self.assertIsNone(pm._parse_iso("not-a-date"))

    def test_dwell_prefers_events_and_is_exact(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        pm.append_event(root, {"ts": "2026-08-17T06:00:00Z", "event": "status",
                               "node": "story", "key": "E001-S01-001",
                               "from": "in-progress", "to": "review"})
        idx = pm.build_events_index(root)
        node = {"key": "E001-S01-001", "status": "review",
                "updated_at": "2026-08-17T09:00:00Z"}
        now = pm._parse_iso("2026-08-17T10:00:00Z")
        hours, exact = pm.dwell_hours(node, idx, now=now)
        self.assertAlmostEqual(hours, 4.0, places=3)
        self.assertTrue(exact)

    def test_dwell_falls_back_to_updated_at_when_no_events(self):
        node = {"key": "E001-S01-001", "status": "review",
                "updated_at": "2026-08-17T08:00:00Z"}
        now = pm._parse_iso("2026-08-17T10:00:00Z")
        hours, exact = pm.dwell_hours(node, {}, now=now)
        self.assertAlmostEqual(hours, 2.0, places=3)
        self.assertFalse(exact)

    def test_dwell_falls_back_when_latest_event_status_disagrees(self):
        # Hand-edited YAML: state says done, last event said review.
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        pm.append_event(root, {"ts": "2026-08-17T06:00:00Z", "event": "status",
                               "node": "story", "key": "E001-S01-001",
                               "from": "in-progress", "to": "review"})
        idx = pm.build_events_index(root)
        node = {"key": "E001-S01-001", "status": "done",
                "updated_at": "2026-08-17T09:30:00Z"}
        now = pm._parse_iso("2026-08-17T10:00:00Z")
        hours, exact = pm.dwell_hours(node, idx, now=now)
        self.assertAlmostEqual(hours, 0.5, places=3)
        self.assertFalse(exact)

    def test_dwell_none_when_no_timestamp_at_all(self):
        hours, exact = pm.dwell_hours({"key": "X", "status": "review"}, {})
        self.assertIsNone(hours)
        self.assertFalse(exact)

    def test_index_takes_latest_event_per_key(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        for ts, to in [("2026-08-17T06:00:00Z", "review"),
                       ("2026-08-17T07:00:00Z", "in-progress")]:
            pm.append_event(root, {"ts": ts, "event": "status", "node": "story",
                                   "key": "E001-S01-001", "to": to})
        idx = pm.build_events_index(root)
        self.assertEqual(idx["E001-S01-001"]["to"], "in-progress")

    def test_index_ignores_actual_events_and_bad_lines(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        pm.append_event(root, {"ts": "2026-08-17T06:00:00Z", "event": "status",
                               "node": "story", "key": "K", "to": "review"})
        pm.append_event(root, {"ts": "2026-08-17T07:00:00Z", "event": "actual",
                               "node": "story", "key": "K"})
        with open(pm.events_path(root), "a", encoding="utf-8") as fh:
            fh.write("{ not json\n")
        idx = pm.build_events_index(root)
        self.assertEqual(idx["K"]["to"], "review")

    def test_flags_fire_at_threshold_per_level(self):
        self.assertEqual(pm.compute_flags("story", "K", "review", 4.5, True)[0]["kind"], "stuck")
        self.assertEqual(pm.compute_flags("story", "K", "review", 3.5, True), [])
        self.assertEqual(pm.compute_flags("story", "K", "in-progress", 5.0, True)[0]["kind"], "stuck")
        self.assertEqual(pm.compute_flags("sprint", "S01", "in-progress", 25.0, True)[0]["kind"], "stuck")
        self.assertEqual(pm.compute_flags("sprint", "S01", "in-progress", 5.0, True), [])
        self.assertEqual(pm.compute_flags("epic", "E001", "in-progress", 80.0, True)[0]["kind"], "stuck")

    def test_ready_for_dev_never_flagged(self):
        self.assertEqual(pm.compute_flags("story", "K", "ready-for-dev", 500.0, True), [])

    def test_done_never_flagged_and_none_dwell_never_flagged(self):
        self.assertEqual(pm.compute_flags("story", "K", "done", 500.0, True), [])
        self.assertEqual(pm.compute_flags("story", "K", "review", None, False), [])

    def test_flag_carries_approximate_marker(self):
        f = pm.compute_flags("story", "K", "review", 9.0, False)[0]
        self.assertFalse(f["exact"])
        self.assertEqual(f["threshold"], 4.0)
        self.assertEqual(f["status"], "review")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestDwellAndFlags -v
```

Expected: FAIL — `AttributeError: ... has no attribute '_parse_iso'`.

- [ ] **Step 3: Implement the helpers**

Insert after `_event_keys`:

```python
# Fixed thresholds, in hours. Deliberately not configurable in this iteration: the
# calibration data needed to tune them is what this report will generate.
STUCK_THRESHOLDS = {
    ("story", "in-progress"): 4.0,
    ("story", "review"): 4.0,
    ("sprint", "in-progress"): 24.0,
    ("epic", "in-progress"): 72.0,
}


def _parse_iso(ts):
    """Parse a pm-status timestamp into an aware datetime, or None if unusable."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def build_events_index(state_root: str) -> dict:
    """key -> the most recent *status* event for that key.

    Returns {} when the log is absent, which is the normal case for every project
    that predates it — callers fall back to `updated_at`.
    """
    idx: dict = {}
    p = events_path(state_root)
    if not os.path.isfile(p):
        return idx
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue  # a torn or hand-mangled line must not kill the report
                if ev.get("event") != "status" or not ev.get("key"):
                    continue
                prev = idx.get(ev["key"])
                if prev is None or str(ev.get("ts", "")) >= str(prev.get("ts", "")):
                    idx[ev["key"]] = ev
    except OSError as e:
        sys.stderr.write(f"pm-status.py: warning — could not read event log: {e}\n")
    return idx


def dwell_hours(node, events_index: dict, now=None):
    """Hours the node has been in its CURRENT status.

    Returns (hours, exact). `exact` is True only when the event log recorded the
    transition into this very status. The `updated_at` fallback is approximate
    because any field write refreshes it, not only a status change.
    """
    if node is None:
        return None, False
    now = now or datetime.now(timezone.utc)
    status = str(node.get("status", ""))
    key = str(node.get("key", ""))
    ev = events_index.get(key)
    if ev is not None and str(ev.get("to", "")) == status:
        started = _parse_iso(ev.get("ts"))
        if started is not None:
            return max(0.0, (now - started).total_seconds() / 3600.0), True
    started = _parse_iso(node.get("updated_at"))
    if started is None:
        return None, False
    return max(0.0, (now - started).total_seconds() / 3600.0), False


def compute_flags(level: str, key: str, status: str, dwell, exact: bool) -> list:
    """Stuck flags for one node. Terminal and waiting statuses are never flagged."""
    if dwell is None:
        return []
    threshold = STUCK_THRESHOLDS.get((level, str(status)))
    if threshold is None or dwell < threshold:
        return []
    return [{"kind": "stuck", "level": level, "key": key, "status": str(status),
             "dwell_hours": round(dwell, 2), "threshold": threshold, "exact": exact}]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestDwellAndFlags -v
```

Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): derive per-status dwell time and stuck flags

Dwell prefers the event log (exact: the transition into the current status) and
falls back to updated_at, which is approximate because any field write refreshes
it. Thresholds are fixed for now; the data needed to tune them is what this
generates."
```

---

### Task 3: Project-wide state walk — the progress model

**Files:**
- Modify: `skills/_shared/pm-status.py` (after `rollup_epic` ~line 1152)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `STATUS_DIRS`, `STATUS_FOR_DIR`, `find_epic_dir()`, `rollup_epic()`, `list_sprint_dirs()`, `list_story_files()`, `load_node()`, `build_events_index()`, `dwell_hours()`, `compute_flags()`, `_accumulate_actuals()`, `_parse_iso()`
- Produces:
  - `list_all_epics(state_root) -> list[tuple[str, str]]` — `(epic_key, dir_status)`, sorted by key
  - `build_epic_detail(state_root, epic_key, dir_status, events_index, now=None) -> dict`
  - `build_progress_model(state_root, plan=None, include_archived=False, now=None) -> dict`

- [ ] **Step 1: Write the failing tests**

```python
class TestProgressModel(Base):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        self.mk("active", "epic-001", "E001", "Foundation", "in-progress",
                sprints={"sprint-01": ("S01", "done", [("E001-S01-001", "done"),
                                                       ("E001-S01-002", "done")]),
                         "sprint-02": ("S02", "in-progress", [("E001-S02-001", "review"),
                                                              ("E001-S02-002", "backlog")])})
        self.mk("archived", "epic-002", "E002", "Auth", "done",
                sprints={"sprint-01": ("S01", "done", [("E002-S01-001", "done")])})
        self.mk("planned", "epic-004", "E004", "Telemetry", "backlog", sprints={})

    def mk(self, folder, edir, ekey, title, status, sprints):
        ed = os.path.join(self.root, folder, edir)
        os.makedirs(ed, exist_ok=True)
        with open(os.path.join(ed, "epic.yaml"), "w") as fh:
            fh.write(f"key: '{ekey}'\ntitle: '{title}'\nstatus: {status}\n"
                     f"updated_at: '2026-08-17T09:00:00Z'\n")
        for sdir, (skey, sstatus, stories) in sprints.items():
            sd = os.path.join(ed, sdir)
            os.makedirs(sd, exist_ok=True)
            with open(os.path.join(sd, "sprint.yaml"), "w") as fh:
                fh.write(f"key: '{skey}'\nepic: '{ekey}'\nstatus: {sstatus}\n"
                         f"updated_at: '2026-08-17T09:00:00Z'\n")
            for stkey, ststatus in stories:
                with open(os.path.join(sd, f"{stkey}.yaml"), "w") as fh:
                    fh.write(f"key: '{stkey}'\nepic: '{ekey}'\nsprint: '{skey}'\n"
                             f"status: {ststatus}\nupdated_at: '2026-08-17T09:00:00Z'\n")

    def test_list_all_epics_spans_all_status_folders(self):
        got = pm.list_all_epics(self.root)
        self.assertEqual(got, [("E001", "active"), ("E002", "archived"), ("E004", "planned")])

    def test_archived_omitted_by_default(self):
        m = pm.build_progress_model(self.root)
        keys = [e["key"] for e in m["unplanned_epics"]]
        self.assertIn("E001", keys)
        self.assertIn("E004", keys)
        self.assertNotIn("E002", keys)

    def test_archived_present_with_include_archived(self):
        m = pm.build_progress_model(self.root, include_archived=True)
        self.assertIn("E002", [e["key"] for e in m["unplanned_epics"]])

    def test_totals_count_archived_even_when_hidden(self):
        m = pm.build_progress_model(self.root)
        self.assertEqual(m["totals"]["epics"], {"in-progress": 1, "done": 1, "backlog": 1})
        self.assertEqual(m["totals"]["stories"]["done"], 3)   # 2 in E001 + 1 in archived E002
        self.assertEqual(m["totals"]["stories"]["review"], 1)

    def test_epic_detail_hierarchy(self):
        m = pm.build_progress_model(self.root)
        e = next(x for x in m["unplanned_epics"] if x["key"] == "E001")
        self.assertEqual(e["title"], "Foundation")
        self.assertEqual(e["dir_status"], "active")
        self.assertEqual(e["sprint_count"], 2)
        self.assertEqual(e["story_count"], 4)
        self.assertEqual([s["key"] for s in e["sprints"]], ["S01", "S02"])
        s2 = e["sprints"][1]
        self.assertEqual([st["key"] for st in s2["stories"]],
                         ["E001-S02-001", "E001-S02-002"])

    def test_placement_anomaly_flagged(self):
        p = os.path.join(self.root, "planned", "epic-004", "epic.yaml")
        with open(p, "w") as fh:
            fh.write("key: 'E004'\ntitle: 'Telemetry'\nstatus: done\n")
        m = pm.build_progress_model(self.root)
        kinds = [f["kind"] for f in m["flags"]]
        self.assertIn("placement", kinds)

    def test_unparseable_node_is_flagged_not_fatal(self):
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-001.yaml")
        with open(p, "w") as fh:
            fh.write("key: [unclosed\n")
        m = pm.build_progress_model(self.root)
        self.assertIn("unreadable", [f["kind"] for f in m["flags"]])

    def test_stuck_story_flagged_from_updated_at(self):
        now = pm._parse_iso("2026-08-17T20:00:00Z")   # 11h after the fixture stamp
        m = pm.build_progress_model(self.root, now=now)
        stuck = [f for f in m["flags"] if f["kind"] == "stuck"]
        self.assertIn("E001-S02-001", [f["key"] for f in stuck])   # review, 11h > 4h
        self.assertNotIn("E001-S02-002", [f["key"] for f in stuck])  # backlog, never

    def test_empty_state_root_yields_empty_model(self):
        empty = os.path.join(self.d, "nothing")
        os.makedirs(empty)
        m = pm.build_progress_model(empty)
        self.assertEqual(m["unplanned_epics"], [])
        self.assertEqual(m["phases"], [])
        self.assertIsNone(m["plan"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestProgressModel -v
```

Expected: FAIL — `has no attribute 'list_all_epics'`.

- [ ] **Step 3: Implement the walk**

Insert after `_fmt_actuals`:

```python
def list_all_epics(state_root: str) -> list:
    """(epic_key, dir_status) for every epic in every status folder, sorted by key.

    The directory name is authoritative for the key: 'epic-001' -> 'E001'. Reading
    the key from the file instead would let a mis-keyed file hide an epic entirely.
    """
    found = []
    for status in STATUS_DIRS:
        base = os.path.join(state_root, status)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.startswith("epic-"):
                continue
            if not os.path.isdir(os.path.join(base, name)):
                continue
            suffix = name[len("epic-"):]
            if not suffix.isdigit():
                continue
            found.append((f"E{int(suffix):03d}", status))
    return sorted(found, key=lambda t: t[0])


def build_epic_detail(state_root: str, epic_key: str, dir_status: str,
                      events_index: dict, now=None) -> dict:
    """One epic subtree, enriched with dwell times, flags, and placement checks."""
    flags: list = []
    ep = epic_file(state_root, epic_key)
    y_node = None
    if ep is not None:
        try:
            _, y_node = load_node(ep)
        except Exception as e:  # noqa: BLE001 - a bad file must not kill the report
            flags.append({"kind": "unreadable", "level": "epic", "key": epic_key,
                          "detail": str(e)})
    enode = y_node or {}

    status = str(enode.get("status", "unknown"))
    expected = STATUS_FOR_DIR.get(dir_status)
    if expected and status != "unknown" and status != expected:
        flags.append({"kind": "placement", "level": "epic", "key": epic_key,
                      "detail": f"status {status!r} but sits in {dir_status}/ "
                                f"(expected {expected!r})"})

    lock = None
    raw_lock = enode.get("_lock")
    if isinstance(raw_lock, dict):
        claimed = _parse_iso(raw_lock.get("claimed_at"))
        ttl = raw_lock.get("ttl_minutes")
        stale = False
        if claimed is not None and ttl:
            try:
                age_min = ((now or datetime.now(timezone.utc)) - claimed).total_seconds() / 60.0
                stale = age_min > float(ttl)
            except (TypeError, ValueError):
                stale = False
        lock = {"session_id": raw_lock.get("session_id"),
                "claimed_at": raw_lock.get("claimed_at"),
                "ttl_minutes": ttl, "stale": stale}
        if stale:
            flags.append({"kind": "stale-lock", "level": "epic", "key": epic_key,
                          "detail": f"lock claimed {raw_lock.get('claimed_at')} "
                                    f"exceeds ttl {ttl}m"})

    dwell, exact = dwell_hours({"key": epic_key, "status": status,
                                "updated_at": enode.get("updated_at")}, events_index, now)
    flags += compute_flags("epic", epic_key, status, dwell, exact)

    sprints, totals, by_status, story_count = [], {}, {}, 0
    for sd in list_sprint_dirs(state_root, epic_key):
        skey = _sprint_key_from_dir(sd)
        s_detail, s_flags = _build_sprint_detail(state_root, epic_key, skey,
                                                 events_index, now)
        flags += s_flags
        sprints.append(s_detail)
        story_count += s_detail["story_count"]
        for k, v in s_detail["by_status"].items():
            by_status[k] = by_status.get(k, 0) + v
        for k, v in s_detail["actual_totals"].items():
            totals[k] = totals.get(k, 0.0) + v

    return {
        "key": epic_key, "title": enode.get("title"), "status": status,
        "dir_status": dir_status, "sprint_count": len(sprints),
        "story_count": story_count, "by_status": by_status,
        "estimate": dict(enode.get("estimate") or {}),
        "actual_totals": totals, "updated_at": enode.get("updated_at"),
        "dwell_hours": None if dwell is None else round(dwell, 2),
        "dwell_exact": exact, "lock": lock, "flags": flags, "sprints": sprints,
    }


def _build_sprint_detail(state_root: str, epic_key: str, sprint_key: str,
                         events_index: dict, now=None):
    """(detail, flags) for one sprint and its stories."""
    flags: list = []
    sp = sprint_file(state_root, epic_key, sprint_key)
    snode = {}
    if sp is not None:
        try:
            _, loaded = load_node(sp)
            snode = loaded or {}
        except Exception as e:  # noqa: BLE001
            flags.append({"kind": "unreadable", "level": "sprint",
                          "key": f"{epic_key}/{sprint_key}", "detail": str(e)})

    s_status = str(snode.get("status", "unknown"))
    s_dwell, s_exact = dwell_hours({"key": sprint_key, "status": s_status,
                                    "updated_at": snode.get("updated_at")},
                                   events_index, now)
    flags += compute_flags("sprint", f"{epic_key}/{sprint_key}", s_status, s_dwell, s_exact)

    stories, by_status, totals = [], {}, {}
    for p in list_story_files(state_root, epic_key, sprint_key):
        try:
            _, node = load_node(p)
        except Exception as e:  # noqa: BLE001
            flags.append({"kind": "unreadable", "level": "story",
                          "key": os.path.basename(p), "detail": str(e)})
            continue
        if node is None:
            continue
        st = str(node.get("status", "unknown"))
        key = str(node.get("key", os.path.basename(p)))
        by_status[st] = by_status.get(st, 0) + 1
        _accumulate_actuals(totals, node)
        d, ex = dwell_hours(node, events_index, now)
        st_flags = compute_flags("story", key, st, d, ex)
        flags += st_flags
        stories.append({"key": key, "status": st,
                        "estimate": dict(node.get("estimate") or {}),
                        "actual": dict(node.get("actual") or {}),
                        "updated_at": node.get("updated_at"),
                        "dwell_hours": None if d is None else round(d, 2),
                        "dwell_exact": ex, "flags": st_flags})

    return ({"key": sprint_key, "status": s_status, "story_count": len(stories),
             "by_status": by_status, "actual_totals": totals,
             "estimate": dict(snode.get("estimate") or {}),
             "updated_at": snode.get("updated_at"),
             "dwell_hours": None if s_dwell is None else round(s_dwell, 2),
             "dwell_exact": s_exact, "stories": stories}, flags)


def build_progress_model(state_root: str, plan=None, include_archived: bool = False,
                         now=None) -> dict:
    """The one model every renderer and every surface consumes.

    Archived epics are built regardless of `include_archived` — phase progress needs
    a true denominator — and filtered only out of the *display* lists.
    """
    events_index = build_events_index(state_root)
    details, flags = {}, []
    totals = {"epics": {}, "sprints": {}, "stories": {}}

    for epic_key, dir_status in list_all_epics(state_root):
        d = build_epic_detail(state_root, epic_key, dir_status, events_index, now)
        details[epic_key] = d
        flags += d["flags"]
        totals["epics"][d["status"]] = totals["epics"].get(d["status"], 0) + 1
        for sp in d["sprints"]:
            totals["sprints"][sp["status"]] = totals["sprints"].get(sp["status"], 0) + 1
        for k, v in d["by_status"].items():
            totals["stories"][k] = totals["stories"].get(k, 0) + v

    def visible(d):
        return include_archived or d["dir_status"] != "archived"

    phases, claimed = [], set()
    for ph in (plan or {}).get("phases") or []:
        members = [str(k) for k in (ph.get("epics") or [])]
        claimed.update(members)
        present = [details[k] for k in members if k in details]
        phases.append({
            "phase": ph.get("phase"), "parallel": bool(ph.get("parallel")),
            "epics": members, "dependencies": list(ph.get("dependencies") or []),
            "epic_total": len(members),
            "epic_done": sum(1 for d in present if d["status"] == "done"),
            "epics_detail": [d for d in present if visible(d)],
        })

    return {
        "generated": _now_iso(),
        "state_root": os.path.abspath(state_root),
        "plan": (plan or {}).get("meta"),
        "phases": phases,
        "unplanned_epics": [d for k, d in sorted(details.items())
                            if k not in claimed and visible(d)],
        "totals": totals,
        "flags": flags,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestProgressModel -v
```

Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): build a project-wide progress model

Walks every status folder into one normalized dict: epic -> sprint -> story with
dwell times, stuck/placement/stale-lock/unreadable flags, and actuals roll-ups.
Archived epics are always built so phase denominators stay true, and filtered
only out of the display lists."
```

---

### Task 4: Plan snapshot join

**Files:**
- Modify: `skills/_shared/pm-status.py`
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `_load()`, `build_progress_model()`
- Produces: `load_plan(plan_pointer: str) -> dict | None` — returns `{"meta": {...}, "phases": [...]}` or `None`

`plan_pointer` is the path to `plan-output-meta.yaml`. That file names the snapshot in `current_plan` but holds no phases (by design — see `step-06-plan-output.md` §4), so the loader must follow the pointer to the snapshot in the same directory.

- [ ] **Step 1: Write the failing tests**

```python
class TestPlanJoin(TestProgressModel):
    def write_plan(self, epics_p1=("E001", "E002"), snapshot="plan-2026-08-17-v1.yaml"):
        pd = os.path.join(self.d, "planning")
        os.makedirs(pd, exist_ok=True)
        with open(os.path.join(pd, "plan-output-meta.yaml"), "w") as fh:
            fh.write(f"current_plan: \"{snapshot}\"\ngenerated: \"2026-08-17T08:00:00Z\"\n"
                     f"readiness: green\nphase_count: 2\n")
        with open(os.path.join(pd, snapshot), "w") as fh:
            fh.write("generated: \"2026-08-17T08:00:00Z\"\nreadiness: green\nphases:\n")
            fh.write(f"  - phase: 1\n    parallel: true\n    epics: {list(epics_p1)}\n"
                     f"    dependencies: []\n")
            fh.write("  - phase: 2\n    parallel: false\n    epics: ['E004']\n"
                     "    dependencies: ['E001']\n")
        return os.path.join(pd, "plan-output-meta.yaml")

    def test_load_plan_follows_pointer_to_snapshot(self):
        plan = pm.load_plan(self.write_plan())
        self.assertEqual(plan["meta"]["readiness"], "green")
        self.assertEqual(len(plan["phases"]), 2)
        self.assertEqual(plan["phases"][0]["epics"], ["E001", "E002"])

    def test_load_plan_returns_none_when_missing(self):
        self.assertIsNone(pm.load_plan(os.path.join(self.d, "nope.yaml")))

    def test_load_plan_returns_none_when_snapshot_dangling(self):
        ptr = self.write_plan(snapshot="does-not-exist.yaml")
        plan = pm.load_plan(ptr)
        self.assertIsNotNone(plan["meta"])
        self.assertEqual(plan["phases"], [])

    def test_model_groups_epics_into_phases(self):
        plan = pm.load_plan(self.write_plan())
        m = pm.build_progress_model(self.root, plan=plan)
        self.assertEqual(len(m["phases"]), 2)
        self.assertEqual(m["phases"][0]["epic_total"], 2)
        self.assertEqual([e["key"] for e in m["phases"][0]["epics_detail"]], ["E001"])
        self.assertEqual(m["plan"]["readiness"], "green")

    def test_archived_counted_in_denominator_but_not_displayed(self):
        plan = pm.load_plan(self.write_plan(epics_p1=("E001", "E002")))
        m = pm.build_progress_model(self.root, plan=plan)
        ph = m["phases"][0]
        self.assertEqual(ph["epic_total"], 2)
        self.assertEqual(ph["epic_done"], 1)                      # E002 is archived+done
        self.assertEqual([e["key"] for e in ph["epics_detail"]], ["E001"])

    def test_planned_epics_do_not_appear_as_unplanned(self):
        plan = pm.load_plan(self.write_plan())
        m = pm.build_progress_model(self.root, plan=plan)
        self.assertEqual(m["unplanned_epics"], [])                # E001,E002,E004 all in phases
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestPlanJoin -v
```

Expected: FAIL — `has no attribute 'load_plan'`.

- [ ] **Step 3: Implement `load_plan`**

Insert immediately before `build_progress_model`:

```python
def load_plan(plan_pointer: str):
    """Load plan phases via the stable pointer.

    `plan-output-meta.yaml` is a pointer plus summary scalars and deliberately holds
    no phases list (step-06-plan-output.md §4), so the phases come from the snapshot
    it names, resolved in the pointer's own directory. A dangling pointer yields the
    meta with empty phases rather than an error: the state hierarchy is still worth
    showing.
    """
    if not plan_pointer or not os.path.isfile(plan_pointer):
        return None
    try:
        _, meta = _load(plan_pointer)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"pm-status.py: warning — could not read plan pointer: {e}\n")
        return None
    if not meta:
        return None
    meta = dict(meta)
    phases = []
    snap_name = meta.get("current_plan")
    if snap_name:
        snap = os.path.join(os.path.dirname(os.path.abspath(plan_pointer)), str(snap_name))
        if os.path.isfile(snap):
            try:
                _, snode = _load(snap)
                phases = [dict(p) for p in ((snode or {}).get("phases") or [])]
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"pm-status.py: warning — could not read plan snapshot: {e}\n")
        else:
            sys.stderr.write(f"pm-status.py: warning — plan pointer names a missing "
                             f"snapshot: {snap_name}\n")
    return {"meta": meta, "phases": phases}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestPlanJoin -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): join the plan snapshot into the progress model

Follows plan-output-meta.yaml to its snapshot for the phases list, groups epics
by phase, and computes epic_done/epic_total from plan membership so denominators
stay true when archived epics are hidden."
```

---

### Task 5: The `report` command and its three renderers

**Files:**
- Modify: `skills/_shared/pm-status.py` (renderers before the subcommands section; `cmd_report` with the other `cmd_*`; parser entry in `build_parser`; docstring subcommand list ~line 30-68; `PM_STATUS_VERSION` and the line-6 marker)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `build_progress_model()`, `load_plan()`
- Produces:
  - `render_tree(model) -> str`
  - `render_md(model) -> str`
  - `cmd_report(args) -> int`
  - CLI: `report --state-root S [--plan P] [--format tree|json|md] [--out F] [--all] [--watch N]`

- [ ] **Step 1: Write the failing tests**

```python
class TestReport(TestPlanJoin):
    def test_json_format_round_trips(self):
        code, out = self.run_main(["report", "--state-root", self.root, "--format", "json"])
        self.assertEqual(code, 0)
        m = json.loads(out)
        self.assertIn("totals", m)
        self.assertIn("unplanned_epics", m)

    def test_tree_renders_hierarchy(self):
        code, out = self.run_main(["report", "--state-root", self.root, "--format", "tree"])
        self.assertEqual(code, 0)
        self.assertIn("E001", out)
        self.assertIn("S02", out)
        self.assertIn("E001-S02-001", out)
        self.assertNotIn("E002", out)          # archived, hidden by default

    def test_tree_shows_archived_with_all(self):
        _, out = self.run_main(["report", "--state-root", self.root,
                                "--format", "tree", "--all"])
        self.assertIn("E002", out)

    def test_tree_renders_phases_when_plan_given(self):
        ptr = self.write_plan()
        _, out = self.run_main(["report", "--state-root", self.root, "--plan", ptr,
                                "--format", "tree"])
        self.assertIn("Phase 1", out)
        self.assertIn("readiness", out.lower())

    def test_md_format_emits_tables(self):
        _, out = self.run_main(["report", "--state-root", self.root, "--format", "md"])
        self.assertIn("|", out)
        self.assertIn("generated by", out.lower())

    def test_out_writes_file_and_prints_nothing_but_confirmation(self):
        dest = os.path.join(self.d, "progress-report.md")
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--format", "md", "--out", dest])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(dest))
        self.assertIn("OK report", out)

    def test_read_only_without_out(self):
        before = self.snapshot_tree()
        self.run_main(["report", "--state-root", self.root, "--format", "tree"])
        self.assertEqual(before, self.snapshot_tree())

    def snapshot_tree(self):
        seen = {}
        for base, _, files in os.walk(self.root):
            for f in files:
                p = os.path.join(base, f)
                seen[p] = os.path.getmtime(p)
        return seen

    def test_empty_tree_renders_without_raising(self):
        empty = os.path.join(self.d, "empty-state")
        os.makedirs(empty)
        code, out = self.run_main(["report", "--state-root", empty, "--format", "tree"])
        self.assertEqual(code, 0)
        self.assertIn("no epics", out.lower())

    def test_stuck_marker_appears_in_tree(self):
        # Age the fixture past the 4h review threshold by rewriting updated_at.
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-001.yaml")
        with open(p, "w") as fh:
            fh.write("key: 'E001-S02-001'\nepic: 'E001'\nsprint: 'S02'\n"
                     "status: review\nupdated_at: '2000-01-01T00:00:00Z'\n")
        _, out = self.run_main(["report", "--state-root", self.root, "--format", "tree"])
        self.assertIn("E001-S02-001", out)
        self.assertIn("stuck", out.lower())

    def test_bad_format_is_usage_error(self):
        code, _ = self.run_main(["report", "--state-root", self.root, "--format", "nope"])
        self.assertEqual(code, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestReport -v
```

Expected: FAIL — `invalid choice: 'report'`.

- [ ] **Step 3: Implement the renderers**

Insert after `_fmt_actuals`:

```python
def _bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    filled = int(round(width * max(0, min(done, total)) / total))
    return "█" * filled + "░" * (width - filled)


def _dwell_str(node: dict) -> str:
    h = node.get("dwell_hours")
    if h is None:
        return ""
    approx = "" if node.get("dwell_exact") else "~"
    return f"{approx}{h:.1f}h"


def _stuck_suffix(node: dict) -> str:
    return "  ⚠ stuck" if any(f["kind"] == "stuck" for f in node.get("flags") or []) else ""


def _render_epic_tree(d: dict, out: list, indent: str = "  ") -> None:
    done = d["by_status"].get("done", 0)
    out.append(f"{indent}{d['key']} {d.get('title') or '':<24} {d['status']:<12} "
               f"{done}/{d['story_count']} stories  {_dwell_str(d)}{_stuck_suffix(d)}")
    if d.get("lock") and d["lock"].get("stale"):
        out.append(f"{indent}  ⚠ STALE LOCK — claimed {d['lock'].get('claimed_at')} "
                   f"(ttl {d['lock'].get('ttl_minutes')}m)")
    for sp in d["sprints"]:
        s_done = sp["by_status"].get("done", 0)
        out.append(f"{indent}  {sp['key']:<6} {sp['status']:<12} "
                   f"{s_done}/{sp['story_count']}  {_dwell_str(sp)}{_stuck_suffix(sp)}")
        for st in sp["stories"]:
            if st["status"] == "done":
                continue  # the counts above carry finished work; the tree shows what is live
            out.append(f"{indent}    {st['key']:<20} {st['status']:<14} "
                       f"{_dwell_str(st)}{_stuck_suffix(st)}")


def render_tree(model: dict) -> str:
    out: list = []
    plan = model.get("plan")
    if plan:
        out.append(f"PLAN {plan.get('current_plan')}   readiness={plan.get('readiness')}"
                   f"   generated={plan.get('generated')}")
    else:
        out.append("PLAN (none — showing state only)")
    out.append(f"STATE {model['state_root']}")
    out.append("")

    total_phases = len(model["phases"])
    for ph in model["phases"]:
        kind = "parallel" if ph["parallel"] else "sequential"
        out.append(f"Phase {ph['phase']}/{total_phases} ({kind})  "
                   f"{_bar(ph['epic_done'], ph['epic_total'])}  "
                   f"{ph['epic_done']}/{ph['epic_total']} epics done")
        if ph["dependencies"]:
            out.append(f"  depends on: {', '.join(str(x) for x in ph['dependencies'])}")
        if not ph["epics_detail"]:
            out.append("  (all epics in this phase are archived — pass --all to show)")
        for d in ph["epics_detail"]:
            _render_epic_tree(d, out)
        out.append("")

    if model["unplanned_epics"]:
        out.append("Not in any plan phase:" if model["phases"] else "Epics:")
        for d in model["unplanned_epics"]:
            _render_epic_tree(d, out)
        out.append("")

    if not model["phases"] and not model["unplanned_epics"]:
        out.append("No epics found — nothing to report.")
        out.append("")

    t = model["totals"]
    out.append("Totals")
    for level in ("epics", "sprints", "stories"):
        counts = t.get(level) or {}
        body = "  ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        out.append(f"  {level:<9} {body}")

    other = [f for f in model["flags"] if f["kind"] != "stuck"]
    if other:
        out.append("")
        out.append("Anomalies")
        for f in other:
            out.append(f"  [{f['kind']}] {f.get('key')} — {f.get('detail', '')}")

    if any(f["kind"] == "stuck" and not f.get("exact") for f in model["flags"]):
        out.append("")
        out.append("~ dwell times are approximate (no event log yet — derived from "
                   "updated_at, which any field write refreshes)")
    return "\n".join(out) + "\n"


def render_md(model: dict) -> str:
    out = ["# Progress Report", ""]
    plan = model.get("plan")
    out.append(f"Generated by `pm-status.py report` at {model['generated']}. "
               "This file is a view, not a source of truth — do not hand-edit; "
               "regenerate it.")
    out.append("")
    if plan:
        out.append(f"**Plan:** `{plan.get('current_plan')}` — readiness "
                   f"`{plan.get('readiness')}`, generated {plan.get('generated')}")
    else:
        out.append("**Plan:** none found — state only.")
    out.append("")

    if model["phases"]:
        out += ["## Phases", "", "| Phase | Mode | Epics done | Members |",
                "|---|---|---|---|"]
        for ph in model["phases"]:
            mode = "parallel" if ph["parallel"] else "sequential"
            out.append(f"| {ph['phase']} | {mode} | {ph['epic_done']}/{ph['epic_total']} "
                       f"| {', '.join(ph['epics'])} |")
        out.append("")

    out += ["## Epics", "", "| Epic | Title | Status | Sprints | Stories done | Dwell |",
            "|---|---|---|---|---|---|"]
    rows = [d for ph in model["phases"] for d in ph["epics_detail"]] + model["unplanned_epics"]
    if not rows:
        out.append("| _none_ | | | | | |")
    for d in rows:
        out.append(f"| {d['key']} | {d.get('title') or ''} | {d['status']} "
                   f"| {d['sprint_count']} | {d['by_status'].get('done', 0)}/"
                   f"{d['story_count']} | {_dwell_str(d) or '—'} |")
    out.append("")

    live = [(d, sp, st) for d in rows for sp in d["sprints"] for st in sp["stories"]
            if st["status"] not in ("done", "backlog")]
    if live:
        out += ["## Stories in flight", "",
                "| Story | Epic | Sprint | Status | Dwell | Stuck |", "|---|---|---|---|---|---|"]
        for d, sp, st in live:
            stuck = "yes" if any(f["kind"] == "stuck" for f in st["flags"]) else ""
            out.append(f"| {st['key']} | {d['key']} | {sp['key']} | {st['status']} "
                       f"| {_dwell_str(st) or '—'} | {stuck} |")
        out.append("")

    out += ["## Totals", "", "| Level | Counts |", "|---|---|"]
    for level in ("epics", "sprints", "stories"):
        counts = model["totals"].get(level) or {}
        out.append(f"| {level} | {', '.join(f'{k}={v}' for k, v in sorted(counts.items())) or 'none'} |")
    out.append("")
    return "\n".join(out) + "\n"
```

- [ ] **Step 4: Implement `cmd_report`**

Insert after `cmd_show`:

```python
def cmd_report(args) -> int:
    """Plan-aware progress report. Read-only unless --out is given, which is what
    lets /l3io-util-doctor stats call this while documenting that it changes nothing."""
    if not os.path.isdir(args.state_root):
        _die_notfound(f"state root {args.state_root}")

    def once() -> str:
        plan = load_plan(args.plan) if args.plan else None
        model = build_progress_model(args.state_root, plan=plan,
                                     include_archived=args.all)
        if args.format == "json":
            return json.dumps(model, indent=2, sort_keys=True) + "\n"
        return render_md(model) if args.format == "md" else render_tree(model)

    if args.watch:
        import time
        try:
            while True:
                sys.stdout.write("\x1b[2J\x1b[H")   # clear + home
                sys.stdout.write(once())
                sys.stdout.write(f"\n[refreshing every {args.watch}s — Ctrl-C to stop]\n")
                sys.stdout.flush()
                time.sleep(args.watch)
        except KeyboardInterrupt:
            return 0

    text = once()
    if args.out:
        d = os.path.dirname(os.path.abspath(args.out)) or "."
        os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stdout.write(f"OK report {args.out} ({args.format})\n")
        return 0
    sys.stdout.write(text)
    return 0
```

- [ ] **Step 5: Register the subcommand**

In `build_parser()`, after the `show` block:

```python
    rp = sub.add_parser("report", help="plan-aware progress report (read-only unless --out)")
    rp.add_argument("--state-root", required=True)
    rp.add_argument("--plan", default="", help="path to plan-output-meta.yaml")
    rp.add_argument("--format", choices=["tree", "json", "md"], default="tree")
    rp.add_argument("--out", default="", help="write to this file instead of stdout")
    rp.add_argument("--all", action="store_true", help="include archived epics")
    rp.add_argument("--watch", type=int, default=0, metavar="SECS",
                    help="re-render on an interval (tree only in practice)")
    rp.set_defaults(func=cmd_report)
```

- [ ] **Step 6: Update the docstring subcommand list and bump the version**

In the module docstring's `Subcommands` block, after the `show` line:

```
  report        --state-root S  [--plan P] [--format tree|json|md] [--out F]
                [--all] [--watch SECS]
```

Change line 6 to `# pm-status-version: 2.3.0` and line 92 to `PM_STATUS_VERSION = "2.3.0"`.

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd skills/_shared/tests && python3 test-pm-status.py TestReport -v
```

Expected: PASS, 10 tests.

- [ ] **Step 8: Run the full suite and eyeball real output**

```bash
cd skills/_shared/tests && python3 test-pm-status.py 2>&1 | tail -3
cd ../../.. && python3 skills/_shared/pm-status.py report --help
```

Expected: OK on the suite; `--help` lists every flag.

- [ ] **Step 9: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): add report command with tree/json/md renderers

One model, three renderers, plus --watch for a live view. Read-only unless --out
is passed, so read-only callers can share the code path. Bumps pm-status to
2.3.0 so self-install propagates it."
```

---

### Task 6: Sync payload copies and update the state-layout contract

**Files:**
- Modify: `skills/_shared/status-files.md` (§1 file locations, §Addressing command table)
- Modify: `CLAUDE.md` (State files list; the `pm-status.py` paragraph; the progress-ledger claim)
- Generated: `skills/l3io-pm-{execute,plan,sync}/scripts/pm-status.py`, `.../scripts/tests/test-pm-status.py`, `.../references/status-files.md`

**Interfaces:**
- Consumes: everything from Tasks 1-5
- Produces: payload copies in sync; `npm run check:scripts` green

- [ ] **Step 1: Add `events.jsonl` to the layout diagram in `status-files.md` §1**

In the tree diagram, after the `issues.yaml` line:

```
│   ├── events.jsonl                        ← append-only transition log
```

And after the diagram's trailing prose, add:

```markdown
`events.jsonl` is an append-only JSON-lines log, one object per status or actuals
write, appended automatically by `set-status`/`set-actual` under `flock`. It is the
only place per-status *dwell* time can come from: `updated_at` records just the last
write and is overwritten by any field change. It is committed, and it is the one
project-level log rather than one per sprint — per-sprint files would fragment the
timeline and turn cross-epic velocity into a multi-file join. Absent on projects that
predate it, in which case the progress report falls back to `updated_at` and labels
its dwell figures approximate.
```

- [ ] **Step 2: Add `report` to the addressing command table in `status-files.md`**

Alongside the existing `progress` row:

```markdown
| `report` | `--state-root` (+ optional `--plan`); walks every epic, addresses none individually |
```

- [ ] **Step 3: Update `CLAUDE.md`**

In the **State files** bullet list, after the `state/issues.yaml` entry:

```markdown
- `state/events.jsonl` — append-only transition log (one JSON object per status/actuals write, `flock`-guarded); the source for per-status dwell time and the progress report's velocity view.
```

Replace the sentence claiming a per-run progress trail — currently *"Each PM skill activates it in a Load the Status Helper step and writes a per-run progress trail to `{sprint|epic_root_dir}/progress.log`"* — with:

```markdown
Each PM skill activates it in a *Load the Status Helper* step. Every status and
actuals write also appends to `{implementation_artifacts}/state/events.jsonl`
automatically (opt out per call with `--no-events`); this replaced the optional
`--ledger` flag, which no step file ever passed, so no progress trail was ever
written. `pm-status.py report` renders that log plus the state tree as a
plan-aware progress view (`--format tree|json|md`, `--watch`, `--all`).
```

- [ ] **Step 4: Run the sync and the drift check**

```bash
npm run sync:scripts && npm run check:scripts
```

Expected: sync reports the copied files; check exits 0.

- [ ] **Step 5: Verify a payload copy actually got the new command**

```bash
python3 skills/l3io-pm-execute/scripts/pm-status.py --version
grep -c "def cmd_report" skills/l3io-pm-plan/scripts/pm-status.py
```

Expected: `pm-status.py 2.3.0`; count `1`.

- [ ] **Step 6: Commit**

```bash
git add -A skills/ CLAUDE.md
git commit -s -m "docs(l3io-pm): document events.jsonl and sync payload copies

Adds the event log to the state-layout contract and corrects CLAUDE.md, which
described a per-sprint progress.log that was never written because --ledger was
optional and unpassed."
```

---

### Task 7: `/l3io-pm-help progress`

**Files:**
- Modify: `skills/l3io-pm-help/SKILL.md`

**Interfaces:**
- Consumes: `pm-status.py report`; help's existing `{pm_state_root}`, `{planning_artifacts}`, `{pm_status}`, `{pm_status_present}` bindings

- [ ] **Step 1: Add the keyword dispatch to "On Activation"**

After the existing setup-keyword paragraph:

```markdown
**Recognized argument — `progress`:** run section 1 (config) and section 2 (layout
detection) exactly as written, then jump to [Progress Mode](#progress-mode) and skip
sections 3-5. The layout gate still applies: a legacy tree short-circuits to the
migration recommendation, because the progress report reads only the sharded layout.
```

- [ ] **Step 2: Add the Progress Mode section**

Append after section 5:

```markdown
### Progress Mode

Invoked with the `progress` argument. Read-only.

**When `{pm_status_present}` is `absent`:** print this and stop — the report is the
one thing here that genuinely needs the helper, because it computes dwell times and
phase roll-ups:

```
pm-status.py is not installed yet, so the progress report cannot be computed. It
self-installs the first time you run /l3io-pm-plan or /l3io-pm-execute.
```

**Otherwise** run:

```bash
python3 {pm_status} report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree
```

Pass `--all` when the user asked to include finished work ("everything", "including
done", "including archived"). Print the output verbatim — do not summarize or
re-format it; it is already the rendered view.

Then add one line pointing at the live view, because that is the part that answers
"what is happening right now" during a long run:

```
For a live view during a run: python3 {pm_status} report --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml --watch 15
```

If the report's output contains `⚠ STALE LOCK`, append the existing clear-lock
recommendation from section 5 for each affected epic. Do not re-derive stale-lock
state yourself — the report already computed it from `_lock.ttl_minutes`.
```

- [ ] **Step 3: Update the skill's frontmatter description**

Change the `description` line to:

```yaml
description: Read project state and recommend the exact next l3io-pm action. Use /l3io-pm-help progress for a plan-aware progress tree (which phase, epic, sprint, and stories are in flight).
```

- [ ] **Step 4: Verify the referenced command actually works end-to-end**

Build a throwaway tree and run the exact command the skill prints:

```bash
T=$(mktemp -d); mkdir -p $T/state/active/epic-001/sprint-01
printf "key: 'E001'\ntitle: 'T'\nstatus: in-progress\n" > $T/state/active/epic-001/epic.yaml
printf "key: 'S01'\nepic: 'E001'\nstatus: in-progress\n" > $T/state/active/epic-001/sprint-01/sprint.yaml
printf "key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n" > $T/state/active/epic-001/sprint-01/E001-S01-001.yaml
python3 skills/_shared/pm-status.py report --state-root $T/state --format tree; rm -rf $T
```

Expected: a tree naming `E001`, `S01`, `E001-S01-001`, and a Totals block. Exit 0.

- [ ] **Step 5: Commit**

```bash
git add skills/l3io-pm-help/SKILL.md
git commit -s -m "feat(l3io-pm): add progress mode to l3io-pm-help

Reuses help's config resolution and layout detection, and hands off to
pm-status.py report rather than re-deriving anything."
```

---

### Task 8: Live render points in `/l3io-pm-execute`

**Files:**
- Modify: `skills/_shared/steps/execute/step-05-epic-loop.md`
- Modify: `skills/_shared/steps/sprint/step-04-sprint-closure.md`
- Modify: `skills/_shared/steps/closure/epic-closure.md`

**Interfaces:**
- Consumes: `pm-status.py report`
- Produces: rendered trees at serialized points; regenerated `md` report at closure boundaries

- [ ] **Step 1: Add the render contract at the top of `step-05-epic-loop.md`**

After the existing intro lines:

```markdown
## Progress rendering — only where execution is serialized

This step dispatches epics **concurrently** inside a parallel phase. Several epic
subagents each printing a progress tree would interleave into unreadable output, and
subagent stdout is buried anyway (the contract there is a one-line `DONE — [metrics]`).
So render only at points where exactly one writer is producing output:

| Point | Render |
|---|---|
| Phase start, phase end (this step, top level) | Yes |
| Sprint boundary when the phase holds a single epic | Yes (see step-04-sprint-closure.md) |
| Sprint boundary inside a parallel phase | No |
| Story boundary | Never |

Nothing is lost by suppressing: every transition still lands in
`{implementation_artifacts}/state/events.jsonl`, so `report --watch 15` in a second
terminal gives full-resolution live detail while the run's own output stays legible.
Mention that once, at phase start.

Render with:

```bash
python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree
```

Print the output verbatim. It is read-only and cannot affect execution.
```

- [ ] **Step 2: Add the phase-start render**

Immediately before the dispatch decision at "If `parallel_flag=true` AND `len(epics) > 1`", insert:

```markdown
**Render progress (phase start).** Run the `report` command above and print it
verbatim. On the first phase of the run, also print:

```
Live view during this run: python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} --plan {planning_artifacts}/plan-output-meta.yaml --watch 15
```

Bind `{single_epic_phase}` = `true` when this phase dispatches exactly one epic, else
`false`, and pass it into every sprint subagent's context block — the sprint-closure
step reads it to decide whether it may render.
```

- [ ] **Step 3: Add the phase-end render**

After all epics of the phase have returned and before advancing to the next phase:

```markdown
**Render progress (phase end).** Run the `report` command above and print it verbatim,
so the phase's net effect is visible in one place before the next phase starts.
```

- [ ] **Step 4: Add the conditional sprint-boundary render to `step-04-sprint-closure.md`**

At the end of the step, after status writes and before the `DONE —` line:

```markdown
## Progress render and report regeneration

**Render (conditional).** Only when `{single_epic_phase}` is `true` — inside a parallel
phase this output would interleave with sibling epics and is suppressed by design (see
`step-05-epic-loop.md`). When true:

```bash
python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree
```

**Regenerate the committed report (always).** Closure is a natural commit point, and
regenerating per story transition would churn git and put parallel subagents in
contention over one file:

```bash
python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format md --out {implementation_artifacts}/progress-report.md
```

The file is a generated view and carries a header saying so. Never hand-edit it;
regenerate it.
```

- [ ] **Step 5: Add the same regeneration to `epic-closure.md`**

At the end of the step, before the `DONE —` line, add the identical `--format md --out`
block from Step 4 plus an unconditional tree render (epic closure runs once per epic,
after its sprints are finished, so it is not in contention with sibling sprints):

```markdown
## Progress render and report regeneration

Render the tree and regenerate the committed report:

```bash
python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree

python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format md --out {implementation_artifacts}/progress-report.md
```
```

- [ ] **Step 6: Sync and check**

```bash
npm run sync:scripts && npm run check:scripts
```

Expected: exit 0. These are shared step files, so the three PM skills' `steps/` copies update.

- [ ] **Step 7: Commit**

```bash
git add -A skills/
git commit -s -m "feat(l3io-pm): render progress at serialized points during execute

Phase boundaries always render; sprint boundaries only when the phase holds a
single epic, because parallel epic subagents would interleave their output. The
committed md report regenerates at closure boundaries, not per transition."
```

---

### Task 9: Fold the hierarchy into the util skill's `stats` mode

**Files:**
- Modify: `skills/l3io-util-cleanup/SKILL.md` (Stats Mode, ~lines 1505-1590)

**Interfaces:**
- Consumes: `pm-status.py report`
- Produces: `stats` prints the hierarchy while keeping backlog/calibration/anomaly sections; still writes nothing

- [ ] **Step 1: Replace Step ST2's manual walk with a `report` call**

Replace the "Walk the sharded tree and count" body — the `ls -d`/per-file enumeration —
with:

```markdown
**Step ST2 — Compute the hierarchy**

Do not walk the tree by hand: `pm-status.py` is the only component that resolves a node
key to a path, and duplicating the walk here would drift from it. Run:

```bash
python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format json
```

This is read-only — `report` writes only when `--out` is passed, which it is not here.

If `{project-root}/_bmad/scripts/pm-status.py` does not exist, print this and fall back
to the counts-only walk described in Step ST2b:

```
pm-status.py is not installed yet — showing counts only, without the plan-aware
hierarchy. It self-installs the first time you run /l3io-pm-plan or /l3io-pm-execute.
```

From the JSON take `totals` (epics/sprints/stories by status), `phases`
(`phase`, `epic_done`, `epic_total`), and `flags` (`placement` entries are the placement
anomalies this mode already reported; `stuck` and `stale-lock` are new and worth
surfacing here too).

**Step ST2b — Counts-only fallback**

Only when `pm-status.py` is absent. Enumerate as before:

```bash
ls -d {pm_state_root}/{planned,active,archived}/epic-*/ 2>/dev/null
```

For each epic directory read `epic.yaml`; for each `sprint-{nn}/` read `sprint.yaml`; for
each `*.yaml` other than `sprint.yaml` read the story node. Accumulate counts by status
at each level.
```

- [ ] **Step 2: Keep the sections `report` does not cover**

Leave the existing bullets for **Backlog items** (`{pm_issues_file}` by severity),
**Last closed sprint**, **Last closed epic**, and **Calibration file** exactly as they
are — `report` does not compute any of them. Add a note under Step ST2:

```markdown
`report` does not cover the backlog, calibration file, or last-closed markers. Read
those as described below; they remain part of this dashboard.
```

- [ ] **Step 3: Update the Step ST3 dashboard template**

Replace the flat counts block with the hierarchy, keeping the rest:

```markdown
**Step ST3 — Print dashboard**

Print the `tree` view first, then the sections `report` does not cover. Re-run with
`--format tree` rather than re-rendering the JSON by hand:

```bash
python3 {project-root}/_bmad/scripts/pm-status.py report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree
```

Then append:

```
----------------------------------------------------------------
Backlog items
  Critical: {n}  High: {n}  Medium: {n}  Low: {n}  total: {n}
Last sprint closed:  Epic {nnn} / Sprint {nn}  (or "none")
Last epic closed:    E{nnn} — {title}          (or "none")
Calibration file:    {version}, {n} scope samples  (or "not found")
Layout:              Sharded state tree
================================================================
```

Placement anomalies no longer need a separate line — they appear in the tree's
Anomalies block. Add `--all` when the user asked to include archived epics.
```

- [ ] **Step 4: Update the mode's one-line description**

In the frontmatter `description` and the Modes list, change the `stats` wording from
"walks the sharded state tree for counts of epics, sprints, and stories by status" to:

```
plan-aware progress dashboard — phase/epic/sprint/story hierarchy with stuck-item
flags, plus backlog size by severity and last closed sprint/epic
```

- [ ] **Step 5: Verify the JSON contract the step relies on**

```bash
T=$(mktemp -d); mkdir -p $T/state/active/epic-001/sprint-01
printf "key: 'E001'\ntitle: 'T'\nstatus: in-progress\n" > $T/state/active/epic-001/epic.yaml
printf "key: 'S01'\nepic: 'E001'\nstatus: in-progress\n" > $T/state/active/epic-001/sprint-01/sprint.yaml
python3 skills/_shared/pm-status.py report --state-root $T/state --format json \
  | python3 -c "import json,sys; m=json.load(sys.stdin); print(sorted(m)); print(m['totals'])"
rm -rf $T
```

Expected: keys include `flags`, `phases`, `plan`, `totals`, `unplanned_epics`; totals show `epics {'in-progress': 1}`.

- [ ] **Step 6: Commit**

```bash
git add skills/l3io-util-cleanup/SKILL.md
git commit -s -m "feat(l3io-util): make stats a plan-aware progress dashboard

Delegates the walk to pm-status.py report instead of duplicating it, keeping the
backlog, calibration, and last-closed sections it uniquely covers."
```

---

### Task 10: Delete the dead `src/` tree

**Files:**
- Delete: `src/` (untracked; contains only two orphaned `__pycache__` bytecode files)

- [ ] **Step 1: Confirm nothing is tracked and nothing references it**

```bash
git ls-files | grep -c "^src/" || true
find src -type f -not -name "*.pyc" | wc -l
grep -rn "\bsrc/" package.json scripts/ .claude-plugin/ .github/ 2>/dev/null | grep -v node_modules || echo "NO REFERENCES"
```

Expected: `0` tracked; `0` non-pyc files; `NO REFERENCES`.

- [ ] **Step 2: Delete**

```bash
rm -rf src/
```

- [ ] **Step 3: Verify the build and tests are unaffected**

```bash
npm run check:scripts && cd skills/_shared/tests && python3 test-pm-status.py 2>&1 | tail -3
```

Expected: check exits 0; suite OK.

- [ ] **Step 4: No commit needed**

`src/` held no tracked files, so `git status` is unchanged by the deletion. Confirm:

```bash
git status --porcelain | grep "src/" || echo "nothing to commit for src/"
```

---

### Task 11: Rename `l3io-util-cleanup` → `l3io-util-doctor` with a deprecation forwarder

**Files:**
- Rename: `skills/l3io-util-cleanup/` → `skills/l3io-util-doctor/`
- Create: `skills/l3io-util-cleanup/SKILL.md` (forwarder only), `skills/l3io-util-cleanup/module.yaml`
- Create: `.claude/commands/l3io-util-doctor.md` (symlink)
- Modify: `.claude-plugin/marketplace.json:59`, `scripts/sync-shared-scripts.mjs:77`, `skills/_shared/steps/shared/step-00-activate.md`, `skills/l3io-pm-help/SKILL.md`, `README.md`, `CLAUDE.md`, `docs/getting-started.md`, `docs/architecture.md`, `docs/l3io-util-reference.md`

Do **not** rewrite `CHANGELOG.md` or `docs/superpowers/plans|specs/*` — those are historical record.

- [ ] **Step 1: Move the skill and its command symlink**

```bash
git mv skills/l3io-util-cleanup skills/l3io-util-doctor
git rm .claude/commands/l3io-util-cleanup.md
ln -s ../../skills/l3io-util-doctor/SKILL.md .claude/commands/l3io-util-doctor.md
git add .claude/commands/l3io-util-doctor.md
```

- [ ] **Step 2: Update the skill's own identity**

In `skills/l3io-util-doctor/SKILL.md` frontmatter set `name: l3io-util-doctor`. Replace
every self-reference — `grep -n "l3io-util-cleanup" skills/l3io-util-doctor/SKILL.md`
lists them; all become `l3io-util-doctor`. Same in `module.yaml` and `customize.toml`
(keep the `[workflow]` root key — this is a workflow skill, not a memory agent).

- [ ] **Step 3: Update the registries**

`.claude-plugin/marketplace.json` line 59: `"./skills/l3io-util-cleanup"` →
`"./skills/l3io-util-doctor"`, and add a second entry `"./skills/l3io-util-cleanup"` for
the forwarder so the deprecated command still installs.

`scripts/sync-shared-scripts.mjs` `allSkillDirs`: rename `"l3io-util-cleanup"` to
`"l3io-util-doctor"` and add `"l3io-util-cleanup"` — the forwarder needs the shared
config-resolution reference and module-setup asset too, or its own `references/` will be
missing when `check:scripts` runs.

- [ ] **Step 4: Write the forwarder skill**

`skills/l3io-util-cleanup/SKILL.md`:

```markdown
---
name: l3io-util-cleanup
description: Deprecated — renamed to l3io-util-doctor. Forwards to it.
---

# l3io-util-cleanup (deprecated)

Communicate all responses in `{communication_language}`.

This skill was renamed to **`l3io-util-doctor`**. "Cleanup" described about three of
its fifteen modes; the default behavior is a diagnose-report-repair health check.

Tell the user exactly once:

```
/l3io-util-cleanup has been renamed to /l3io-util-doctor. Running it for you now —
please use the new name from here on.
```

Then load `{project-root}/skills/l3io-util-doctor/SKILL.md` (or the installed
equivalent) and execute it with the same arguments you received, unchanged. Do not
re-implement any mode here.
```

`skills/l3io-util-cleanup/module.yaml`: copy the renamed skill's `module.yaml` and set
the skill name to `l3io-util-cleanup`. Leave the version alone — `postbump` maintains it.

- [ ] **Step 5: Update the cross-references**

```bash
grep -rln "l3io-util-cleanup" \
  skills/_shared skills/l3io-pm-help README.md CLAUDE.md \
  docs/getting-started.md docs/architecture.md docs/l3io-util-reference.md
```

In each, replace `l3io-util-cleanup` with `l3io-util-doctor` (these are all live
recommendations like "run `/l3io-util-cleanup migrate-state`"). Then add one line to
`README.md` in the module table noting the old name still works and is deprecated.

- [ ] **Step 6: Sync, check, and verify nothing live still points at the old name**

```bash
npm run sync:scripts && npm run check:scripts
grep -rn "l3io-util-cleanup" skills/ docs/getting-started.md docs/architecture.md \
  docs/l3io-util-reference.md README.md CLAUDE.md \
  | grep -v "skills/l3io-util-cleanup/" | grep -v "deprecated" || echo "NO STALE REFS"
```

Expected: check exits 0; `NO STALE REFS`.

- [ ] **Step 7: Verify both command names resolve**

```bash
test -f .claude/commands/l3io-util-doctor.md && head -3 .claude/commands/l3io-util-doctor.md
test -f skills/l3io-util-cleanup/SKILL.md && grep -c "l3io-util-doctor" skills/l3io-util-cleanup/SKILL.md
python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); \
print([s for s in json.dumps(d).split('\"') if 'l3io-util' in s])"
```

Expected: the symlink resolves to the renamed SKILL.md; the forwarder mentions the new
name; marketplace lists both paths.

- [ ] **Step 8: Commit**

```bash
git add -A skills/ .claude/commands/ .claude-plugin/marketplace.json \
  scripts/sync-shared-scripts.mjs README.md CLAUDE.md docs/
git commit -s -m "refactor(l3io-util)!: rename l3io-util-cleanup to l3io-util-doctor

'Cleanup' described 3 of 15 modes; the default behavior is a diagnose-report-repair
health check. The old name ships as a deprecation forwarder, following the
bmad-editorial-review -> bmad-review precedent. Historical records in CHANGELOG and
docs/superpowers are left unrewritten.

BREAKING CHANGE: /l3io-util-cleanup is deprecated in favor of /l3io-util-doctor.
The old command still works and forwards, and will be removed in a future release."
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task |
|---|---|
| Progress model schema | 3 |
| Event log (auto-write, flock, `--no-events`, one project-level log) | 1 |
| Reader safety / unparseable node tolerance | 3 (`unreadable` flag) |
| Renderers `tree`/`json`/`md` | 5 |
| `--watch` | 5 |
| Surface: CLI `report` | 5 |
| Surface: `/l3io-pm-help progress` | 7 |
| Surface: execute-loop render points | 8 |
| Surface: `stats` fold-in | 9 |
| Archived omitted unless `--all`, denominators stay true | 3, 4 |
| Stuck flags with fixed thresholds | 2 |
| Stale lock reuses `_lock.ttl_minutes` | 3 |
| Degradation: no events / no plan / legacy layout / no pm-status.py / bad node | 2, 4, 7, 9, 3 |
| Testing list | 1-5 |
| Chore: delete `src/` | 10 |
| Chore: rename + forwarder | 11 |

No gaps. The spec's "md report is a view, never a source of truth" requirement is met by the generated-by header in `render_md` (Task 5) and the "never hand-edit" note in Task 8.

**2. Placeholder scan**

No `TBD`/`TODO`/"similar to Task N"/"add appropriate error handling". Every code step carries real code; every verification step carries a runnable command and an expected result.

**3. Type consistency**

- `dwell_hours(node, events_index, now=None) -> (float|None, bool)` — same signature at every call site in Tasks 2 and 3.
- `compute_flags(level, key, status, dwell, exact) -> list[dict]` — consistent; `level` is always one of `"story"`/`"sprint"`/`"epic"`, matching `STUCK_THRESHOLDS` keys.
- `build_progress_model(state_root, plan=None, include_archived=False, now=None)` — the `plan` parameter is the `{"meta":…, "phases":…}` dict that `load_plan` returns, and `model["plan"]` is `plan["meta"]`. Consistent between Tasks 3, 4, and 5.
- `_build_sprint_detail` returns `(detail, flags)`; only `build_epic_detail` calls it, and it unpacks both.
- Flag dicts always carry `kind`; `stuck` additionally carries `dwell_hours`/`threshold`/`exact`, which is what `render_tree`'s approximate-dwell note and Task 9's JSON contract read.

One fix applied inline during review: Task 3's tests referenced `STATUS_FOR_DIR`, which is defined at line 1557 — *after* `rollup_epic` but *before* the new helpers' insertion point, so the reference resolves at call time regardless. No move needed.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-17-plan-aware-progress-reporting.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batched with checkpoints for review.

**Which approach?**
