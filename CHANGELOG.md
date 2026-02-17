# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.1] - 2026-02-17

### Added

- Initialized `uv` workspace monorepo with root `pyproject.toml`.
- Created library stubs: `nornweave-core`, `nornweave-storage`, `nornweave-testing`.
- Created service stubs: `router`, `fusion`, `memory-agent`, `registry`.
- Configured `ruff` (linting + formatting), `mypy` (strict for libs, standard for services), and `pre-commit` hooks.
- Set up `pytest` with `tests/unit/`, `tests/integration/`, `tests/e2e/` directories.
- Added `docker-compose.yaml` with pgvector (pg16) and Kafka (KRaft mode, 4 topics).
- Added `.gitignore` for Python monorepo.

[Unreleased]: https://github.com/southpawriter02/nornweave/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/southpawriter02/nornweave/releases/tag/v0.0.1
