SHELL := /bin/bash

LOCAL_DIR := $(CURDIR)
EXT_DIR ?= $(abspath $(LOCAL_DIR)/../microbit-edit-logger)

MAKECODE_PORT := 3232
MAKECODE_WSPORT := 3233
EDITOR_PORT := 8080
EXTENSION_REPO ?= https://github.com/k4nkan/microbit-edit-logger

.PHONY: help setup editor makecode dev dev-open ports stop-ports url

help:
	@echo "microbit-edit-logger local commands"
	@echo ""
	@echo "  make setup      npm install for extension and local runner"
	@echo "  make dev-open   start both servers and open MakeCode with debugExtensions"
	@echo "  make dev        start both servers without opening browser"
	@echo "  make editor     start only editor extension UI on :$(EDITOR_PORT)"
	@echo "  make makecode   start only local MakeCode on :$(MAKECODE_PORT)"
	@echo "  make ports      show processes using :$(MAKECODE_PORT), :$(MAKECODE_WSPORT), :$(EDITOR_PORT)"
	@echo "  make stop-ports kill processes using :$(MAKECODE_PORT), :$(MAKECODE_WSPORT), :$(EDITOR_PORT)"
	@echo ""
	@echo "Extension URL for MakeCode:"
	@echo "  $(EXTENSION_REPO)"

setup:
	cd "$(EXT_DIR)" && npm install
	cd "$(LOCAL_DIR)" && npm install

editor:
	cd "$(EXT_DIR)" && npm run serve:editor

makecode:
	cd "$(LOCAL_DIR)" && EXT_DIR="$(EXT_DIR)" npm run serve

dev:
	@set -e; \
	echo "Starting editor extension UI on http://localhost:$(EDITOR_PORT)/extension.html"; \
	(cd "$(EXT_DIR)" && npm run serve:editor) & \
	editor_pid=$$!; \
	trap 'kill $$editor_pid 2>/dev/null || true' EXIT INT TERM; \
	echo "Starting local MakeCode. Copy the local_token URL, then use:"; \
	echo "http://localhost:$(MAKECODE_PORT)/index.html?debugExtensions=1#local_token=...&wsport=$(MAKECODE_WSPORT)"; \
	cd "$(LOCAL_DIR)"; \
	EXT_DIR="$(EXT_DIR)" npm run serve

dev-open:
	@set -euo pipefail; \
	echo "Starting editor extension UI on http://localhost:$(EDITOR_PORT)/extension.html"; \
	(cd "$(EXT_DIR)" && npm run serve:editor) & \
	editor_pid=$$!; \
	opened=0; \
	trap 'kill $$editor_pid 2>/dev/null || true' EXIT INT TERM; \
	echo "Starting local MakeCode. The browser opens after local_token is printed."; \
	cd "$(LOCAL_DIR)"; \
	EXT_DIR="$(EXT_DIR)" npm run serve 2>&1 | while IFS= read -r line; do \
		echo "$$line"; \
		if [[ $$opened -eq 0 && "$$line" =~ http://localhost:$(MAKECODE_PORT)/\#local_token=([^[:space:]]+) ]]; then \
			url="http://localhost:$(MAKECODE_PORT)/index.html?debugExtensions=1#local_token=$${BASH_REMATCH[1]}"; \
			echo ""; \
			echo "Opening MakeCode:"; \
			echo "$$url"; \
			open "$$url"; \
			opened=1; \
		fi; \
	done

ports:
	@lsof -nP -iTCP:$(MAKECODE_PORT) -sTCP:LISTEN || true
	@lsof -nP -iTCP:$(MAKECODE_WSPORT) -sTCP:LISTEN || true
	@lsof -nP -iTCP:$(EDITOR_PORT) -sTCP:LISTEN || true

stop-ports:
	@for port in $(MAKECODE_PORT) $(MAKECODE_WSPORT) $(EDITOR_PORT); do \
		pids=$$(lsof -tiTCP:$$port -sTCP:LISTEN || true); \
		if [[ -n "$$pids" ]]; then \
			echo "Killing port $$port: $$pids"; \
			kill $$pids; \
		fi; \
	done

url:
	@echo "Use the local_token from npm run serve:"
	@echo "http://localhost:$(MAKECODE_PORT)/index.html?debugExtensions=1#local_token=...&wsport=$(MAKECODE_WSPORT)"
	@echo ""
	@echo "Extension URL:"
	@echo "$(EXTENSION_REPO)"
