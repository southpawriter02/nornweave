"""Initial schema — documents, chunks, and pgvector.

Revision ID: 001
Revises: None
Create Date: 2026-02-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE documents (
            id              VARCHAR(255) PRIMARY KEY,
            domain_id       VARCHAR(255) NOT NULL,
            source_path     TEXT         NOT NULL,
            content         TEXT         NOT NULL,
            content_hash    VARCHAR(64)  NOT NULL,
            metadata        JSONB        NOT NULL DEFAULT '{}',
            ingested_at     TIMESTAMPTZ  NOT NULL,
            source_updated_at TIMESTAMPTZ NOT NULL,

            UNIQUE (domain_id, content_hash)
        )
    """)

    op.execute("CREATE INDEX idx_documents_domain_id ON documents (domain_id)")
    op.execute("CREATE INDEX idx_documents_ingested_at ON documents (ingested_at)")

    op.execute("""
        CREATE TABLE chunks (
            id                   VARCHAR(255) PRIMARY KEY,
            document_id          VARCHAR(255) NOT NULL
                                     REFERENCES documents(id) ON DELETE CASCADE,
            domain_id            VARCHAR(255) NOT NULL,
            content              TEXT         NOT NULL,
            embedding            vector(768)  NOT NULL,
            embedding_dimensions INTEGER      NOT NULL,
            embedding_model_name VARCHAR(255) NOT NULL,
            position             INTEGER      NOT NULL,
            token_count          INTEGER      NOT NULL,
            metadata             JSONB        NOT NULL DEFAULT '{}',
            created_at           TIMESTAMPTZ  NOT NULL
        )
    """)

    op.execute("CREATE INDEX idx_chunks_document_id ON chunks (document_id)")
    op.execute("CREATE INDEX idx_chunks_domain_id ON chunks (domain_id)")
    op.execute("""
        CREATE INDEX idx_chunks_embedding
        ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
