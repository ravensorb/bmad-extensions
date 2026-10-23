"""Facade: makes `import pm_status` hand back __main__'s module object itself.

MIGRATION INSTRUMENT, not the end state. Tasks 2-5 move code into submodules behind this;
shrinking it to a real public surface is separate work after the suite is repointed.

Why an alias and not a copy of its names: the suite does `mock.patch.object(pm, "<name>", ...)`
in ~20 places and the code under test reads `__main__`'s own globals. A re-exported copy is a
different namespace, so those patches land on the copy and silently change nothing (measured: 20
failures, no AttributeError). It must be the same module object, so a patch is seen by the code.
It also carries underscore-prefixed names a star-import would skip (`_file_sha`, `_load_checked`).

Script-path bootstrap: the shipped binding runs `pm_status/__main__.py` as a script, where
`__package__` is empty and any relative import raises "no known parent package". The one-line
prologue in `__main__.py` (after the imports, before any relative import) loads THIS directory
as a package named `pm_status` from its own path, so submodules import normally. It must not
import by name: the installed directory is `pm-status`, which is not an importable identifier.
Never add a relative import above it. tests: TestInvocationModes.
"""
import sys

from . import __main__ as _main

sys.modules[__name__] = _main
