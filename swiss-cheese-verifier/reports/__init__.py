"""Report Generation Module.

Generates verification reports in JSON, XML, and HTML formats.
"""

from .generator import ReportGenerator, ReportFormat

__all__ = ["ReportGenerator", "ReportFormat"]
