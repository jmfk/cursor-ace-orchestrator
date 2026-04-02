import os
import json
from typing import List, Dict, Any, Optional

class Evaluator:
    """
    Core evaluation logic and scoring for the SQE.
    """
    def __init__(self):
        pass

    def evaluate(self, decomposition: Dict[str, Any], examination: Dict[str, Any], test_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combines PRD analysis, code examination, and test results into a final quality score.
        """
        project_name = decomposition.get("project_name", "Unknown Project")
        
        # Flatten requirements
        flat_requirements = self._flatten_requirements(decomposition.get("requirements", []))
        total_reqs = len(flat_requirements)
        
        # Calculate scores
        evaluations = examination.get("evaluations", [])
        test_runs = test_results.get("test_run_results", [])
        
        # 1. PRD Coverage (what % of requirements are implemented)
        implemented_reqs = [e for e in evaluations if e.get("status") in ["Full", "Partial"]]
        coverage_score = (len(implemented_reqs) / total_reqs * 100) if total_reqs > 0 else 0
        
        # 2. Code Quality Score (average of quality scores from examination)
        quality_scores = [e.get("quality_score", 0) for e in evaluations if "quality_score" in e]
        avg_quality_score = (sum(quality_scores) / len(quality_scores)) if quality_scores else 0
        
        # 3. Functional Correctness (via test results)
        passed_tests = [t for t in test_runs if t.get("passed", False)]
        correctness_score = (len(passed_tests) / len(test_runs) * 100) if test_runs else 0
        
        # 4. Overall Quality Score (weighted average)
        # Weights: Coverage (30%), Quality (30%), Correctness (40%)
        overall_score = (coverage_score * 0.3) + (avg_quality_score * 0.3) + (correctness_score * 0.4)
        
        # 5. Usefulness/Value Score (heuristic based on coverage and quality)
        value_score = (overall_score * 0.8) + (coverage_score * 0.2)
        
        final_report = {
            "project_name": project_name,
            "overall_score": round(overall_score, 2),
            "value_score": round(value_score, 2),
            "metrics": {
                "total_requirements": total_reqs,
                "implemented_requirements": len(implemented_reqs),
                "coverage_score": round(coverage_score, 2),
                "average_quality_score": round(avg_quality_score, 2),
                "correctness_score": round(correctness_score, 2),
                "total_tests": len(test_runs),
                "passed_tests": len(passed_tests)
            },
            "detailed_evaluations": evaluations,
            "test_results": test_runs
        }
        
        return final_report

    def _flatten_requirements(self, requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flattens a hierarchical requirements list."""
        flat = []
        for req in requirements:
            flat.append(req)
            if "sub_requirements" in req:
                flat.extend(self._flatten_requirements(req["sub_requirements"]))
        return flat

    def save_final_report(self, report: Dict[str, Any], output_path: str):
        """Saves the final report to a JSON file."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
