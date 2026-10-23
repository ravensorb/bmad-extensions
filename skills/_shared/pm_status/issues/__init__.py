"""pm_status.issues -- the deferred-issue lifecycle, and the ADR number allocator.

`state/issues.yaml` (open) and `state/issues-resolved.yaml` (resolved), every verb that
changes them, and the integrity audit over them. Spec:
docs/superpowers/specs/2026-09-10-issue-lifecycle-design.md; ADR-0002.

It sits ABOVE `nodes` (it loads and saves story nodes when promoting) and BELOW the status
verbs and the plan operations, which are its consumers. `promote` also reaches UP into
`metrics` for the estimate it writes onto a promoted story -- `metrics` sits between
`nodes` and `issues`, which is what keeps that edge one-way.

A directory rather than one module because the bucket is ~1,970 lines and the package's
per-file budget is 1,500 (check:docs check 12). The four modules are a strict layering,
and the order below is the import order:

    adr        standalone -- the ADR register allocator; `audit` reads it for finding 1k
    store      IssueStore, the schema constants, append / resolve / update
    promote    promote-issue, schedule-issue, the story-key allocator
    audit      audit-issues, repair-issue, the legacy normalisers, list-issues

There is no edge in the other direction anywhere, so a cycle between two of these files is
a design error, not a plumbing problem to route around with a deferred import.

This file imports the four submodules and re-exports NOTHING, for the same reason
`metrics/__init__.py` does not: a name re-exported here would sit beside
`issues.<mod>.<name>` as a second binding of the same function, and `mock.patch` on one
would not reach the other. `__main__.py` re-exports what the facade needs, from the
defining module, and leaves `resolve_issue_core` -- the one patch target in this bucket --
out of every re-export list.
"""
from __future__ import annotations

from . import (  # noqa: F401 -- submodule imports, so `issues.<mod>` resolves on the package
    adr,
    audit,
    promote,
    store,
)
