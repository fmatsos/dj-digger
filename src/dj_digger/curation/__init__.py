"""Compatibility forwarding package for :mod:`dj_digger.core.curation`."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("dj_digger.core.curation")
