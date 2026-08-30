-- Creates the extensions the rest of the schema needs BEFORE creating the
-- schema.  pgcrypto and libzlintpq are NOT created here: sql/create_schema.sql
-- creates them (10_certwatch_schema.sh).
CREATE EXTENSION IF NOT EXISTS libx509pq;
CREATE EXTENSION IF NOT EXISTS libocsppq;