"""Compatibility forwarding module for canonical curation prompts."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("dj_digger.core.curation.prompts")
