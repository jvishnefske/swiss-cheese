"""Verification Gates.

Command-line verification gates with return codes and report generation.
Each gate returns 0 for pass, non-zero for failure.
"""

from .base import Gate, GateResult, GateRunner
from .static_analysis import StaticAnalysisGate
from .tdd import TDDGate
from .review import ReviewGate

__all__ = [
    "Gate",
    "GateResult",
    "GateRunner",
    "StaticAnalysisGate",
    "TDDGate",
    "ReviewGate",
]
