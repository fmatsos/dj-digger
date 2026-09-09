"""Metadata command adapter."""

from typing import Any

from dj_digger.cli.presenters.metadata import metadata_payload
from dj_digger.core.application import CoreApplication, MetadataRequest


def execute(service: CoreApplication, request: MetadataRequest) -> dict[str, Any]:
    """Execute one typed metadata request through the core boundary."""
    return metadata_payload(service.metadata(request))


__all__ = ["execute"]
