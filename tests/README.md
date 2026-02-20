# Tests

## Structure

- `tests/unit/` — fast unit tests (no device required)
- `tests/e2e/` — end-to-end tests that talk to an EP-133 (marked `e2e`)
- `tests/fixtures/` — sample WAVs and captured outputs used during development

## Running

- Unit tests (default): `pytest`
- E2E tests: `pytest -m e2e --device "EP-133"`
