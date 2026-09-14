import json
from unittest.mock import patch

from prompt_piper.setup.gpu_detect import GpuInfo, detect_gpus, select_gpu
from prompt_piper.setup.hardware import recommendations
from prompt_piper.setup.wizard import run_setup_wizard


def report(free=32000, ram=48000):
    gpu = GpuInfo("nvidia", "5090", 32607, free, "GPU-large")
    return recommendations([gpu], gpu, ram)


def test_multi_gpu_does_not_choose_first_or_pool_memory(monkeypatch):
    monkeypatch.setattr(
        "prompt_piper.setup.gpu_detect.shutil.which",
        lambda name: name if name == "nvidia-smi" else None,
    )
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    with patch(
        "prompt_piper.setup.gpu_detect._run",
        return_value="2070,8192,7800,GPU-small\n5090,32607,32000,GPU-large\n",
    ):
        devices = detect_gpus()
    assert len(devices) == 2
    assert select_gpu(devices).device_id == "GPU-large"
    assert recommendations(devices, select_gpu(devices), 48000)["recommended"] == "high"
    two_small = [GpuInfo("nvidia", "8GB", 8192, 7800)] * 2
    assert recommendations(two_small, two_small[0], 48000)["recommended"] == "mid"


def test_malformed_memory_and_visibility(monkeypatch):
    monkeypatch.setattr(
        "prompt_piper.setup.gpu_detect.shutil.which",
        lambda name: name if name == "nvidia-smi" else None,
    )
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-second")
    with patch(
        "prompt_piper.setup.gpu_detect._run",
        return_value="one,32000,31000,GPU-first\ntwo,N/A,N/A,GPU-second\n",
    ):
        devices = detect_gpus()
    assert len(devices) == 1
    assert devices[0].free_vram_mb is None
    assert recommendations(devices, devices[0], 48000)["recommended"] == "low"


def test_amd_memory_json(monkeypatch):
    monkeypatch.setattr(
        "prompt_piper.setup.gpu_detect.shutil.which",
        lambda name: name if name == "rocm-smi" else None,
    )
    output = json.dumps(
        {
            "card0": {
                "Card Series": "AMD test",
                "VRAM Total Memory (B)": str(32 * 1024**3),
                "VRAM Total Used Memory (B)": str(2 * 1024**3),
            }
        }
    )
    with patch("prompt_piper.setup.gpu_detect._run", return_value=output):
        gpu = select_gpu(detect_gpus())
    assert gpu.vendor == "amd"
    assert gpu.free_vram_mb == 30720


def test_low_mid_high_options_and_unknown_resources():
    assert [o["id"] for o in report()["local_options"]] == ["low", "mid", "high"]
    assert report()["local_options"][2]["preset"] == "deepseek-r1-32b"
    assert report(9000)["local_options"][1]["preset"] == "qwen3-8b"
    assert report(18000)["local_options"][1]["preset"] == "qwen3-14b"
    assert report(18000)["recommended"] == "mid"
    assert report(1000)["local_options"][0]["status"] == "cpu"
    assert recommendations([], None, None)["recommended"] == "remote"
    assert len(recommendations([], None, None)["local_options"]) == 3


def test_interactive_high_and_remote_and_cpu(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPT_PIPER_REPO_ROOT", str(tmp_path))
    for choices, expected in [
        (["3", "1", "1", ""], "deepseek-r1-32b"),
        (["4", "https://example.test/v1", "hosted-model", ""], "custom"),
        (["0"], None),
    ]:
        inputs = iter(choices)
        with patch("prompt_piper.setup.hardware.scan_hardware", return_value=report()):
            result = run_setup_wizard(
                env_path=tmp_path / ".env",
                input_fn=lambda _: next(inputs),
                print_fn=lambda _: None,
            )
        assert result.preset_id == expected
        if expected == "custom":
            assert (
                "PROMPT_PIPER_AUTO_START_LLM=false" in (tmp_path / ".env").read_text()
            )


def test_rebuild_scan_only_is_read_only(monkeypatch):
    from prompt_piper.setup.rebuild import main

    monkeypatch.setattr("prompt_piper.setup.rebuild.scan_hardware", report)
    with (
        patch("prompt_piper.setup.rebuild.run_setup_wizard") as configure,
        patch("prompt_piper.setup.rebuild.subprocess.run") as build,
    ):
        assert main(["--scan-only"]) == 0
        configure.assert_not_called()
        build.assert_not_called()


def test_rebuild_preserves_data_and_backs_up_config(tmp_path, monkeypatch):
    from prompt_piper.setup.embedding_device import EmbeddingDeviceDecision
    from prompt_piper.setup.rebuild import main

    monkeypatch.setattr("prompt_piper.setup.rebuild.repo_root", lambda: tmp_path)
    monkeypatch.setattr("prompt_piper.setup.rebuild.scan_hardware", report)
    monkeypatch.setattr(
        "prompt_piper.setup.embedding_device.resolve_embedding_device",
        lambda: EmbeddingDeviceDecision("cpu", "test"),
    )
    (tmp_path / ".env").write_text(
        "CUDA_VISIBLE_DEVICES=old\nPROMPT_PIPER_LLAMA_GPU_LAYERS=12\nCUSTOM_VALUE=keep\n"
    )
    (tmp_path / "saved-session.json").write_text("keep")
    assert main(["--skip-build", "--non-interactive", "cpu-only"]) == 0
    assert (tmp_path / "saved-session.json").read_text() == "keep"
    assert "CUSTOM_VALUE=keep" in (tmp_path / ".env").read_text()
    assert "CUDA_VISIBLE_DEVICES=" not in (tmp_path / ".env").read_text()
    backup = next(tmp_path.glob(".env.hardware-*.bak"))
    assert "CUDA_VISIBLE_DEVICES=old" in backup.read_text()
    assert backup.stat().st_mode & 0o777 == 0o600


def test_hardware_api_reports_three_local_options_and_remote(client):
    with patch("prompt_piper.setup.hardware.scan_hardware", return_value=report()):
        result = client.get("/health/hardware")
    assert result.status_code == 200
    assert len(result.json()["local_options"]) == 3
    assert result.json()["remote_option"]["id"] == "remote"
