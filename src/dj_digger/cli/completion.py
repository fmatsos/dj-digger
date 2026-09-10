"""Compatibility fixes for Typer's PowerShell completion installer.

Typer's own installer rewrites the entire PowerShell profile and relaxes the
user's execution policy as a side effect. This module replaces it with a
marked-region rewrite that preserves unrelated profile content and reports —
never silently changes — a policy that would keep the profile from loading.
"""

import codecs
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from typer import _completion_shared

_START = "# >>> dj-digger completion >>>"
_END = "# <<< dj-digger completion <<<"
_PROGRAM = "dj-digger"
_SHELL_TIMEOUT_SECONDS = 30.0
_BLOCKING_EXECUTION_POLICIES = frozenset({"restricted", "allsigned"})
_EXECUTION_POLICY_NOTICE = (
    "PowerShell execution policy is {policy}, so the profile that enables "
    "dj-digger completion will not load. dj-digger does not change security "
    "settings for you; run this yourself if you want completion active:\n"
    "  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser"
)

_patched = False
_typer_install_powershell: Callable[..., Path] | None = None


def _without_marked_regions(profile: str) -> str:
    lines = profile.splitlines(keepends=True)
    starts: list[int] = []
    removed: set[int] = set()
    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        if content == _START:
            starts.append(index)
        elif content == _END and starts:
            start = starts.pop()
            removed.update(range(start, index + 1))
    return "".join(
        line
        for index, line in enumerate(lines)
        if index not in removed and line.rstrip("\r\n") not in {_START, _END}
    )


def _without_legacy_script(profile: str, script: str) -> str:
    lines = profile.splitlines(keepends=True)
    contents = [line.rstrip("\r\n") for line in lines]
    script_lines = script.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if contents[index : index + len(script_lines)] == script_lines:
            index += len(script_lines)
        else:
            kept.append(lines[index])
            index += 1
    return "".join(kept)


def replace_profile_region(profile: str, script: str) -> str:
    """Replace only DJ Digger's marked profile block, preserving other content."""
    block = f"{_START}\n{script}\n{_END}"
    profile = _without_marked_regions(profile)
    profile = _without_legacy_script(profile, script)
    separator = "" if not profile or profile.endswith(("\n", "\r")) else "\n"
    return f"{profile}{separator}{block}\n"


def _decode_path(raw_path: bytes) -> str:
    """Keep Typer's Windows-compatible profile-path decoding behavior."""
    for encoding in ("windows-1252", "utf8", "cp850"):
        try:
            return raw_path.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError("could not decode the PowerShell profile path")


def _read_profile(path: Path) -> tuple[str, str]:
    if not path.is_file():
        return "", "utf-8"
    raw_profile = path.read_bytes()
    if raw_profile.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw_profile.decode("utf-16"), "utf-16"
    for encoding in ("utf-8-sig", "utf-8", "windows-1252", "cp850"):
        try:
            return raw_profile.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeError("could not decode the PowerShell profile")


def _report_blocking_execution_policy(shell: str) -> None:
    """Warn when the effective policy would keep the profile from loading.

    Reporting instead of calling ``Set-ExecutionPolicy`` keeps a completion
    install from silently weakening the machine's script-execution posture.
    """
    try:
        result = subprocess.run(
            [shell, "-NoProfile", "-Command", "Get-ExecutionPolicy"],
            capture_output=True,
            check=False,
            timeout=_SHELL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode != 0:
        return
    policy = result.stdout.decode("utf-8", errors="replace").strip()
    if policy.lower() in _BLOCKING_EXECUTION_POLICIES:
        print(_EXECUTION_POLICY_NOTICE.format(policy=policy), file=sys.stderr)


def _install_powershell(*, prog_name: str, complete_var: str, shell: str) -> Path:
    if prog_name != _PROGRAM:
        return _original_install_powershell(
            prog_name=prog_name, complete_var=complete_var, shell=shell
        )
    _report_blocking_execution_policy(shell)
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", "echo", "$profile"],
        check=True,
        stdout=subprocess.PIPE,
        timeout=_SHELL_TIMEOUT_SECONDS,
    )
    path_obj = Path(_decode_path(result.stdout).strip())
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    script = _completion_shared.get_completion_script(
        prog_name=prog_name, complete_var=complete_var, shell=shell
    )
    profile, encoding = _read_profile(path_obj)
    path_obj.write_text(replace_profile_region(profile, script), encoding=encoding)
    return path_obj


def _original_install_powershell(*, prog_name: str, complete_var: str, shell: str) -> Path:
    """Delegate to the Typer installer captured before applying our patch."""
    if _typer_install_powershell is None:
        raise RuntimeError("Typer no longer exposes a PowerShell completion installer")
    installed: Path = _typer_install_powershell(
        prog_name=prog_name, complete_var=complete_var, shell=shell
    )
    return installed


def install_patches() -> None:
    """Apply the installer fix once, tolerating changes to Typer internals.

    Called from the CLI entry point rather than at import time: importing
    ``dj_digger.cli`` must not mutate a third-party module for the whole process.
    """
    global _patched, _typer_install_powershell
    if _patched:
        return
    _patched = True
    installer = getattr(_completion_shared, "install_powershell", None)
    if installer is None:
        return
    _typer_install_powershell = installer
    _completion_shared.install_powershell = _install_powershell


__all__ = ["install_patches", "replace_profile_region"]
