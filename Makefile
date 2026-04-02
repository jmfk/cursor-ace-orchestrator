.PHONY: build-ace install build-exe install-exe help install-ralph build-ralph-exe install-ralph-exe eval eval-llm report report-llm full-report

help:
	@echo "Cursor ACE Orchestrator - Development Commands"
	@echo "  make build-ace    Run the RALPH loop to iteratively build the system"
	@echo "  make install      Install the 'ace' and 'ralph' commands locally (editable)"
	@echo "  make install-ralph Install the 'ralph' command locally (editable)"
	@echo "  make build-exe    Build a self-contained 'ace' executable"
	@echo "  make install-exe  Build and install the 'ace' binary to /usr/local/bin"
	@echo "  make build-ralph-exe Build a self-contained 'ralph' executable"
	@echo "  make install-ralph-exe Build and install the 'ralph' binary to /usr/local/bin"
	@echo "  make eval         Evaluate recent git commits using heuristics (limit 10)"
	@echo "  make eval-llm     Evaluate recent git commits using Gemini Flash (limit 5)"
	@echo "  make report       Generate a markdown report with commit value graphs (limit 20)"
	@echo "  make report-llm   Generate a markdown report with LLM analysis (limit 10)"
	@echo "  make full-report  Analyze FULL history and aggregate value by milestones/features"

build-ace:
	python3 ralph_loop.py

install:
	pip install -e .

install-ralph:
	pip install -e .

build-exe:
	pip install pyinstaller
	pyinstaller --onefile --name ace ace.py --collect-all ace_lib --collect-all ace_api

install-exe: build-exe
	@echo "Installing 'ace' binary to /usr/local/bin..."
	sudo cp dist/ace /usr/local/bin/ace
	@echo "Successfully installed 'ace' command."

build-ralph-exe:
	pip install pyinstaller pyyaml
	pyinstaller --onefile --name ralph ralph_loop.py --hidden-import yaml

install-ralph-exe: build-ralph-exe
	@echo "Installing 'ralph' binary to /usr/local/bin..."
	sudo cp dist/ralph /usr/local/bin/ralph
	@echo "Successfully installed 'ralph' command."

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
