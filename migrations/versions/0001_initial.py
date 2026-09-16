"""initial schema

Revision ID: 0001_initial
Revises:
"""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE sources (
          id uuid PRIMARY KEY, name varchar(200) NOT NULL, provider varchar(20) NOT NULL,
          root_path text NOT NULL UNIQUE, enabled boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_sources_provider ON sources(provider);

        CREATE TABLE import_jobs (
          id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          status varchar(20) NOT NULL DEFAULT 'pending', files_total integer NOT NULL DEFAULT 0,
          files_processed integer NOT NULL DEFAULT 0, conversations_processed integer NOT NULL DEFAULT 0,
          messages_processed integer NOT NULL DEFAULT 0, error_count integer NOT NULL DEFAULT 0,
          checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb, last_error text,
          started_at timestamptz, finished_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_import_jobs_source_id ON import_jobs(source_id);
        CREATE INDEX ix_import_jobs_status ON import_jobs(status);

        CREATE TABLE import_files (
          id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          relative_path text NOT NULL, sha256 varchar(64) NOT NULL, size_bytes bigint NOT NULL,
          modified_ns bigint NOT NULL, status varchar(20) NOT NULL DEFAULT 'pending', error text,
          imported_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_id, relative_path)
        );
        CREATE INDEX ix_import_files_source_id ON import_files(source_id);
        CREATE INDEX ix_import_files_sha256 ON import_files(sha256);

        CREATE TABLE conversations (
          id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          provider_conversation_id varchar(255), fingerprint varchar(64) NOT NULL, title text NOT NULL,
          source_created_at timestamptz, source_updated_at timestamptz,
          current_node_source_id varchar(255), raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(source_id, provider_conversation_id), UNIQUE(source_id, fingerprint)
        );
        CREATE INDEX ix_conversations_source_id ON conversations(source_id);
        CREATE INDEX ix_conversation_source_updated ON conversations(source_id, source_updated_at);

        CREATE TABLE messages (
          id uuid PRIMARY KEY, conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
          source_file_id uuid REFERENCES import_files(id) ON DELETE SET NULL,
          source_message_id varchar(255), parent_source_id varchar(255), fingerprint varchar(64) NOT NULL,
          role varchar(30) NOT NULL, content_type varchar(50) NOT NULL DEFAULT 'text', body text NOT NULL,
          source_created_at timestamptz, sort_order integer NOT NULL DEFAULT 0,
          is_current_path boolean NOT NULL DEFAULT true, raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(conversation_id, source_message_id), UNIQUE(conversation_id, fingerprint)
        );
        CREATE INDEX ix_messages_conversation_id ON messages(conversation_id);
        CREATE INDEX ix_messages_source_created_at ON messages(source_created_at);
        CREATE INDEX ix_messages_role ON messages(role);
        CREATE INDEX ix_messages_is_current_path ON messages(is_current_path);
        CREATE INDEX ix_message_conversation_order ON messages(conversation_id, sort_order);

        CREATE TABLE message_revisions (
          id uuid PRIMARY KEY, message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
          body text NOT NULL, raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          recorded_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_message_revisions_message_id ON message_revisions(message_id);

        CREATE TABLE attachments (
          id uuid PRIMARY KEY, message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
          relative_path text NOT NULL, original_name text NOT NULL, mime_type varchar(255), size_bytes bigint,
          fingerprint varchar(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(message_id, fingerprint)
        );
        CREATE INDEX ix_attachments_message_id ON attachments(message_id);

        CREATE TABLE search_chunks (
          id uuid PRIMARY KEY, message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
          position integer NOT NULL, title text NOT NULL DEFAULT '', body text NOT NULL,
          token_count integer NOT NULL DEFAULT 0,
          search_vector tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('pg_catalog.simple', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('pg_catalog.simple', coalesce(body, '')), 'B')
          ) STORED,
          embedding vector(384), embedding_model varchar(255), embedding_error text,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(message_id, position)
        );
        CREATE INDEX ix_search_chunks_message_id ON search_chunks(message_id);
        CREATE INDEX ix_search_chunks_fts ON search_chunks USING gin(search_vector);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS search_chunks;
        DROP TABLE IF EXISTS attachments;
        DROP TABLE IF EXISTS message_revisions;
        DROP TABLE IF EXISTS messages;
        DROP TABLE IF EXISTS conversations;
        DROP TABLE IF EXISTS import_files;
        DROP TABLE IF EXISTS import_jobs;
        DROP TABLE IF EXISTS sources;
        """
    )
