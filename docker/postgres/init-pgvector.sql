-- Runs once on first container init (empty data volume). Required for pgvector columns in migrations.
CREATE EXTENSION IF NOT EXISTS vector;
