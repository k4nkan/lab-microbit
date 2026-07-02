SHELL := /bin/bash

ROOT_DIR := $(CURDIR)
EXT_DIR := $(ROOT_DIR)/microbit-edit-logger
LOCAL_DIR := $(ROOT_DIR)/microbit-edit-logger-local

MAKECODE_PORT := 3232
MAKECODE_WSPORT := 3233
EDITOR_PORT := 8080

.PHONY: setup dev build stop

setup:
	cd "$(EXT_DIR)" && npm install
	cd "$(LOCAL_DIR)" && npm install

dev:
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

build:
	cd "$(EXT_DIR)" && npm run build

stop:
	@for port in $(MAKECODE_PORT) $(MAKECODE_WSPORT) $(EDITOR_PORT); do \
		pids=$$(lsof -tiTCP:$$port -sTCP:LISTEN || true); \
		if [[ -n "$$pids" ]]; then \
			echo "Killing port $$port: $$pids"; \
			kill $$pids; \
		fi; \
	done
