"""GovWren: an open system of record for AI governance."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("govwren")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

PRODUCT_NAME = "GovWren"
TAGLINE = "AI governance people actually use."
