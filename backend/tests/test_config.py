"""Settings and path resolution.

These tests guard the one thing that silently breaks everything if it drifts:
where the essay corpus lives.
"""

from pathlib import Path

import pydantic
import pytest

from config import BACKEND_DIR, REPO_ROOT, Settings, get_settings


def test_data_dir_points_at_the_real_corpus() -> None:
    data_dir = get_settings().data_dir
    assert data_dir == REPO_ROOT / "data"
    assert data_dir.is_dir(), f"corpus missing at {data_dir}"
    assert len(list((data_dir / "essays").glob("*.json"))) > 200


def test_repo_root_is_the_parent_of_backend() -> None:
    assert BACKEND_DIR.name == "backend"
    assert BACKEND_DIR.parent == REPO_ROOT


def test_index_json_exists() -> None:
    """The catalog the ingest step will read must be present."""
    assert (REPO_ROOT / "data" / "index.json").is_file()


def test_cors_origins_parsed_and_trimmed() -> None:
    s = Settings(cors_origins="https://a.dev, https://b.dev ,")
    assert s.cors_origin_list == ["https://a.dev", "https://b.dev"]


def test_empty_cors_origins_means_same_origin_only() -> None:
    assert Settings(cors_origins="").cors_origin_list == []


def test_unknown_env_keys_are_ignored_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Frontend-only vars in the shared .env must not break backend startup."""
    monkeypatch.setenv("OPENROUTER_MODEL", "some/model")
    s = Settings()
    assert s.app_name == "askgraham-api"


def test_environment_literal_rejects_typos() -> None:
    with pytest.raises(pydantic.ValidationError):
        Settings(environment="production")  # type: ignore[arg-type]


def test_database_url_defaults_to_local_compose_service() -> None:
    """Kept in sync with docker-compose.yml by hand — assert that contract."""
    default = Settings().database_url
    assert default.startswith("postgresql+asyncpg://")
    assert ":5432/" in default or ":5433/" in default


def test_settings_are_cached_singleton() -> None:
    assert get_settings() is get_settings()


def test_paths_are_absolute() -> None:
    assert Path(REPO_ROOT).is_absolute()
    assert Path(BACKEND_DIR).is_absolute()
