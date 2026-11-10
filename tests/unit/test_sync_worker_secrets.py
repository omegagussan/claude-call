import json
import subprocess
from unittest.mock import Mock

import pytest

from scripts import sync_worker_secrets as script


@pytest.fixture
def local_config(tmp_path, monkeypatch):
    monkeypatch.setattr(script, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        'API_KEYS=test-app-secret\nTELNYX_API_KEY="test-${LITERAL}-provider"\n'
        "UNRELATED=private\nCLOUDFLAIR_DEPLOY_KEY=test-cloud-token\nCLOUDFLAIR_ACCOUNT_ID=test-account\n"
    )
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout="private", stderr="private"))
    monkeypatch.setattr(script.subprocess, "run", run)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    return tmp_path, run


def test_upload_allowlist_stdin_and_no_secret_output(local_config, capsys):
    path, run = local_config
    script.sync_worker_secrets()
    args, kwargs = run.call_args
    assert args[0] == ["npx", "--no-install", "wrangler", "secret", "bulk"]
    assert json.loads(kwargs["input"]) == {
        "API_KEYS": "test-app-secret",
        "TELNYX_API_KEY": "test-${LITERAL}-provider",
    }
    assert kwargs["cwd"] == path
    assert kwargs["env"]["CLOUDFLARE_API_TOKEN"] == "test-cloud-token"
    assert kwargs["env"]["CLOUDFLARE_ACCOUNT_ID"] == "test-account"
    assert kwargs["capture_output"]
    output = capsys.readouterr()
    assert "private" not in output.out + output.err
    assert "test-app-secret" not in output.out + output.err


@pytest.mark.parametrize(
    "contents", [None, "API_KEYS=x\n", "API_KEYS\nTELNYX_API_KEY=x\n", "API_KEYS=' '\nTELNYX_API_KEY=x"]
)
def test_invalid_config_never_uploads(local_config, contents):
    path, run = local_config
    if contents is None:
        (path / ".env").unlink()
    else:
        (path / ".env").write_text(contents)
    assert script.main() == 1
    run.assert_not_called()


@pytest.mark.parametrize("failure", ["exit", "timeout", "missing"])
def test_upload_failure_is_nonzero_and_output_is_private(local_config, failure, capsys):
    _, run = local_config
    if failure == "exit":
        run.return_value = subprocess.CompletedProcess([], 1, stdout="private", stderr="private")
    elif failure == "timeout":
        run.side_effect = subprocess.TimeoutExpired("npx", 120, output="private")
    else:
        run.side_effect = FileNotFoundError("private")
    assert script.main() == 1
    output = capsys.readouterr()
    assert output.err
    assert "private" not in output.out + output.err


def test_process_credentials_take_precedence(local_config, monkeypatch):
    _, run = local_config
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "process-token")
    script.sync_worker_secrets()
    assert run.call_args.kwargs["env"]["CLOUDFLARE_API_TOKEN"] == "process-token"
