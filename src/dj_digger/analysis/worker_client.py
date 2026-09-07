"""Compatibility forwarding module."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("dj_digger.core.analysis.worker_client")
