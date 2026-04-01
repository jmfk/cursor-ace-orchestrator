.PHONY: build-ace install help

help:
	@echo "Cursor ACE Orchestrator - Development Commands"
	@echo "  make build-ace    Run the RALPH loop to iteratively build the system"
	@echo "  make install      Install the 'ace' command locally"

build-ace:
	python3 ralph_loop.py

install:
	pip install -e .
