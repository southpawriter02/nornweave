"""Tests for DatabaseConfig."""

import os
from unittest.mock import patch

from nornweave_storage.config import DatabaseConfig


class TestDatabaseConfigDefaults:
    def test_defaults(self) -> None:
        config = DatabaseConfig()
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.user == "nornweave"
        assert config.password == "nornweave_dev"
        assert config.name == "nornweave"

    def test_pool_defaults(self) -> None:
        config = DatabaseConfig()
        assert config.min_pool_size == 2
        assert config.max_pool_size == 10
        assert config.pool_timeout == 30.0

    def test_dsn(self) -> None:
        config = DatabaseConfig()
        assert config.dsn == "postgresql://nornweave:nornweave_dev@localhost:5432/nornweave"


class TestDatabaseConfigEnvOverride:
    def test_host_override(self) -> None:
        with patch.dict(os.environ, {"NORNWEAVE_DB_HOST": "db.example.com"}):
            config = DatabaseConfig()
        assert config.host == "db.example.com"

    def test_port_override(self) -> None:
        with patch.dict(os.environ, {"NORNWEAVE_DB_PORT": "5433"}):
            config = DatabaseConfig()
        assert config.port == 5433

    def test_all_overrides(self) -> None:
        env = {
            "NORNWEAVE_DB_HOST": "prod-db",
            "NORNWEAVE_DB_PORT": "5433",
            "NORNWEAVE_DB_USER": "admin",
            "NORNWEAVE_DB_PASSWORD": "secret",
            "NORNWEAVE_DB_NAME": "production",
        }
        with patch.dict(os.environ, env):
            config = DatabaseConfig()
        assert config.dsn == "postgresql://admin:secret@prod-db:5433/production"

    def test_pool_size_override(self) -> None:
        env = {
            "NORNWEAVE_DB_MIN_POOL_SIZE": "5",
            "NORNWEAVE_DB_MAX_POOL_SIZE": "20",
            "NORNWEAVE_DB_POOL_TIMEOUT": "60.0",
        }
        with patch.dict(os.environ, env):
            config = DatabaseConfig()
        assert config.min_pool_size == 5
        assert config.max_pool_size == 20
        assert config.pool_timeout == 60.0


class TestDatabaseConfigExplicit:
    def test_explicit_values(self) -> None:
        config = DatabaseConfig(
            host="custom-host",
            port=5555,
            user="custom_user",
            password="custom_pass",
            name="custom_db",
        )
        assert config.dsn == "postgresql://custom_user:custom_pass@custom-host:5555/custom_db"
