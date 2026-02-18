import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Generator

import pytest
from nanoid import generate
from pytest import MonkeyPatch

from getgather.config import FRIENDLY_CHARS, settings


@pytest.fixture
def temp_project_dir(monkeypatch: MonkeyPatch) -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

    monkeypatch.setattr("getgather.config.PROJECT_DIR", temp_path)
    yield temp_path
    # Clean up
    if temp_path.exists():
        shutil.rmtree(temp_path)


def _get_test_auth_token() -> str:
    if not settings.FIRST_PARTY_OAUTH_PROVIDER_NAME or not settings.FIRST_PARTY_APPS:
        return "no_auth_setup"
    else:
        app_key = list(settings.FIRST_PARTY_APPS.keys())[0]
        user_id = generate(FRIENDLY_CHARS, 6)
        print(f"Generated test user_id: {user_id} for auth token")
        return f"{settings.FIRST_PARTY_OAUTH_PROVIDER_NAME}_{app_key}_{user_id}"


@pytest.fixture
def mcp_config() -> dict[str, Any]:
    return {
        "mcpServers": {
            "getgather": {
                "url": f"{os.environ.get('HOST', 'http://localhost:23456')}/mcp",
                "headers": {"Authorization": f"Bearer {_get_test_auth_token()}"},
            }
        }
    }
