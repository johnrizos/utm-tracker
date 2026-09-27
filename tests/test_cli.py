import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from utm_tracker import cli
from utm_tracker.models import ApiKey
from utm_tracker.security import hash_key


def test_key_lifecycle(
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: factory)

    assert cli.main(["create-key", "Marketing"]) == 0
    key = capsys.readouterr().out.strip().splitlines()[-1]
    assert key.startswith("utm_")

    with factory() as session:
        row = session.scalars(select(ApiKey)).one()
        # Only the hash is stored.
        assert row.key_hash == hash_key(key)
        assert key not in (row.key_hash, row.prefix)

    assert cli.main(["list-keys"]) == 0
    assert "Marketing  (active)" in capsys.readouterr().out

    assert cli.main(["revoke-key", key[:12]]) == 0
    assert cli.main(["revoke-key", "utm_missing"]) == 1
    with factory() as session:
        assert session.scalars(select(ApiKey)).one().revoked_at is not None
