"""Smoke tests to verify all package stubs are importable."""

from __future__ import annotations


def test_core_version() -> None:
    from nornweave_core import __version__

    assert __version__ == "0.0.2"


def test_storage_version() -> None:
    from nornweave_storage import __version__

    assert __version__ == "0.0.1"


def test_testing_version() -> None:
    from nornweave_testing import __version__

    assert __version__ == "0.0.1"


def test_router_version() -> None:
    from nornweave_router import __version__

    assert __version__ == "0.0.1"


def test_fusion_version() -> None:
    from nornweave_fusion import __version__

    assert __version__ == "0.0.1"


def test_memory_agent_version() -> None:
    from nornweave_memory import __version__

    assert __version__ == "0.0.1"


def test_registry_version() -> None:
    from nornweave_registry import __version__

    assert __version__ == "0.0.1"
