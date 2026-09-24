# Skills and Sequence

Why each skill exists, when you reach for it, and the orders that make sense.

Eight skills across four modules is a lot of surface. The thing to understand first is that
**you invoke very few of them directly.** Two of the four modules mostly run *inside* the
execution engine, on your behalf, at points where their judgement is needed.

## The short version

| Skill | The problem it solves | How you use it |
|---|---|---|
| `l3io-util-doctor` | "Is this project in a shape the other skills can read?" | **Run it first**, after every install and upgrade |
| `l3io-arch-review` | "Is this design sound, and is the decision recorded?" | Directly at design time; otherwise **automatic** inside execution |
| `l3io-pm-plan` | "What order should this work run in, and how long will it take?" | Once per planning round |
| `l3io-pm-execute` | "Actually do the work, and don't let it close sloppily" | The engine — most of your runs |
| `l3io-sec-redteam` | "What would an adversary do with this?" | **Automatic** at closure; directly for ad-hoc reviews |
| `l3io-pm-help` | "What should I do next? Where is everything?" | Any time you are unsure. Read-only |
| `l3io-pm-sync` | "Keep GitHub Issues in step with this state" | Opt-in, when your team lives in Issues |
| `l3io-pm-setup` | "Record l3io-pm's project-level settings" | Only when you explicitly run `/l3io-pm-setup`, `configure`, or `install` |

## Why each one exists

### `l3io-util-doctor` — the entry point

Every other skill reads a state tree at `{implementation_artifacts}/state/`. If that tree is
missing, half-migrated, or in a legacy shape, the rest of the system either refuses or gives
you confusing answers. The doctor is what makes the project legible: with no argument it scans
for every known problem, reports findings, and proposes the fixes in dependency order behind
one confirmation.

It is also the documented post-upgrade step, because the installer refreshes skills but does
**not** migrate your data. And it self-installs the shared `pm-status.py` helper at activation —
comparing bytes rather than version strings, and never downgrading — so it repairs the runtime
as a side effect of running.

Reach for it: after install, after every upgrade, whenever something looks wrong, and for
`triage` (close backlog items already fixed) and `stats` (a progress dashboard).

### `l3io-arch-review` — before you build, and whenever a decision is made

This is the only module with **no runtime dependency on the others**; it works on a project
that uses none of the rest. It applies an engineering-standards charter in three modes: design
guardrails for a new project, review of an existing design or diff, and decision support that
records an ADR.

Its value inside this package is different from its value alone. Installed alongside `l3io-pm`,
it becomes the reviewer behind two gates that would otherwise be prose: the epic architecture
gate that runs *before* any sprint, and the drift reviews at sprint and epic closure. Without
it, those gates self-skip and the story-level check falls back to a built-in checklist.

Reach for it directly: at the start of a project, when weighing a load-bearing choice, or to
audit something specific. Otherwise it runs itself — see [what runs automatically](#what-runs-automatically-inside-execution).

### `l3io-pm-plan` — decide the order before spending money on it

Given epics and stories, planning answers what can run now, what is blocked, what can run in
parallel, and what it will cost. It validates readiness, elaborates thin stories, estimates all
five metrics, reads `depends_on` declarations, and produces a dated plan snapshot plus a stable
pointer that execution reads.

It exists because ordering decided up front is far cheaper than ordering discovered during a
run, and because an estimate recorded before the work is the only thing that makes the actual
recorded afterwards meaningful.

Reach for it: whenever you have more than one epic, or after adding work.

### `l3io-pm-execute` — the engine

This is where the work happens, and where most of the design effort went. It runs the plan,
one epic, or one sprint. Per story: dev, code review, then a fix loop capped at three
iterations. At sprint and epic closure: retrospective, drift review, security review, UX review,
triage, and a closure fix loop.

Two properties are worth knowing because they explain the rest of the system. First, it
dispatches **one agent to prepare a sprint, one per story, and one to close it** — short
sessions, because cost grows with the turns a single session accumulates, and every hand-off is
a file on disk rather than context carried forward. Second, **nothing closes with unresolved
Critical, High or Medium findings**; Low findings defer to a tracked backlog rather than being
forgotten.

Reach for it: most of the time. `/l3io-pm-execute` for the whole plan, `E001` for one epic,
`E001-S01` for one sprint.

### `l3io-sec-redteam` — the adversary you would not think to be

Adversarial security review through five threat lenses — external attacker, malicious insider,
chaos engineer, abusive legitimate user, and a design red team — with an AI-poisoning cross-cut
where AI components are in scope.

It exists as its own module because the questions it asks are not the questions a code reviewer
asks, and asking them as an afterthought produces afterthought answers.

You mostly do not invoke it: it runs at sprint and epic closure automatically when installed
and the work is code-bearing. Reach for it directly for an ad-hoc review of something specific.

### `l3io-pm-help` — the read-only oracle

Reads the project and tells you the single next action. With `progress` it forwards to
`/l3io-util-doctor stats` for the progress tree rather than rendering its own copy, and with
`list plan` it enumerates plan snapshots so you can see whether the pointer is stale.

It exists because the honest answer to "what now?" depends on state most people should not have
to hold in their heads: whether a plan exists, whether readiness is green, whether an epic holds
a stale lock, whether a migration is half-finished.

It is strictly read-only — it never writes state, and it is the one PM skill that does not even
self-install the helper. When it suggests clearing a lock, it prints the command for you to run.

Reach for it: whenever you are unsure, and after any interruption.

### `l3io-pm-sync` — only if your team lives in GitHub Issues

Mirrors state onto GitHub Issues in both directions: `push` creates and updates issues, `pull`
marks stories done whose issue closed as completed, `sync` does both. GitHub only.

It is opt-in and orthogonal. Nothing else depends on it, and skipping it costs you nothing but
the mirror.

### `l3io-pm-setup` — the module's setup skill

`l3io-pm` is the only multi-skill module in this package, so it is the only one with a
dedicated setup skill; `l3io-util`, `l3io-sec`, and `l3io-arch` each self-register from their
own single skill instead. Records `l3io-pm`'s project-level settings (`implementation_artifacts`,
`planning_artifacts`, and any other declared `module.yaml` variables) in the two human-authored
BMad config layers.

It never runs implicitly. `l3io-pm` declares no required settings, so an absent
`[modules.l3io-pm]` section is normal, not a first-run trigger — every PM skill works without
one. Run it only when you explicitly ask to install, configure, or reconfigure `l3io-pm`.

## What runs automatically inside execution

This is the part that surprises people. With `l3io-pm-execute` driving, these happen without
you asking:

| When | What runs | Condition | If not installed |
|---|---|---|---|
| Before any sprint of an epic | `l3io-arch-review` Mode B over the whole epic's design | CODE or MIXED work | The gate skips entirely — it never partially skips |
| Story preparation | The six-dimension technical-AC check | Always enforced | Falls back to a built-in checklist |
| Per story | Core dev, code review, fix loop | Always | — |
| Sprint closure | Retrospective, drift review (`l3io-arch-review`), security review (`l3io-sec-redteam`), UX review (legacy `bmad-ux-review`, else `bmad-ux`) | Code-bearing work; UX only for UI-facing stories | Each phase skips gracefully |
| Epic closure | All of the above at epic scope, plus issue triage and the closure report | Code-bearing work | Skips gracefully |

The consequence: installing `l3io-arch` and `l3io-sec` does not add steps you have to remember.
It adds reviewers to gates that already exist.

## Orders that make sense

### A new project

```
/l3io-arch-review design        → boundaries, initial ADRs, a docs skeleton
bmad-create-epics-and-stories   → the work itself (core BMad)
/l3io-util-doctor               → confirm the project is legible
/l3io-pm-plan                   → order, dependencies, estimates
/l3io-pm-execute                → run it
```

### A project that already has work underway

```
/l3io-util-doctor               → health check first, always
/l3io-pm-help                   → what is the next action?
/l3io-pm-execute E001           → or whatever it told you
```

### A legacy project, from before the sharded state layout

```
/l3io-util-doctor               → it detects the layout and sequences the migration
                                  behind one confirmation. Do not run the individual
                                  migration modes by hand.
/l3io-pm-help                   → confirm it now reads cleanly
```

If the doctor reports more than one layout present, it stops rather than guessing which is
authoritative. See [Upgrading](upgrading.md) for the ordered sequence and the rollback table.

### Day to day

```
/l3io-pm-help                   → what next
/l3io-pm-execute E001-S02       → run it
/l3io-pm-help progress          → watch, any time, read-only
```

### Any time, independently

- `/l3io-arch-review decision` — weigh a choice against the standards and record the ADR
- `/l3io-sec-redteam` — an ad-hoc adversarial review
- `/l3io-util-doctor triage` — close backlog items that are already fixed
- `/l3io-util-doctor stats` — a progress dashboard
- `/l3io-pm-sync` — reconcile with GitHub Issues

## Required, optional, and what happens without each

| Module | Required? | Without it |
|---|---|---|
| `l3io-pm` | The core of the package | No orchestration, planning, or closure discipline |
| `l3io-util` | **Required when using `l3io-pm`** (declared in `skills/l3io-pm-setup/assets/module.yaml`'s `dependencies:` list) | `l3io-pm-help` warns at every activation via `check-pm-status`; `progress` forwards to `l3io-util-doctor stats` and errors without it; state-layout migrations (`migrate-state`, `bootstrap-state`) and the plan-aware progress dashboard fail if reached. The marketplace bundle ships it alongside `l3io-pm`, so a standard install always carries it. |
| `l3io-arch` | Optional | The epic architecture gate skips; the story technical-AC gate falls back to a built-in checklist; drift reviews lose their reviewer |
| `l3io-sec` | Optional | Closure runs without a security review |

From core BMad and the official `bmm` module, these must be present: `bmad-code-review`,
`bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review` (adversarial lens — the
legacy `bmad-review-adversarial-general` is used only when it is absent), and
`bmad-sprint-planning` (readiness gate — the legacy `bmad-check-implementation-readiness` is
preferred when installed, because its presence is evidence `intent=readiness` may not be
understood there). Story enrichment and implementation prefer the legacy `bmad-create-story` and
legacy `bmad-dev-story` when installed, else this package runs its own in-package agent in their
place, so no `--shims` flag is ever needed. UX review is optional — the legacy `bmad-ux-review`
is preferred when installed, `bmad-ux`'s opt-in Reviewer Gate otherwise, and the phase skips
gracefully when neither is present.

## Which skills write state

Worth knowing before you run something on a project you care about.

| Skill | Writes state? |
|---|---|
| `l3io-pm-execute` | Yes — statuses, actuals, the event log, closure artifacts |
| `l3io-pm-plan` | Yes — plan snapshots, elaborated stories, estimates |
| `l3io-util-doctor` | Yes, but every change is confirmed first, and migrations preserve originals as `.legacy` |
| `l3io-pm-sync` | Yes — story statuses on `pull`, and the sync mapping store |
| `l3io-arch-review` | Writes ADRs and review reports, not PM state |
| `l3io-sec-redteam` | Writes findings reports, not PM state |
| `l3io-pm-help` | **No.** Read-only by design |

Every state write goes through one shared helper (`pm-status.py`) under a lock, which is what
makes concurrent epics safe.

## Where to go next

- [Getting started](getting-started.md) — prerequisites, install, and your first run
- [l3io-pm reference](l3io-pm-reference.md) — the full lifecycle and every subcommand
- [Architecture and execution model](architecture.md) — why the context boundary and the cost
  model are shaped the way they are
