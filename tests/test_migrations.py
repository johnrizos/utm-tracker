import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from utm_tracker.config import get_settings
from utm_tracker.db import Base

ROOT = Path(__file__).resolve().parents[1]


def test_migrations_match_the_models_and_downgrade_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    monkeypatch.setenv("UTM_DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))

    try:
        command.upgrade(config, "head")
        engine = create_engine(url)
        tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert tables == set(Base.metadata.tables)

        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        engine.dispose()
    finally:
        get_settings.cache_clear()
