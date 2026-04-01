.PHONY: build-ace install build-exe help

help:
	@echo "Cursor ACE Orchestrator - Development Commands"
	@echo "  make build-ace    Run the RALPH loop to iteratively build the system"
	@echo "  make install      Install the 'ace' command locally (editable)"
	@echo "  make build-exe    Build a self-contained executable using PyInstaller"

build-ace:
	python3 ralph_loop.py

install:
	pip install -e .

build-exe:
	pip install pyinstaller
	pyinstaller --onefile --name ace ace.py --collect-all ace_lib --collect-all ace_api
