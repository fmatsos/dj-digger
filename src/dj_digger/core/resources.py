"""Access resources shipped inside the installed package."""

from importlib.resources import files


def read_text(relative_path: str) -> str:
    """Read a required UTF-8 resource from the installed package."""
    # ``schemas/`` was the pre-core location. Keep that resource spelling
    # readable for external callers while making ``core/schemas/`` canonical.
    canonical_path = (
        f"core/{relative_path}" if relative_path.startswith("schemas/") else relative_path
    )
    resource = files("dj_digger").joinpath(*canonical_path.split("/"))
    if not resource.is_file():
        raise FileNotFoundError(f"required packaged resource missing: dj_digger/{relative_path}")
    return resource.read_text(encoding="utf-8")
