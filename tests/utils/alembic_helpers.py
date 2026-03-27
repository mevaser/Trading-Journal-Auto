from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory


def get_head_revision() -> str:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()
