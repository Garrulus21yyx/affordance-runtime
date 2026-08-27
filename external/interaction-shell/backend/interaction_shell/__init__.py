"""Standalone external interaction shell; no Runtime internals are imported."""

from .api import create_app

__all__ = ("create_app",)
