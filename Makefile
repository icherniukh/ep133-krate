.PHONY: test coverage lint ios-create ios-build ios-run ios-logs ios

# Desktop test suite
test:
	python3 -m pytest tests/unit/ -v

lint:
	pylint src tests

coverage:
	python3 -m pytest tests/unit/ --cov=. --cov-report=term-missing

# ── iOS / Briefcase ──────────────────────────────────────────────────────────
# See CONTRIBUTING.md for setup. IOS_SIM can be set to a simulator UDID.

BRIEFCASE   := .venv-mobile/bin/briefcase
IOS_SIM     ?= auto
IOS_DIR     := src/ios

ios-create:
	cd $(IOS_DIR) && ../../$(BRIEFCASE) create iOS

ios-build:
	cd $(IOS_DIR) && ../../$(BRIEFCASE) build iOS

ios-run:
	cd $(IOS_DIR) && ../../$(BRIEFCASE) run iOS -d $(IOS_SIM)

# Rebuild from scratch and launch — standard agent workflow
ios: ios-create ios-build ios-run

# Stream simulator logs (separate terminal; useful when run is backgrounded)
ios-logs:
	xcrun simctl spawn $(if $(filter auto,$(IOS_SIM)),booted,$(IOS_SIM)) log stream --predicate 'processImagePath contains "Krate"'
