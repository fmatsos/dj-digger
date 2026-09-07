"""Compatibility imports for packaged-resource access."""

from importlib.resources import files

from dj_digger.core.resources import read_text

__all__ = ["files", "read_text"]
