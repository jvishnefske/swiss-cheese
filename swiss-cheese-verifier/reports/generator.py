"""Report Generator.

Generates comprehensive verification reports in multiple formats.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from orchestrator.core import VerificationReport, TaskStatus


class ReportFormat(Enum):
    """Supported report formats."""
    JSON = "json"
    XML = "xml"
    HTML = "html"


class ReportGenerator:
    """Generates verification reports in multiple formats."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        report: VerificationReport,
        formats: list[ReportFormat] | None = None,
        filename_base: str = "verification-report",
    ) -> dict[ReportFormat, Path]:
        """Generate reports in specified formats.

        Args:
            report: The verification report to generate.
            formats: List of formats to generate. Defaults to all.
            filename_base: Base name for output files.

        Returns:
            Dict mapping format to output file path.
        """
        if formats is None:
            formats = list(ReportFormat)

        outputs: dict[ReportFormat, Path] = {}

        for fmt in formats:
            if fmt == ReportFormat.JSON:
                path = self.output_dir / f"{filename_base}.json"
                path.write_text(self._to_json(report))
                outputs[fmt] = path

            elif fmt == ReportFormat.XML:
                path = self.output_dir / f"{filename_base}.xml"
                path.write_text(self._to_xml(report))
                outputs[fmt] = path

            elif fmt == ReportFormat.HTML:
                path = self.output_dir / f"{filename_base}.html"
                path.write_text(self._to_html(report))
                outputs[fmt] = path

        return outputs

    def _to_json(self, report: VerificationReport) -> str:
        """Generate JSON report."""
        return report.to_json()

    def _to_xml(self, report: VerificationReport) -> str:
        """Generate JUnit-compatible XML report."""
        root = ET.Element("testsuites", {
            "name": report.project_name,
            "tests": str(report.total_tasks),
            "failures": str(report.failed_tasks),
            "time": str(
                (report.completed_at - report.started_at).total_seconds()
                if report.completed_at else 0
            ),
        })

        for layer_name, layer_result in report.layer_results.items():
            testsuite = ET.SubElement(root, "testsuite", {
                "name": layer_name,
                "tests": str(len(layer_result.task_results)),
                "failures": str(sum(
                    1 for t in layer_result.task_results
                    if t.status == TaskStatus.FAILED
                )),
            })

            for task_result in layer_result.task_results:
                testcase = ET.SubElement(testsuite, "testcase", {
                    "name": task_result.task_name,
                    "time": str(task_result.duration_ms / 1000),
                    "classname": layer_name,
                })

                if task_result.status == TaskStatus.FAILED:
                    failure = ET.SubElement(testcase, "failure", {
                        "message": task_result.error or "Task failed",
                        "type": "AssertionError",
                    })
                    failure.text = task_result.output

                elif task_result.status == TaskStatus.SKIPPED:
                    ET.SubElement(testcase, "skipped")

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def _to_html(self, report: VerificationReport) -> str:
        """Generate HTML report."""
        status_colors = {
            TaskStatus.PASSED: "#28a745",
            TaskStatus.FAILED: "#dc3545",
            TaskStatus.SKIPPED: "#6c757d",
            TaskStatus.PENDING: "#ffc107",
            TaskStatus.RUNNING: "#17a2b8",
        }

        overall_color = status_colors.get(report.overall_status, "#6c757d")

        # Build layer sections
        layers_html = ""
        for layer_name, layer_result in report.layer_results.items():
            layer_color = status_colors.get(layer_result.status, "#6c757d")

            tasks_html = ""
            for task in layer_result.task_results:
                task_color = status_colors.get(task.status, "#6c757d")
                status_icon = "✓" if task.status == TaskStatus.PASSED else "✗"

                tasks_html += f"""
                <tr>
                    <td>{task.task_name}</td>
                    <td><span style="color: {task_color};">{status_icon} {task.status.value}</span></td>
                    <td>{task.duration_ms}ms</td>
                    <td>{task.error or '-'}</td>
                </tr>
                """

            layers_html += f"""
            <div class="layer">
                <h3>
                    <span class="status-badge" style="background: {layer_color};">
                        {layer_result.status.value.upper()}
                    </span>
                    {layer_name}
                </h3>
                <table>
                    <thead>
                        <tr>
                            <th>Task</th>
                            <th>Status</th>
                            <th>Duration</th>
                            <th>Error</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tasks_html}
                    </tbody>
                </table>
            </div>
            """

        duration = (
            (report.completed_at - report.started_at).total_seconds()
            if report.completed_at else 0
        )

        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification Report: {report.project_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        h1 {{ margin-top: 0; color: #333; }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .summary-card {{
            padding: 20px;
            border-radius: 8px;
            background: #f8f9fa;
            text-align: center;
        }}
        .summary-card h2 {{
            margin: 0;
            font-size: 2em;
        }}
        .summary-card p {{
            margin: 5px 0 0;
            color: #666;
        }}
        .status-badge {{
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: bold;
            display: inline-block;
            margin-right: 10px;
        }}
        .layer {{
            margin: 20px 0;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .progress-bar {{
            height: 20px;
            background: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
            margin: 10px 0;
        }}
        .progress-fill {{
            height: 100%;
            background: #28a745;
            transition: width 0.3s;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>
            <span class="status-badge" style="background: {overall_color};">
                {report.overall_status.value.upper()}
            </span>
            {report.project_name}
        </h1>

        <div class="summary">
            <div class="summary-card">
                <h2>{report.passed_tasks}/{report.total_tasks}</h2>
                <p>Tasks Passed</p>
            </div>
            <div class="summary-card">
                <h2>{len(report.layer_results)}</h2>
                <p>Layers</p>
            </div>
            <div class="summary-card">
                <h2>{duration:.1f}s</h2>
                <p>Duration</p>
            </div>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" style="width: {100*report.passed_tasks/max(report.total_tasks,1):.1f}%;"></div>
        </div>

        <p><strong>Started:</strong> {report.started_at.isoformat()}</p>
        <p><strong>Completed:</strong> {report.completed_at.isoformat() if report.completed_at else 'In progress'}</p>

        <h2>Verification Layers</h2>
        {layers_html}
    </div>
</body>
</html>
        """
