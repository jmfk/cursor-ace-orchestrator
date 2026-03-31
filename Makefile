.PHONY: build-ace help

help:
	@echo "Cursor ACE Orchestrator - Development Commands"
	@echo "  make build-ace    Run the RALPH loop to iteratively build the system"

build-ace:
	python3 ralph_loop.py
