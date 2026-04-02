.PHONY: build-ace install build-exe install-exe help install-rolf build-rolf-exe install-rolf-exe eval eval-llm report report-llm full-report comprehensive test

help:
	@echo "Cursor ACE Orchestrator - Development Commands"
	@echo "  make rolf --help    Run the ROLF loop to iteratively build the system"
	@echo "  make install      Install the 'ace' and 'rolf' commands locally (editable)"
	@echo "  make eval         Evaluate recent git commits using heuristics"
	@echo "  make eval-llm     Evaluate recent git commits using Gemini Flash (limit 5)"
	@echo "  make report       Generate a markdown report with commit value graphs"
	@echo "  make report-llm   Generate a markdown report with LLM analysis (limit 10)"
	@echo "  make full-report  Analyze FULL history and aggregate value by milestones/features"
	@echo "  make comprehensive Generate a comprehensive report (Time-series + Milestones + Commits)"
	@echo "  make test         Run all tests in the tests/ directory (including SQE tests)"

rolf:
	python3 rolf_loop.py

install:
	pip install .

eval:
	python3 commit_evaluator.py 

eval-llm:
	python3 commit_evaluator.py --limit 5 --llm

report:
	python3 commit_evaluator.py --report --output commit_value_report.md

report-llm:
	python3 commit_evaluator.py --limit 10 --llm --report --output commit_value_report_llm.md

full-report:
	python3 commit_evaluator.py --all --output milestone_value_report.md

comprehensive:
	python3 commit_evaluator.py --all --output comprehensive_value_report.md

test:
	pytest tests/
