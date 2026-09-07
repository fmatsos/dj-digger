"""Compatibility re-exports for canonical schema-driven writers."""

from dj_digger.core.exports.formats import (
    FORMATS,
    fields_for_schema,
    output_path,
    projected,
    select_fields,
    write_object,
    write_rows,
)

__all__ = [
    "FORMATS",
    "fields_for_schema",
    "output_path",
    "projected",
    "select_fields",
    "write_object",
    "write_rows",
]
