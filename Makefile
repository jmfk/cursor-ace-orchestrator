.PHONY: build-ace install build-exe install-exe help install-ralph

help:
	@echo "Cursor ACE Orchestrator - Development Commands"
	@echo "  make build-ace    Run the RALPH loop to iteratively build the system"
	@echo "  make install      Install the 'ace' and 'ralph' commands locally (editable)"
	@echo "  make install-ralph Install the 'ralph' command locally (editable)"
	@echo "  make build-exe    Build a self-contained executable using PyInstaller"
	@echo "  make install-exe  Build and install the self-contained 'ace' binary to /usr/local/bin"

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
