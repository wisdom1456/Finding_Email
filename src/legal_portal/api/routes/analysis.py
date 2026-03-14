"""Document analysis endpoints — backward-compatibility shim.

This module re-exports all public symbols from the split route modules
so that existing tests and imports continue to work unchanged.

Actual implementations live in:
  - _analysis_helpers.py  (shared helpers, models, constants)
  - analysis_core.py      (8 core endpoints + background processing)
  - chat_routes.py        (chat endpoints)
  - document_status_routes.py (document status endpoints)
  - gap_routes.py         (gap analysis endpoints + helpers)
  - letter_routes.py      (letter generation endpoints)
"""

# Re-export everything from the split modules.
# fmt: off
# isort: skip_file
from legal_portal.api.routes._analysis_helpers import *  # noqa: F401,F403
from legal_portal.api.routes.analysis_core import *  # noqa: F401,F403
from legal_portal.api.routes.gap_routes import *  # noqa: F401,F403
from legal_portal.api.routes.letter_routes import *  # noqa: F401,F403
from legal_portal.api.routes.chat_routes import *  # noqa: F401,F403
from legal_portal.api.routes.document_status_routes import *  # noqa: F401,F403
# fmt: on

# The router is intentionally NOT re-exported here.
# main.py registers each module's router independently.
# This import ensures that `from analysis import router` still works
# for any code that references it, but the router registered in main.py
# is analysis_core.router (which has the 8 core endpoints).
from legal_portal.api.routes.analysis_core import router  # noqa: F401,E402
