.PHONY: test coverage lint ios-create ios-build ios-run ios-logs ios

# Desktop test suite
test:
	python3 -m pytest tests/unit/ -v

lint:
	pylint src tests

coverage:
	python3 -m pytest tests/unit/ --cov=. --cov-report=term-missing

# ── iOS / Briefcase ──────────────────────────────────────────────────────────
# Venv: .venv-mobile (Python 3.12, created by: python3.12 -m venv .venv-mobile)
# Config: src/ios/pyproject.toml
# Simulator UUID: 446DA412-2BE7-43A6-BA99-26B85E010A93

BRIEFCASE   := .venv-mobile/bin/briefcase
IOS_SIM     := 446DA412-2BE7-43A6-BA99-26B85E010A93
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
	xcrun simctl spawn $(IOS_SIM) log stream --predicate 'processImagePath contains "Krate"'
