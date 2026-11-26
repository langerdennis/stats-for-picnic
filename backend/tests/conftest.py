from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import create_all_tables, init_db_engine
from app.main import create_app


@pytest.fixture()
def temp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("MEALIE_URL", "")
    monkeypatch.setenv("MEALIE_API_TOKEN", "")
    get_settings.cache_clear()
    init_db_engine(get_settings())
    create_all_tables()
    yield data_dir
    get_settings.cache_clear()


@pytest.fixture()
def client(temp_data_dir: Path) -> Generator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
