.PHONY: build-ace install build-exe install-exe help install-ralph build-ralph-exe install-ralph-exe eval eval-llm report report-llm full-report comprehensive migrate hierarchical analyze-commits check-quality sqe

help:
	@echo "Cursor ACE Orchestrator - Development Commands"
	@echo "  make build-ace       Run the RALPH loop (now hierarchical by default)"
	@echo "  make hierarchical    Alias for build-ace"
	@echo "  make sqe             Run the System Quality Evaluator (SQE)"
# ...
sqe:
	python3 -m sqe.sqe_loop "PRD-01 - Cursor-ace-orchestrator-prd.md"
	@echo "  make migrate         Migrate existing flat plan.md to hierarchical PlanTree"
	@echo "  make analyze-commits Analyze ALL git commits using Gemini for improvement scores"
	@echo "  make check-quality   Compare new commit quality against historical baseline"
	@echo "  make install         Install the 'ace' and 'ralph' commands locally (editable)"
	@echo "  make reinstall       Force a fresh link of the entry points"
	@echo "  make eval            Evaluate recent git commits using heuristics"
	@echo "  make eval-llm        Evaluate recent git commits using Gemini Flash (limit 5)"
	@echo "  make report          Generate a markdown report with commit value graphs"
	@echo "  make report-llm      Generate a markdown report with LLM analysis (limit 10)"
	@echo "  make full-report     Analyze FULL history and aggregate value by milestones/features"
	@echo "  make comprehensive   Generate a comprehensive report (Time-series + Milestones + Commits)"

build-ace:
	python3 ralph_loop.py

install:
	pip install -e .

reinstall:
	pip uninstall -y cursor-ace
	pip install -e .

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

hierarchical: build-ace

migrate:
	python3 migrate_plan.py

analyze-commits:
	python3 analyze_commits.py

check-quality:
	pytest tests/test_improvement_trend.py -s
