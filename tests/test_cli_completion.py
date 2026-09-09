import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer import _completion_shared

from dj_digger.cli import completion
from dj_digger.cli.completion import _read_profile, replace_profile_region


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("dj-digger")
    assert executable is not None
    return subprocess.run(
        [executable, *args],
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
        text=True,
    )


def test_completion_suggests_commands_and_options(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("")
    commands = _run_cli(
        env={"_DJ_DIGGER_COMPLETE": "complete_bash", "COMP_WORDS": "dj-digger ", "COMP_CWORD": "1"},
    )
    options = _run_cli(
        env={
            "_DJ_DIGGER_COMPLETE": "complete_bash",
            "COMP_WORDS": f"dj-digger analyze --config {config} --",
            "COMP_CWORD": "4",
        },
    )
    assert commands.returncode == 0
    assert "scan" in commands.stdout
    assert options.returncode == 0
    assert "--workers" in options.stdout


def test_show_completion_emits_dynamic_bash_script() -> None:
    result = _run_cli(
        "--show-completion",
        "bash",
        env={"_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION": "1"},
    )
    assert result.returncode == 0
    assert "COMP_WORDS" in result.stdout
    assert "complete_bash" in result.stdout


def test_install_completion_overwrites_dedicated_bash_file(tmp_path: Path) -> None:
    env = {
        "HOME": str(tmp_path),
        "_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION": "1",
    }
    first = _run_cli("--install-completion", "bash", env=env)
    assert first.returncode == 0
    path = tmp_path / ".bash_completions/dj-digger.sh"
    path.write_text("stale")
    second = _run_cli("--install-completion", "bash", env=env)
    assert second.returncode == 0
    assert path.read_text().count("complete -o") == 1


def test_replace_profile_region_is_idempotent_and_preserves_unrelated_content() -> None:
    profile = (
        "# user setting\n\n# >>> dj-digger completion >>>\nstale\n# <<< dj-digger completion <<<\n"
    )
    result = replace_profile_region(profile, "new script")
    assert result.count("dj-digger completion") == 2
    assert "# user setting" in result
    assert replace_profile_region(result, "new script") == result


def test_replace_profile_region_removes_legacy_unmarked_completion() -> None:
    script = _completion_shared.get_completion_script(
        prog_name="dj-digger", complete_var="_DJ_DIGGER_COMPLETE", shell="powershell"
    )
    profile = f"# user setting\r\n{script.replace(chr(10), chr(13) + chr(10))}\r\n"

    result = replace_profile_region(profile, script)

    assert result.count("Register-ArgumentCompleter -Native -CommandName dj-digger") == 1
    assert result.count("# >>> dj-digger completion >>>") == 1
    assert "# user setting" in result


def test_replace_profile_region_consolidates_regions_and_preserves_orphan_content() -> None:
    profile = (
        "# <<< dj-digger completion <<<\n"
        "# user setting\n"
        "# >>> dj-digger completion >>>\nold\n# <<< dj-digger completion <<<\n"
        "# >>> dj-digger completion >>>\nstale\n# <<< dj-digger completion <<<\n"
    )

    result = replace_profile_region(profile, "new script")

    assert result.count("# >>> dj-digger completion >>>") == 1
    assert result.count("# <<< dj-digger completion <<<") == 1
    assert "# user setting" in result


def test_replace_profile_region_preserves_content_after_orphan_start_marker() -> None:
    profile = (
        "# >>> dj-digger completion >>>\n"
        "# user setting\n"
        "# >>> dj-digger completion >>>\nold\n# <<< dj-digger completion <<<\n"
    )

    result = replace_profile_region(profile, "new script")

    assert "# user setting" in result
    assert result.count("# >>> dj-digger completion >>>") == 1


def test_read_profile_preserves_utf16_encoding(tmp_path: Path) -> None:
    profile = tmp_path / "profile.ps1"
    profile.write_text("# réglage utilisateur\n", encoding="utf-16")

    content, encoding = _read_profile(profile)

    assert content == "# réglage utilisateur\n"
    assert encoding == "utf-16"


def test_importing_the_cli_package_does_not_patch_typer() -> None:
    """Importing the CLI must stay free of global side effects on Typer.

    Runs in a fresh interpreter: asserting on import-time behaviour in-process
    would require tearing ``dj_digger.cli`` out of ``sys.modules`` and leaking
    that into every later test.
    """
    probe = (
        "from typer import _completion_shared as shared;"
        "before = shared.install_powershell;"
        "import dj_digger.cli;"
        "assert shared.install_powershell is before, 'importing dj_digger.cli patched Typer';"
        "import dj_digger.cli.completion as completion;"
        "completion.install_patches();"
        "assert shared.install_powershell is not before, 'install_patches() did not apply'"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, check=False, text=True
    )

    assert result.returncode == 0, result.stderr


def test_install_patches_is_idempotent_and_reversible(monkeypatch: pytest.MonkeyPatch) -> None:
    original = _completion_shared.install_powershell
    monkeypatch.setattr(completion, "_patched", False, raising=False)
    monkeypatch.setattr(_completion_shared, "install_powershell", original)

    completion.install_patches()
    patched = _completion_shared.install_powershell
    completion.install_patches()

    assert patched is not original
    assert _completion_shared.install_powershell is patched


def test_install_patches_tolerates_a_missing_typer_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(completion, "_patched", False, raising=False)
    monkeypatch.delattr(_completion_shared, "install_powershell", raising=False)

    completion.install_patches()

    assert not hasattr(_completion_shared, "install_powershell")


def test_powershell_install_never_relaxes_the_execution_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Installing completion must never mutate the user's PowerShell policy."""
    profile = tmp_path / "profile.ps1"
    commands: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(argv)
        if "Get-ExecutionPolicy" in argv:
            return subprocess.CompletedProcess(argv, 0, b"Restricted\r\n", b"")
        return subprocess.CompletedProcess(argv, 0, str(profile).encode("utf-8"), b"")

    monkeypatch.setattr(completion.subprocess, "run", fake_run)

    installed = completion._install_powershell(
        prog_name="dj-digger", complete_var="_DJ_DIGGER_COMPLETE", shell="pwsh"
    )

    assert installed == profile
    assert "dj-digger completion" in profile.read_text(encoding="utf-8")
    assert not any("Set-ExecutionPolicy" in argument for argv in commands for argument in argv)
    assert "Set-ExecutionPolicy" in capsys.readouterr().err
