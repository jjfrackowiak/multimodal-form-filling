.PHONY: check eval eval-b6 eval-b7 eval-b9 lint format typecheck imports test sync

# All first-party packages, for lint/typecheck (which apply uniformly).
PACKAGES := packages/mff-contracts packages/mff-vision packages/mff-docmodel \
            packages/mff-manifest packages/mff-applier packages/mff-store packages/mff-fakes
SERVICES := services/email-service services/editor-service

# Coverage-gated at >=85%. mff-vision and services/cv stay ungated.
COVERAGE_PACKAGES := packages/mff-contracts packages/mff-docmodel packages/mff-manifest \
                      packages/mff-applier packages/mff-store packages/mff-fakes \
                      services/email-service services/editor-service
UNGATED_PACKAGES := packages/mff-vision services/cv

sync:
	uv sync --all-packages

check: lint typecheck imports test

lint:
	uv run ruff format --check packages services
	uv run ruff check packages services

format:
	uv run ruff format packages services
	uv run ruff check --fix packages services

typecheck:
	@set -e; \
	for pkg in $(PACKAGES) $(SERVICES); do \
		echo "== mypy $$pkg =="; \
		uv run mypy "$$pkg/src" "$$pkg/tests"; \
	done

imports:
	uv run lint-imports

# Coverage is measured per package (not globally) so one well-tested package
# cannot hide four untested ones.
test:
	@set -e; \
	for pkg in $(COVERAGE_PACKAGES); do \
		name=$$(basename "$$pkg" | tr '-' '_'); \
		echo "== $$pkg ($$name) =="; \
		uv run pytest "$$pkg/tests" -q \
			--cov="$$name" --cov-report=term-missing --cov-fail-under=85; \
	done
	@for pkg in $(UNGATED_PACKAGES); do \
		echo "== $$pkg (no new coverage gate — pre-existing, not B0's) =="; \
		uv run pytest "$$pkg/tests" -q; \
	done

# Live model evaluation is deliberately separate from `test`: it consumes ADC-backed
# Gemini calls and reports structural scores through pydantic-evals.
eval: eval-b6 eval-b7 eval-b9

eval-b6:
	@test -n "$(GOOGLE_CLOUD_PROJECT)" || (echo "Set GOOGLE_CLOUD_PROJECT before make eval"; exit 2)
	uv run python evals/b6/run.py

eval-b7:
	@test -n "$(GOOGLE_CLOUD_PROJECT)" || (echo "Set GOOGLE_CLOUD_PROJECT before make eval"; exit 2)
	MFF_B7_LIVE_EVAL=1 uv run python evals/b7/run.py

eval-b9:
	@test -n "$(GOOGLE_CLOUD_PROJECT)" || (echo "Set GOOGLE_CLOUD_PROJECT before make eval"; exit 2)
	MFF_B9_LIVE_EVAL=1 uv run python evals/b9/run.py
