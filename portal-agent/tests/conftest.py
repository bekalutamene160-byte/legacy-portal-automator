"""
conftest.py for legacy-portal tests.

Ensures the legacy-portal directory's PARENT is on sys.path so that
`import legacy_portal.app` works from the tests.

Directory layout:
    legacy-portal-automator/         <- this is what we add to sys.path
        legacy-portal/                <- the package
            __init__.py
            app.py
            tests/
                conftest.py           <- this file
"""

import sys
from pathlib import Path

# legacy-portal/ is two levels up from this conftest.py
# (conftest.py -> tests/ -> legacy-portal/)
# We want the PARENT of legacy-portal/ on sys.path so the package is importable.
PACKAGE_PARENT = Path(__file__).parent.parent.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))