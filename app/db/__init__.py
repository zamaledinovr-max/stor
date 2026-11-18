"""Database package. `Base` and session helpers are re-exported here.

ORM models are intentionally not imported in this module: models import
`app.db.base`, and importing them from the package __init__ would create a
circular import. Import `app.models` explicitly where metadata is needed.
"""

from app.db.base import Base
from app.db.session import build_engine, build_session_factory

__all__ = [
    "Base",
    "build_engine",
    "build_session_factory",
]
