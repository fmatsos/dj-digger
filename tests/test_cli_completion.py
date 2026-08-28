import os
import shutil
import subprocess
from pathlib import Path

from typer import _completion_shared

from dj_digger.completion import _read_profile, replace_profile_region


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
