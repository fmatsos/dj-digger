"""CLI adapters for operational core use cases."""

from typing import Any

from dj_digger.cli.presenters.operations import operation_payload


def execute_status(service: Any) -> dict[str, Any]:
    return operation_payload(service.status())


def execute_doctor(service: Any) -> dict[str, Any]:
    return operation_payload(service.doctor())


def execute_optimize(service: Any) -> dict[str, Any]:
    return operation_payload(service.optimize_database())


def execute_quick_check(service: Any) -> dict[str, Any]:
    return operation_payload(service.quick_check_database())


def execute_integrity_check(service: Any) -> dict[str, Any]:
    return operation_payload(service.integrity_check_database())


def execute_rebuild(service: Any) -> dict[str, Any]:
    return operation_payload(service.rebuild_current_analysis())


__all__ = [
    "execute_doctor",
    "execute_integrity_check",
    "execute_optimize",
    "execute_quick_check",
    "execute_rebuild",
    "execute_status",
]
