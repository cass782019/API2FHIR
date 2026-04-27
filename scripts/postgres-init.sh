#!/bin/bash
# scripts/postgres-init.sh
# Cria múltiplas databases no boot do container Postgres.
# Lido pelo entrypoint do pgvector/pgvector via /docker-entrypoint-initdb.d/

set -e
set -u

function create_user_and_database() {
    local database=$1
    echo "  Creating database '$database'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE DATABASE $database;
        GRANT ALL PRIVILEGES ON DATABASE $database TO $POSTGRES_USER;
EOSQL
}

function enable_pgvector() {
    local database=$1
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" <<-EOSQL
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE EXTENSION IF NOT EXISTS unaccent;
EOSQL
    echo "  pgvector + pg_trgm + unaccent habilitados em '$database'"
}

if [ -n "${POSTGRES_MULTIPLE_DATABASES:-}" ]; then
    echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"
    for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
        create_user_and_database $db
        enable_pgvector $db
    done
    echo "Multiple databases created"
fi

# Habilita também no database default (forge)
enable_pgvector "$POSTGRES_USER"
