import os
import json
import argparse
from datetime import datetime
from .lib.prd_analyzer import PRDAnalyzer
from .lib.code_examiner import CodeExaminer
from .lib.test_builder import TestBuilder
from .lib.evaluator import Evaluator
from .lib.reporting import Reporting

class SQELoop:
    """
    Main orchestration loop for the System Quality Evaluator (SQE).
    """
    def __init__(self, prd_path: str, model_name: str = "gemini-3-flash-preview"):
        self.prd_path = prd_path
        self.model_name = model_name
        self.data_dir = "sqe/data"
        self.reports_dir = os.path.join(self.data_dir, "reports")
        os.makedirs(self.reports_dir, exist_ok=True)
        
        self.analyzer = PRDAnalyzer(model_name=model_name)
        self.examiner = CodeExaminer(model_name=model_name)
        self.test_builder = TestBuilder(model_name=model_name)
        self.evaluator = Evaluator()
        self.reporting = Reporting()

    def run(self):
        """
        Executes the full SQE evaluation workflow.
        """
        print(f"🚀 Starting SQE Evaluation for PRD: {self.prd_path}", flush=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(self.data_dir, f"session_{timestamp}")
        os.makedirs(session_dir, exist_ok=True)

        # 1. PRD Analysis
        print("Step 1: Analyzing PRD and decomposing requirements...", flush=True)
        decomposition = self.analyzer.analyze(self.prd_path)
        self.analyzer.save_decomposition(decomposition, os.path.join(session_dir, "decomposition.json"))

        # 2. Code Examination
        print("Step 2: Examining code against requirements...", flush=True)
        examination = self.examiner.examine(decomposition)
        self.examiner.save_examination(examination, os.path.join(session_dir, "examination.json"))

        # 3. Test Building & Execution
        print("Step 3: Building and running evaluation tests...", flush=True)
        test_data = self.test_builder.build_tests(decomposition, examination)
        self.test_builder.save_test_results(test_data, os.path.join(session_dir, "tests_generated.json"))
        
        test_run_results = self.test_builder.run_tests(test_data)
        self.test_builder.save_test_results(test_run_results, os.path.join(session_dir, "test_run_results.json"))

        # 4. Final Evaluation
        print("Step 4: Performing final evaluation and scoring...", flush=True)
        final_report = self.evaluator.evaluate(decomposition, examination, test_run_results)
        self.evaluator.save_final_report(final_report, os.path.join(session_dir, "final_report.json"))

        # 5. Reporting & Visualization
        print("Step 5: Generating reports and visualizations...", flush=True)
        markdown_report_path = os.path.join(self.reports_dir, f"quality_report_{timestamp}.md")
        self.reporting.generate_markdown_report(final_report, markdown_report_path)
        
        # Update trend data
        self.reporting.update_trend_data(final_report, os.path.join(self.data_dir, "sqe_history.jsonl"))
        
        # Generate trend visualization
        trend_html_path = os.path.join(self.reports_dir, "quality_trend.html")
        self.reporting.generate_trend_visualization(os.path.join(self.data_dir, "sqe_history.jsonl"), trend_html_path)

        print(f"✅ SQE Evaluation complete! Report: {markdown_report_path}", flush=True)
        return final_report

def main():
    parser = argparse.ArgumentParser(description="System Quality Evaluator (SQE)")
    parser.add_argument("prd_path", help="Path to the PRD file to evaluate")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="LLM model to use")
    args = parser.parse_args()

    sqe = SQELoop(args.prd_path, model_name=args.model)
    sqe.run()

if __name__ == "__main__":
    main()
