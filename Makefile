.PHONY: install dev lint format typecheck test test-cov clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -r requirements.txt

dev: ## Install all dependencies (production + dev tools)
	pip install -r requirements.txt
	pip install -e ".[dev]"

lint: ## Run Ruff linter
	ruff check agents/ tests/

format: ## Format code with Ruff
	ruff format agents/ tests/

format-check: ## Check formatting without changing files
	ruff format --check agents/ tests/

typecheck: ## Run Pyright type checker
	pyright agents/ tests/

test: ## Run tests
	pytest tests/ -v

test-cov: ## Run tests with coverage report
	pytest tests/ --cov=agents --cov-report=term-missing

check: lint format-check typecheck test ## Run all checks (lint + format + types + tests)

clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/

# --- Agent commands ---

generate-episode: ## Generate episode script (use: make generate-episode EP=1)
	python agents/generate_episode.py --episode $(EP)

generate-video: ## Generate scene video (use: make generate-video SCENE=data/episodes/1/scenes/scene_1_prompt.yaml)
	python agents/generate_video.py --scene $(SCENE)

validate: ## Validate episode quality (use: make validate EP=1)
	python agents/validate_quality.py --episode $(EP)

compose: ## Compose episode from clips (use: make compose EP=1)
	python agents/compose_episode.py --episode $(EP)

publish: ## Publish episode to site (use: make publish EP=1)
	python agents/publish_site.py --episode $(EP)

tally: ## Tally votes (use: make tally EP=1)
	python agents/tally_votes.py --episode $(EP) --format summary
