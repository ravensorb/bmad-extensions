"""Facade: makes `import pm_status` hand back __main__'s module object itself.

MIGRATION INSTRUMENT, not the end state. Tasks 2-5 move code into submodules behind this;
shrinking it to a real public surface is separate work after the suite is repointed.

Why an alias and not a copy of its names: the suite does `mock.patch.object(pm, "<name>", ...)`
in ~20 places and the code under test reads `__main__`'s own globals. A re-exported copy is a
different namespace, so those patches land on the copy and silently change nothing (measured: 20
failures, no AttributeError). It must be the same module object, so a patch is seen by the code.
It also carries underscore-prefixed names a star-import would skip (`_file_sha`, `_load_checked`).
"""
import sys

from . import __main__ as _main

sys.modules[__name__] = _main
