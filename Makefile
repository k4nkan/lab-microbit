SHELL := /bin/bash

ROOT_DIR := $(CURDIR)
EXT_DIR := $(ROOT_DIR)/microbit-edit-logger
LOCAL_DIR := $(ROOT_DIR)/microbit-edit-logger-local

MAKECODE_PORT := 3232
MAKECODE_WSPORT := 3233
EDITOR_PORT := 8080
EXTENSION_REPO := https://github.com/k4nkan/microbit-edit-logger

.PHONY: help setup build editor makecode dev dev-open ports stop-ports url

help:
	@echo "lab-microbit commands"
	@echo ""
	@echo "  make setup      install dependencies"
	@echo "  make build      build the MakeCode extension"
	@echo "  make dev-open   start editor UI and local MakeCode, then open browser"
	@echo "  make dev        start editor UI and local MakeCode without opening browser"
	@echo "  make editor     start only editor UI on :$(EDITOR_PORT)"
	@echo "  make makecode   start only local MakeCode on :$(MAKECODE_PORT)"
	@echo "  make ports      show local MakeCode/editor processes"
	@echo "  make stop-ports stop local MakeCode/editor processes"
	@echo ""
	@echo "Extension URL: $(EXTENSION_REPO)"

setup:
	cd "$(EXT_DIR)" && npm install
	cd "$(LOCAL_DIR)" && npm install

build:
	cd "$(EXT_DIR)" && npm run build

editor:
	cd "$(EXT_DIR)" && npm run serve:editor

makecode:
	cd "$(LOCAL_DIR)" && EXT_DIR="$(EXT_DIR)" npm run serve

dev:
	@set -e; \
		echo "Starting editor UI on http://localhost:$(EDITOR_PORT)/extension.html"; \
		(cd "$(EXT_DIR)" && npm run serve:editor) & \
		editor_pid=$$!; \
		trap 'kill $$editor_pid 2>/dev/null || true' EXIT INT TERM; \
		echo "Starting local MakeCode. Copy the local_token URL, then use:"; \
		echo "http://localhost:$(MAKECODE_PORT)/index.html?debugExtensions=1#local_token=...&wsport=$(MAKECODE_WSPORT)"; \
		cd "$(LOCAL_DIR)"; \
		EXT_DIR="$(EXT_DIR)" npm run serve

dev-open:
	@set -euo pipefail; \
		echo "Starting editor UI on http://localhost:$(EDITOR_PORT)/extension.html"; \
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
	@echo "MakeCode local URL:"
	@echo "http://localhost:$(MAKECODE_PORT)/index.html?debugExtensions=1#local_token=...&wsport=$(MAKECODE_WSPORT)"
	@echo ""
	@echo "Extension URL:"
	@echo "$(EXTENSION_REPO)"
