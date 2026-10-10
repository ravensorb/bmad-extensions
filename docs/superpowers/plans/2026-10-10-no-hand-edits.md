# Every Recommended Action Has a Command — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Never ask a user to hand-edit something this package writes. Every finding and every
blocked path names the command that resolves it, and that command is verified to exist and to
behave as the message claims.

## What the goal does and does not cover

Three cases came out of the sweep, and they are not the same.

**The rule is one sentence: the human decides, the agent edits.** "Go and edit this yourself"
is never an acceptable outcome, in any file. What varies is only how much the agent may decide
on its own before acting.

| Case | Rule | Why |
|---|---|---|
| **Our machine-written state and artifacts** — `state/**`, `plan-output-meta.yaml`, `epic.yaml` | Agent acts. **Never** ask for a hand edit; if no command exists, that is the defect | We own the writer. Free-form YAML edits under parallelism are what `pm-status.py` exists to prevent |
| **The user's own documents** — their `CLAUDE.md`, `AGENTS.md` | Agent **shows the ambiguity, asks which reading is right, then makes the edit** | Never *guess* — the marker engine refuses an ambiguous file precisely so nothing picks a `l3io:begin` at random. But once a human has resolved the ambiguity, locating and splicing the lines is mechanical work there is no reason to hand back |
| **Human judgement** — "check these ADR mentions still read correctly" | Agent surfaces each one with its context, the human rules on it, **the agent applies the ruling** | Only the *decision* is human. Making the user then go and perform the edit is handing back the easy half |

An earlier draft of this plan exempted the middle row entirely, on the grounds that the file
is the user's. That conflated two different things — *deciding* what the file should say, which
is theirs, and *performing the edit*, which is not. Refusing to guess does not require refusing
to type.

## The defect that started this

A reorg's stated objective is to remove dependencies crossing an epic boundary, so the epic
dependency becomes unnecessary and more epics land in one parallel phase. **Measured, the second
arrow does not happen:**

| | cross-epic edges | phases |
|---|---|---|
| Before reorg | 2 | `[1:[E003]], [2:[E001]]` |
| After reorg | **0** | `[1:[E003]], [2:[E001]]` — **identical** |

Phases come from **epic-level** `depends_on`. Reorg cannot touch it — `TARGET_FIELDS` is
`{key, epic, sprint, order}` and the derivation emits only `create-sprint`, `reparent-story`,
`retire-epic`. So the now-vestigial `E001 depends_on E003` keeps serialising two epics that no
longer need it, and `max_parallel_subagents` never engages because no phase gained an epic.

**And the obvious remedy does not exist.** `set-depends-on` is append-only (`--add KEY`,
repeatable), and `set-field` refuses list fields outright — its own help says it would store
`"['E001']"` as a string "which a reader takes for a scalar". So today the only way to drop an
epic dependency is to hand-edit `epic.yaml`, which the state contract forbids.

## Decisions

Settled in discussion 2026-10-10.

| # | Decision | Rationale |
|---|---|---|
| D1 | The finding surfaces in **reorg's post-apply report**, not on every plan run | It is contextual, not continuous. A long-standing epic dependency with no story edges is often deliberate — "ship the API before the client" is real sequencing with zero technical edges — so firing every plan run is noise on exactly the projects that organised most carefully. The moment a reorg removed the last justifying edge, it is near-certain |
| D2 | **Report-only.** Reorg does not gain an operation that drops a dependency | The target format's safety argument is that it is impoverished — a row says only *where a node belongs*. Dropping a dependency is a semantic edit to the plan graph, and ADR-0011's argument rests on the move set being pure re-placement |
| D3 | Every such message **names the command**, and the command is verified to exist | This whole plan exists because a recommendation was nearly written for an action the toolchain could not perform |

## Global Constraints

- **This repo's `CLAUDE.md` does not ship.** A consuming project sees only payload, so every rule a consuming agent must follow belongs in a step file, a script docstring, or the shipped instruction block — never here.
- `skills/_shared/` is canonical. **Edit there, then `npm run sync:scripts`.** Per-skill edits are silently overwritten.
- **Regenerate manifests** with `node scripts/write-payload-manifest.mjs` after any skill file changes; `check:manifest` now fails on any skill edit until you do.
- **Check 26:** no file under `skills/` assembles a state path.
- **Check 31:** no `/l3io-*` invocation in markdown carries a `--flag`.
- `pm-status.py` is the only writer of `state/**`, and takes **no graph library** (ADR-0011 rationale: 616 ms import against 92 call sites).
- Conventional Commits, every commit signed off (`git commit -s`).

## Review Focus

1. **Removing a dependency that is still justified.** The inverse mistake: dropping `E001 depends_on E003` while story edges still cross that boundary leaves the phase graph unable to order work it must order. → Task 1 must refuse or loudly warn, and the check is already computable.
2. **Removing the last entry.** `depends_on: []` and an absent `depends_on` must mean the same thing to every reader. → Task 1.
3. **A command named in a message but never run.** The `suggests` strings and step-file remedies are prose today; nothing asserts they parse. → Task 4.
4. **Readiness override is a deliberate act.** Making it a command must not make it *casual* — the friction is the point, only the mechanism changes. → Task 5.
5. **An ambiguous instruction file must still not be auto-repaired.** Task 6 improves the diagnosis only; a task that starts editing the user's prose has misread the goal.

---

## Execution order

Task 1 is a hard prerequisite: Tasks 2 and 3 are inert without it, because the message they
emit would name a command that does not exist — the exact defect this plan fixes. Tasks 5 and
6 are independent and may land in any order.

```
1 (verb) ──> 2 (finding) ──> 3 (step file renders the command) ──> 4 (check 4 covers it, free)
5 (readiness override) ──┐
6 (marker diagnosis)   ──┴──> 7 (check 34 locks it in — must land after both)
```

Task 7 last by necessity: a check that forbids the two instances cannot pass until they are
gone.

### - [x] Task 1: `set-depends-on --remove KEY`

The missing verb. Mirrors `--add`'s existing contract — repeatable, idempotent, order
preserved, all-or-nothing, every key validated before anything is written.

- Removing a key that is not present is a no-op, not an error (idempotent, like `--add`).
- **Refuse** when live story edges still cross that boundary (Review Focus 1), naming them.
  `--force` may override, because a deliberate business sequencing removal is legitimate.
- `--add` and `--remove` in one call: decide and document. Simplest is to refuse the
  combination rather than define an order nobody will remember.
- An emptied list: write `depends_on: []`, and confirm every reader treats it as absent
  (Review Focus 2).
- **Tests:** removes; idempotent on absent; refuses while justified; `--force` overrides;
  emptied list reads back as no dependencies; a sprint node still exits 2.

### - [x] Task 2: the `unneeded-epic-dependency` finding

`plan-graph.py analyze` gains the inverse of `unbacked-cross-epic-dependency`: an epic
declaring `depends_on: [X]` with **zero** story edges crossing into X.

- Severity `info` per D1 — it must not trigger the plan-run reorg advisory, which routes on
  severity alone and would otherwise recommend a tool that structurally cannot fix it.
- `measured` carries the epic pair and the edge count (zero), so the report can be specific.
- **Tests:** fires on a declared-but-unjustified dependency; silent when edges justify it;
  silent on an epic with no `depends_on`; never appears at `warn`.

### - [x] Task 3: reorg's post-apply report names the next two commands

After apply, re-run `analyze` and report any `unneeded-epic-dependency` the reorg **caused** —
present now, absent before. Both measurements already exist in the flow (§3 and §6).

The message is the deliverable, and it is two commands and a reason:

```
↯ This reorg removed the last 2 story dependencies justifying E001 depends_on E003.
  Dropping it would let E001 and E003 run in the same parallel phase.

    uv run {pm_status} set-depends-on --state-root {pm_state_root} --epic E001 --remove E003
    /l3io-plan        # rebuild the snapshot so execution picks up the new order
```

Not a hand edit, not a description of a problem. State plainly that it is **optional** — the
dependency may be a deliberate sequencing decision this tool cannot see.

### - [x] Task 4: put every recommended command where the existing gate already looks

The reason this plan exists is that a recommendation was nearly shipped for an action the
toolchain could not perform. Close the class, do not just fix the instance.

**This needs no new checker.** Check 4 already judges every code-formatted `pm-status.py`
invocation in `skills/**/*.md` against the real argparse surface — its own header records that
the forward arm missed exactly these and was widened to cover "the commands agents actually
execute". So the rule is a placement rule, not a tooling one:

**The finding says what is wrong; the STEP FILE says what to run.** A command belongs in a
step file's code block, never in the analyzer's `suggests` string. `suggests` is a Python
string literal that no gate reads; the same text in a step file is validated for free, and a
message naming a flag that does not exist fails the build instead of reaching a user.

- Task 2's finding states the condition and names the epics. It does not carry a command.
- Task 3's step file renders the command, in a fenced block, from the finding's `measured`.
- **Tests:** plant a bad flag in that block and confirm check 4 fails (the discipline the
  check-docs suite already applies 113 times over).

### - [x] Task 5: readiness override stops being a hand edit

`step-03-load-plan.md` currently tells the user to *"edit `readiness:` in
`plan-output-meta.yaml` to amber"*. That file is **agent-written** (step-06 §4), not
`pm-status.py`-written, so the agent can set it — no new verb needed, only prose.

Keep the friction and move the mechanism: on explicit confirmation that the risk is accepted,
the agent rewrites the field and says so. A hand edit is not safer here, only more
error-prone — wrong field, wrong file, damaged YAML — and the confirmation is just as
deliberate.

### - [x] Task 6: diagnose the ambiguous instruction file precisely

`step-00-activate.md` §2 says `repair it by hand — see /l3io-doctor`, and **no doctor mode
exists for it** — the pointer is hollow.

**This must stop being a hand edit, without the engine ever guessing.** Both are achievable,
because they are different steps:

1. **Show the ambiguity concretely** — "two `l3io:begin` at lines 42 and 118; the one at 42 has
   no matching `l3io:end`" — with the surrounding lines, so the user can see what they are
   deciding about.
2. **Ask which reading is right.** This is the part the marker engine correctly refuses to
   decide, and the only part that needs a human.
3. **Make the edit.** Once a human has said which block is real, removing the other is
   mechanical, and handing that back is handing back the easy half.

Nothing outside the resolved markers is touched, and the file is never rewritten on a guess —
if the user declines to choose, say so and continue, exactly as today.

Drop the hollow `see /l3io-doctor`, or give it a real mode that performs the three steps above.
Do not leave it pointing at nothing.

### - [x] Task 7: check 34 — no runtime directive asks a user to hand-edit

Lands **after** Tasks 5 and 6, which remove the two instances; this is what stops them coming
back. A grep for known phrasings is a hand-kept list, which is the thing this repo distrusts —
but four existing checks are already this exact shape (**9** no directive reads
`skills/_shared/`, **14** no directive names the old ADR home, **17** no live doc does X,
**31** no `/l3io-*` invocation carries a `--flag`), so the pattern is idiomatic rather than
novel.

Scope it to runtime directives under `skills/` that tell a user to edit a path **this package
writes** — the state tree, `plan-output-meta.yaml`, `epic.yaml`. A directive about the user's
own document is judged by whether it ends in a command, not by whether it mentions editing.

Per this repo's own standard, the check carries a planted violation it must catch, and the
header must state what it does **not** reach: it reads phrasing, so a directive that asks for
a hand edit in words nobody anticipated will pass. It narrows the opening; it does not close
it.

---

## Validation Strategy

| Probe | Asserts |
|---|---|
| Build the before/after trees from the defect above, run `set-depends-on --remove`, re-run `phases` | the parallelism gain actually materialises — the whole point |
| `--remove` while a story edge still crosses | refused, and the message names the edges |
| Every command in a `suggests` string, extracted and parsed | Task 4's gate catches a named flag that does not exist |
| check 34 over the shipped tree | **zero remain** — every path either runs a command or asks a question and then runs one |
| a planted bad flag in Task 3's command block | check 4 fails the build, with no new checker written |
| a planted hand-edit directive | check 34 fails the build |

**Mutation testing required** for Task 1 (drop the still-justified refusal → its test must
fail), Task 4 (plant a bad flag in the step file's command block → check 4 must fail) and
Task 7 (plant a hand-edit directive → check 34 must fail).

**What cannot be validated, stated rather than glossed.** Tasks 5 and 6 are prose, and no gate
proves an agent follows prose. The split is worth being precise about, because the half that
would actually cause damage is the half that *is* mechanical:

- **Safety is guaranteed in code.** The marker engine refuses an ambiguous file. That is
  tested, and nothing in Task 6 can make it guess.
- **Wiring is guaranteed in code.** A doctor mode added by Task 6 needs a `module-help.csv`
  row and a routing-table entry, or `check:module` rule 9 fails; check 15 counts the modes.
- **The interaction is not.** That the agent asks before splicing, rather than doing either
  half alone, rests on the step file being unambiguous. Check 34 proves the old instruction is
  gone; nothing proves the new one is obeyed.

**Gates:** all seven, `npm run test:python`, `smoke:install` before release.

## Risks

- **Task 1 removes an ordering constraint.** It is the one change here that can make a plan
  run work in parallel that previously ran in sequence. The still-justified refusal is the
  guard; `--force` is the deliberate escape, and the report says the dependency may be
  intentional.
- **More parallelism meets a known limitation.** Concurrent epics share one working tree with
  no source-file independence check (`docs/superpowers/specs/2026-08-17-adaptive-parallelism-design.md`,
  unimplemented). Succeeding at this plan's goal pushes directly on that. Worth saying in the
  reorg report rather than discovering at dispatch.
- **Task 4 widens a gate over prose.** A false positive there blocks a build over a sentence.
  Scope it to lines that are already code-formatted commands, the same qualifier check 4 uses
  to stay off ordinary prose.
