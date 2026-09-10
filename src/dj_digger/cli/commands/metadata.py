"""Metadata command adapter."""

from dj_digger.cli.presenters.metadata import metadata_payload
from dj_digger.core.application import CoreApplication, MetadataRequest
from dj_digger.core.diagnostics import Diagnostic


def execute(service: CoreApplication, request: MetadataRequest) -> Diagnostic:
    """Execute one typed metadata request through the core boundary."""
    return metadata_payload(service.metadata(request))


__all__ = ["execute"]
