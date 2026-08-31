import os
import sys
from multiprocessing import Process
from pathlib import Path
from time import sleep

import httpx
import pytest
import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[2]
API_PORT = 8765
TEST_EXPORT_ROOT = REPO_ROOT / "data" / "test-export"


def _run_server() -> None:
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
    os.environ.setdefault("PROMPT_PIPER_EXPORT_ROOT", str(TEST_EXPORT_ROOT))
    os.environ.setdefault("PROMPT_PIPER_HOST_EXPORT_ROOT", str(TEST_EXPORT_ROOT))
    os.environ.setdefault("REGISTRY_PATH", str(TEST_EXPORT_ROOT / "registry"))
    os.environ.setdefault("ARTIFACTS_PATH", str(TEST_EXPORT_ROOT / "exports"))
    os.environ.setdefault("AUDIT_LOG_PATH", str(TEST_EXPORT_ROOT / "audit"))
    uvicorn.run(
        "prompt_piper_api.main:app",
        host="127.0.0.1",
        port=API_PORT,
        log_level="warning",
    )


@pytest.fixture(scope="module")
def live_server():
    process = Process(target=_run_server, daemon=True)
    process.start()
    try:
        for _ in range(30):
            try:
                response = httpx.get(f"http://127.0.0.1:{API_PORT}/health", timeout=1.0)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                sleep(0.2)
        else:
            pytest.fail("API did not become ready in time")
        yield f"http://127.0.0.1:{API_PORT}"
    finally:
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()


def test_api_starts_and_serves_health(live_server: str):
    response = httpx.get(f"{live_server}/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_uvicorn_importable():
    from prompt_piper_api.main import app

    assert app.title == "Nautilius Prompting Workbench API"
