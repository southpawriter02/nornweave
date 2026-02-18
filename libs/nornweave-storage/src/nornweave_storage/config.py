"""Database configuration via environment variables."""

from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    """PostgreSQL connection settings, loaded from NORNWEAVE_DB_* env vars.

    Defaults match the docker-compose.yaml dev environment.
    """

    model_config = {"env_prefix": "NORNWEAVE_DB_"}

    host: str = "localhost"
    port: int = 5432
    user: str = "nornweave"
    password: str = "nornweave_dev"  # noqa: S105
    name: str = "nornweave"

    min_pool_size: int = 2
    max_pool_size: int = 10
    pool_timeout: float = 30.0

    @property
    def dsn(self) -> str:
        """PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
