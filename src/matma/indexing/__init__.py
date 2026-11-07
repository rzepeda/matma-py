"""Index-time dependency graph and deterministic manifest generation."""

from .engine import index_project
from .graph import build_graph

__all__ = ["index_project", "build_graph"]
