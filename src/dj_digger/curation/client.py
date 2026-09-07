"""Compatibility forwarding module for the canonical curation client."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("dj_digger.core.curation.client")
