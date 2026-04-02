import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

class Reporting:
    """
    Generates markdown reports and visualizations for the SQE.
    """
    def __init__(self):
        pass

    def generate_markdown_report(self, report: Dict[str, Any], output_path: str):
        """Generates a markdown report summarizing the evaluation."""
        metrics = report.get("metrics", {})
        
        md = [
            f"# System Quality Evaluation Report: {report.get('project_name')}",
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            f"- **Overall Quality Score**: {report.get('overall_score')}/100",
            f"- **Usefulness/Value Score**: {report.get('value_score')}/100",
            f"- **PRD Coverage**: {metrics.get('coverage_score')}%",
            f"- **Code Quality Score**: {metrics.get('average_quality_score')}/100",
            f"- **Functional Correctness**: {metrics.get('correctness_score')}%",
            "",
            "## Metrics",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| Total Requirements | {metrics.get('total_requirements')} |",
            f"| Implemented Requirements | {metrics.get('implemented_requirements')} |",
            f"| Total Tests | {metrics.get('total_tests')} |",
            f"| Passed Tests | {metrics.get('passed_tests')} |",
            "",
            "## Detailed Evaluations",
            "| Requirement ID | Status | Quality | Analysis | Gaps |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        
        for eval_res in report.get("detailed_evaluations", []):
            gaps = ", ".join(eval_res.get("gaps", [])) if isinstance(eval_res.get("gaps"), list) else eval_res.get("gaps", "None")
            md.append(f"| {eval_res.get('requirement_id')} | {eval_res.get('status')} | {eval_res.get('quality_score')} | {eval_res.get('analysis')} | {gaps} |")
            
        md.append("\n## Test Results")
        md.append("| Requirement ID | Passed | Test File | Output/Error |")
        md.append("| :--- | :--- | :--- | :--- |")
        
        for test_res in report.get("test_results", []):
            passed_icon = "✅" if test_res.get("passed") else "❌"
            output = test_res.get("stdout", "") or test_res.get("error", "")
            # Clean up output for table
            output = output.replace("\n", " ").replace("|", "\\|")[:100] + "..." if len(output) > 100 else output
            md.append(f"| {test_res.get('requirement_id')} | {passed_icon} | {test_res.get('test_file')} | {output} |")
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

    def update_trend_data(self, report: Dict[str, Any], history_path: str):
        """Appends the current report metrics to the history file."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "project_name": report.get("project_name"),
            "overall_score": report.get("overall_score"),
            "value_score": report.get("value_score"),
            "coverage_score": report.get("metrics", {}).get("coverage_score"),
            "quality_score": report.get("metrics", {}).get("average_quality_score"),
            "correctness_score": report.get("metrics", {}).get("correctness_score")
        }
        
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def generate_trend_visualization(self, history_path: str, output_path: str):
        """Generates an interactive HTML visualization of quality trends."""
        if not PLOTLY_AVAILABLE:
            print("⚠️ Plotly not available. Skipping trend visualization.")
            return

        if not os.path.exists(history_path):
            print("⚠️ No history data found for trend visualization.")
            return

        history = []
        with open(history_path, "r", encoding="utf-8") as f:
            for line in f:
                history.append(json.loads(line))

        if not history:
            return

        timestamps = [h["timestamp"] for h in history]
        overall_scores = [h["overall_score"] for h in history]
        value_scores = [h["value_score"] for h in history]
        coverage_scores = [h["coverage_score"] for h in history]
        quality_scores = [h["quality_score"] for h in history]
        correctness_scores = [h["correctness_score"] for h in history]

        fig = make_subplots(specs=[[{"secondary_y": False}]])
        
        fig.add_trace(go.Scatter(x=timestamps, y=overall_scores, mode='lines+markers', name='Overall Score'))
        fig.add_trace(go.Scatter(x=timestamps, y=value_scores, mode='lines+markers', name='Value Score'))
        fig.add_trace(go.Scatter(x=timestamps, y=coverage_scores, mode='lines+markers', name='Coverage Score'))
        fig.add_trace(go.Scatter(x=timestamps, y=quality_scores, mode='lines+markers', name='Quality Score'))
        fig.add_trace(go.Scatter(x=timestamps, y=correctness_scores, mode='lines+markers', name='Correctness Score'))

        fig.update_layout(
            title="System Quality Trends",
            xaxis_title="Timestamp",
            yaxis_title="Score (0-100)",
            template="plotly_white"
        )
        
        fig.write_html(output_path)
        print(f"Trend visualization generated: {output_path}")
