import pytest
from prompt_piper.setup.download_model import download_configured_model
from prompt_piper.setup.model_sources import (
    load_preferences,
    local_gguf,
    public_preferences,
    save_preferences,
)


@pytest.fixture
def source_root(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPT_PIPER_REPO_ROOT", str(tmp_path))
    return tmp_path


def test_token_is_write_only_and_owner_readable(source_root):
    saved = save_preferences(hf_token="hf_test-secret", local_repo=str(source_root))
    assert saved == {"hf_token_configured": True, "local_repo": str(source_root)}
    assert "hf_test-secret" not in str(public_preferences())
    assert (source_root / "data/model-source.json").stat().st_mode & 0o777 == 0o600
    save_preferences(hf_token="")
    assert load_preferences()["hf_token"] == "hf_test-secret"
    save_preferences(clear_token=True)
    assert not public_preferences()["hf_token_configured"]


def test_local_repo_discovery_rejects_lfs_pointer(source_root):
    (source_root / "model.gguf").write_bytes(
        b"version https://git-lfs.github.com/spec/v1"
    )
    with pytest.raises(ValueError, match="Git LFS"):
        local_gguf(str(source_root), "model.gguf")
    (source_root / "model.gguf").write_bytes(b"GGUFtest")
    assert local_gguf(str(source_root), "model.gguf") == source_root / "model.gguf"


def test_local_import_does_not_call_huggingface(source_root):
    source = source_root / "repo/model.gguf"
    source.parent.mkdir()
    source.write_bytes(b"GGUFtest")
    target = source_root / "models/model.gguf"
    env = source_root / ".env"
    env.write_text(
        f"PROMPT_PIPER_LOCAL_MODEL_SOURCE=local\nPROMPT_PIPER_LOCAL_MODEL_SOURCE_PATH={source}\nPROMPT_PIPER_LOCAL_MODEL_PATH={target}\n"
    )
    result = download_configured_model(env_path=env)
    assert result.status == "downloaded"
    assert target.read_bytes() == source.read_bytes() == b"GGUFtest"
    assert download_configured_model(env_path=env).status == "exists"


def test_token_sent_to_download_and_redacted_from_errors(source_root, monkeypatch):
    import sys
    from types import SimpleNamespace

    save_preferences(hf_token="hf_test-secret")
    env = source_root / ".env"
    env.write_text(
        "PROMPT_PIPER_LOCAL_MODEL_GGUF_REPO=Qwen/test\nPROMPT_PIPER_LOCAL_MODEL_GGUF_FILE=model.gguf\n"
    )

    def download(**kwargs):
        assert kwargs["token"] == "hf_test-secret"
        raise RuntimeError("Failed token hf_test-secret")

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download)
    )
    result = download_configured_model(env_path=env, models_dir=source_root / "models")
    assert result.status == "error"
    assert "hf_test-secret" not in result.message


def test_model_source_api_never_returns_token(source_root, client):
    response = client.put(
        "/settings/model-source",
        json={"hf_token": "hf_private", "local_repo": str(source_root)},
    )
    assert response.status_code == 200
    assert response.json()["hf_token_configured"]
    assert "hf_private" not in response.text
    assert "hf_private" not in client.get("/settings/model-source").text


def test_local_paths_with_spaces_and_shell_characters_are_literal(source_root):
    from prompt_piper.setup.download_model import _load_env
    from prompt_piper.setup.env_writer import upsert_env_section

    value = str(source_root / "models $(literal) with spaces" / "model.gguf")
    env = source_root / ".env"
    upsert_env_section(env, {"PROMPT_PIPER_LOCAL_MODEL_PATH": value})
    assert _load_env(env)["PROMPT_PIPER_LOCAL_MODEL_PATH"] == value
