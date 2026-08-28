"""Small compatibility fix for Typer's PowerShell completion installer."""

import codecs
import subprocess
from pathlib import Path

from typer import _completion_shared

_START = "# >>> dj-digger completion >>>"
_END = "# <<< dj-digger completion <<<"
_original_install_powershell = _completion_shared.install_powershell


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


def _install_powershell(*, prog_name: str, complete_var: str, shell: str) -> Path:
    if prog_name != "dj-digger":
        return _original_install_powershell(
            prog_name=prog_name, complete_var=complete_var, shell=shell
        )
    subprocess.run(
        [shell, "-Command", "Set-ExecutionPolicy", "Unrestricted", "-Scope", "CurrentUser"]
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", "echo", "$profile"],
        check=True,
        stdout=subprocess.PIPE,
    )
    path_obj = Path(_decode_path(result.stdout).strip())
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    script = _completion_shared.get_completion_script(
        prog_name=prog_name, complete_var=complete_var, shell=shell
    )
    profile, encoding = _read_profile(path_obj)
    path_obj.write_text(replace_profile_region(profile, script), encoding=encoding)
    return path_obj


def install_patches() -> None:
    """Apply installer fixes once, after Typer has been imported."""
    _completion_shared.install_powershell = _install_powershell
