# syntax=docker/dockerfile:1
#
# VibeSOP e2e VALIDATION base image (arm64-native, Apple Silicon / OrbStack).
#
# What's baked in:
#   - Python 3.12  (project requires >=3.12)
#   - uv          (matches the project's package manager)
#   - full dev/test deps in /opt/venv  (ruff, mypy, basedpyright, pytest + plugins)
#   - node 20 + bun  (for pack-install / package.json / local-build e2e)
#
# What's NOT baked in:
#   - the project source. Mount the repo at /repo at runtime so each validation
#     runs against the live (post-fix) code. `uv run --frozen` installs the
#     project editable into the pre-built /opt/venv (fast, offline).
#   - the `semantic` extra (pulls sentence-transformers -> torch, GBs). Add
#     per-feature if an embedding-matching scenario actually needs it.
#
# Example per-feature validation:
#   docker run --rm -v "$PWD":/repo -w /repo vibesop-val-base:py3.12 \
#       uv run --frozen pytest tests/unit -q

FROM --platform=linux/arm64 python:3.12-slim

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# system deps: git (pack clone e2e), build-essential (any C ext / hatchling builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

# node 20 + bun (package.json preinstall / local-build-script e2e)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g bun \
    && rm -rf /var/lib/apt/lists/*

# uv (copy the binary from the official image — no separate install step)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# pre-install ALL dev/test deps (NO project source, NO semantic/torch).
# `--no-install-project` so we don't need src/ here; the project is installed
# editable at runtime against the mounted repo.
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN uv sync --extra dev --frozen --no-install-project

# callers mount the repo here
WORKDIR /repo
CMD ["bash"]
