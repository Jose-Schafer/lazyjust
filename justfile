set dotenv-load := true

default:
    @just --list

# Run uv directly
uv *args:
    uv {{ args }}

# Start the TUI
run:
    uv run python main.py

# Lint Python
lint:
    uv run ruff check .

# Format Python
fmt:
    uv run ruff format .

# Run tests
test:
    uv run pytest

# Reinstall
reinstall:
    uv tool install --reinstall /Users/joseschafer/Documents/lazypro
