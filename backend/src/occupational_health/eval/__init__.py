"""Offline RAGAS and domain-specific evaluation toolkit."""

from occupational_health.eval.dataset import EvalCase, GoldDocument, load_golden

__all__ = ["EvalCase", "GoldDocument", "load_golden"]
