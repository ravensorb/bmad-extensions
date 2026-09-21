### 1. Load paths from config

Resolve config through BMad core's resolver — full contract in
`{skill-root}/references/config-resolution.md`:

```bash
uv run --python 3.11 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root}
```

If the resolver is missing or fails, BMad core is not installed here — stop and tell the
user to run the BMad installer. Extract, applying the default when a key is absent:

- `{output_folder}` — `core.output_folder` (default `{project-root}/_bmad-output`)
- `{implementation_artifacts}` — `modules.l3io-pm.implementation_artifacts`
  (default `{output_folder}/implementation-artifacts`)
- `{planning_artifacts}` — `modules.l3io-pm.planning_artifacts`
  (default `{output_folder}/planning-artifacts`)
- Set `{pm_state_root}` = `{implementation_artifacts}/state`
- Set `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- Set `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py` (self-installed by the
  other PM skills; l3io-pm-help only reads, it does not self-install)

Then check whether `{pm_status}` is actually on disk and bind `{pm_status_present}`:

```bash
[ -f {project-root}/_bmad/scripts/pm-status.py ] && echo present || echo absent
```

**No staleness check.** This skill has no `module.yaml` of its own to compare against — that
file lives only at each module's home (`skills/l3io-pm-setup/assets/module.yaml`), and reading
a sibling skill's path from here would be the cross-skill path read this package avoids
elsewhere. Presence is the only signal l3io-pm-help can honestly report; it does not guess at
version freshness.

**Never invoke `{pm_status}` when it is absent.** On a fresh install nothing has
self-installed it yet, so every `{pm_status}` call below is conditional: when
`{pm_status_present}` is `absent`, read each `epic.yaml` directly instead (it is plain YAML).

Note in the report, when absent:

```
pm-status.py not installed yet — reading epic.yaml files directly. Run /l3io-util-doctor to
install it (l3io-pm-help only reads; it does not self-install).
```

Not a hard blocker: everything l3io-pm-help needs can still be read.

