"""Access resources shipped inside the installed package."""

import sys
from importlib.resources import files


def read_text(relative_path: str) -> str:
    """Read a required UTF-8 resource from the installed package."""
    resource_files = files
    legacy = sys.modules.get("dj_digger.resources")
    if legacy is not None:
        resource_files = getattr(legacy, "files", files)
    resource = resource_files("dj_digger").joinpath(*relative_path.split("/"))
    if not resource.is_file():
        raise FileNotFoundError(f"required packaged resource missing: dj_digger/{relative_path}")
    return resource.read_text(encoding="utf-8")
