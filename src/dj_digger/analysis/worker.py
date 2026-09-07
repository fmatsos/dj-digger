"""Executable compatibility forwarding entry point for the analysis worker."""

from dj_digger.core.analysis.worker import MAX_ERROR_LENGTH, PROTOCOL_VERSION, execute_request, main

__all__ = ["MAX_ERROR_LENGTH", "PROTOCOL_VERSION", "execute_request", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
