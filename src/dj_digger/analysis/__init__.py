"""Compatibility aliases for the canonical core analysis package."""

import sys

from dj_digger.core.analysis import aggregation as aggregation
from dj_digger.core.analysis import audio as audio
from dj_digger.core.analysis import config as config
from dj_digger.core.analysis import ebur128 as ebur128
from dj_digger.core.analysis import eligibility as eligibility
from dj_digger.core.analysis import exporters as exporters
from dj_digger.core.analysis import extractor as extractor
from dj_digger.core.analysis import ffmpeg as ffmpeg
from dj_digger.core.analysis import persistence as persistence
from dj_digger.core.analysis import pipeline as pipeline
from dj_digger.core.analysis import rhythm as rhythm
from dj_digger.core.analysis import segmentation as segmentation
from dj_digger.core.analysis import semantics as semantics
from dj_digger.core.analysis import spectrum as spectrum
from dj_digger.core.analysis import windows as windows
from dj_digger.core.analysis import worker_client as worker_client

sys.modules[__name__ + ".aggregation"] = aggregation
sys.modules[__name__ + ".audio"] = audio
sys.modules[__name__ + ".config"] = config
sys.modules[__name__ + ".ebur128"] = ebur128
sys.modules[__name__ + ".eligibility"] = eligibility
sys.modules[__name__ + ".exporters"] = exporters
sys.modules[__name__ + ".extractor"] = extractor
sys.modules[__name__ + ".ffmpeg"] = ffmpeg
sys.modules[__name__ + ".persistence"] = persistence
sys.modules[__name__ + ".pipeline"] = pipeline
sys.modules[__name__ + ".rhythm"] = rhythm
sys.modules[__name__ + ".segmentation"] = segmentation
sys.modules[__name__ + ".semantics"] = semantics
sys.modules[__name__ + ".spectrum"] = spectrum
sys.modules[__name__ + ".windows"] = windows
sys.modules[__name__ + ".worker_client"] = worker_client

__all__ = [
    "aggregation",
    "audio",
    "config",
    "ebur128",
    "eligibility",
    "exporters",
    "extractor",
    "ffmpeg",
    "persistence",
    "pipeline",
    "rhythm",
    "segmentation",
    "semantics",
    "spectrum",
    "windows",
    "worker_client",
]
