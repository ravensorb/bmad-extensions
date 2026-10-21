### 3. Read state files

```bash
ls -d {pm_state_root}/active/epic-*/ 2>/dev/null || echo "(none)"
ls -d {pm_state_root}/planned/epic-*/ 2>/dev/null || echo "(none)"
uv run {pm_status} list-issues --state-root {pm_state_root} --all --format json 2>/dev/null \
  || cat {pm_issues_file} 2>/dev/null || echo "(absent)"
cat {planning_artifacts}/plan-output-meta.yaml 2>/dev/null || echo "(absent)"
```

For each active/planned epic directory found, read its `epic.yaml` directly (key, title,
status, `_lock`, `depends_on`). If `{pm_status_present}` is `present`, you may instead use
`uv run {pm_status} show --state-root {pm_state_root} --epic {key}` for a computed roll-up
including sprint/story counts. If it is `absent`, use the direct read only.

Also surface one read-only health fact — state that is gitignored will never be committed,
which defeats the point of the layout:

```bash
if git -C {project-root} check-ignore -q {pm_state_root}; then
  echo "IGNORED $(git -C {project-root} check-ignore -v {pm_state_root})"
else
  echo TRACKED
fi
```

Only `-q` decides. `-v` exits 0 whenever **any** pattern matched, including a negation that
re-includes the path, so keying the decision on `-v` reports `IGNORED` for a path git actually
tracks — exactly the state a user is left in after correcting their `.gitignore`.

For `IGNORED`, the `-v` part is `source:line:pattern<TAB>path`. Include this in the snapshot,
naming the source file, line and pattern (it does not stop the recommendation, and you write
nothing). If that part is empty, the rule could not be located — say so instead of naming one:
```
⚠️  {pm_state_root} is gitignored by <source> line <line> (`<pattern>`) — project state will not
be committed. Negations must be written relative to the directory of the .gitignore that holds
the rule, one for each excluded parent directory down to the state directory (an absolute path
matches nothing). If the pattern excludes a parent directory, git cannot re-include from inside
it: that rule itself has to change or be narrowed.
```

