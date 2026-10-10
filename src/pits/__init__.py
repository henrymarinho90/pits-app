"""Pits App data platform."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pits-app")
except PackageNotFoundError:
    __version__ = "0.0.0"
