"""Opto — local, reversible context-compression proxy for GitHub Copilot.

Fewer tokens, same answers, with a quality guarantee.
"""

from opto._version import __version__
from opto.pipeline import Pipeline, compress
from opto.config import Config, get_config

__all__ = ["__version__", "Pipeline", "compress", "Config", "get_config"]
