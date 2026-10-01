#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${APP_CONFIG:-}" ]]; then
    DEPLOYED_CONFIG="${ROOT_DIR}/../../conf/serviceindex.conf"
    if [[ -f "$DEPLOYED_CONFIG" ]]; then
        export APP_CONFIG="$DEPLOYED_CONFIG"
    fi
fi

load_config_value() {
    local key="$1"
    local config_file="${APP_CONFIG:-}"

    if [[ -n "$config_file" && -f "$config_file" ]]; then
        python3 - "$config_file" "$key" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as config_file:
    value = json.load(config_file).get(sys.argv[2], "")
print("" if value is None else value)
PY
    fi
}

TARGET_DB=""
DB_USER="${DJANGO_USER:-$(load_config_value DJANGO_USER)}"
DB_USER="${DB_USER:-serviceindex_django}"
DB_PASS="${DJANGO_PASS:-$(load_config_value DJANGO_PASS)}"
DB_SCHEMA="${DB_SCHEMA:-$(load_config_value DB_SCHEMA)}"
DB_SCHEMA="${DB_SCHEMA:-$DB_USER}"
DB_HOST="${DB_HOSTNAME_READ:-$(load_config_value DB_HOSTNAME_READ)}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-$(load_config_value DB_PORT)}"
DB_PORT="${DB_PORT:-5432}"
DB_SSLMODE="${DB_SSLMODE:-$(load_config_value DB_SSLMODE)}"
DB_SSLROOTCERT="${DB_SSLROOTCERT:-$(load_config_value DB_SSLROOTCERT)}"
DRY_RUN=0

EXPECTED_TABLES=(
    auth_user
    django_migrations
    services_availability
    services_event
    services_host
    services_hosteventlog
    services_hosteventstatus
    services_link
    services_logentry
    services_misc_urls
    services_service
    services_site
    services_staff
    services_support
)

usage() {
    cat <<EOF
Usage: ./database/verify_db.sh --target-db NAME [options]

Run structural and ownership checks against a restored Service Index database.

Options:
  --target-db NAME  Explicit database to verify (required)
  --schema NAME     Application schema (default: ${DB_SCHEMA})
  --dry-run         Print the checks without connecting
  --help            Show this help
EOF
}

validate_identifier() {
    local value="$1"
    local label="$2"
    if [[ ! "$value" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "Invalid ${label}: ${value}" >&2
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-db)
            [[ $# -ge 2 ]] || { echo "--target-db requires a value" >&2; exit 1; }
            TARGET_DB="$2"
            shift 2
            ;;
        --schema)
            [[ $# -ge 2 ]] || { echo "--schema requires a value" >&2; exit 1; }
            DB_SCHEMA="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "$TARGET_DB" ]]; then
    usage >&2
    exit 1
fi
validate_identifier "$TARGET_DB" "target database"
validate_identifier "$DB_USER" "database user"
validate_identifier "$DB_SCHEMA" "schema"

echo "Preparing Service Index database verification"
echo "  target database: ${TARGET_DB}"
echo "  schema:          ${DB_SCHEMA}"
echo "  user:            ${DB_USER}"
echo "  host:            ${DB_HOST}:${DB_PORT}"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry run only. Planned checks:"
    echo "  - authenticated connection resolves to ${TARGET_DB}"
    echo "  - schema ${DB_SCHEMA} exists"
    echo "  - expected Django and Service Index tables exist"
    echo "  - application tables are owned by ${DB_USER}"
    echo "  - migrations and representative tables have row counts"
    echo "  - application sequences exist"
    exit 0
fi

if [[ -n "$DB_SSLMODE" ]]; then
    export PGSSLMODE="$DB_SSLMODE"
fi
if [[ -n "$DB_SSLROOTCERT" ]]; then
    export PGSSLROOTCERT="$DB_SSLROOTCERT"
fi

run_psql() {
    if [[ -n "$DB_PASS" ]]; then
        PGPASSWORD="$DB_PASS" psql -X -h "$DB_HOST" -p "$DB_PORT" \
            -U "$DB_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1 "$@"
    else
        env -u PGPASSWORD psql -X -h "$DB_HOST" -p "$DB_PORT" \
            -U "$DB_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1 "$@"
    fi
}

connected_database="$(run_psql -t -A -c "SELECT current_database();" | xargs)"
if [[ "$connected_database" != "$TARGET_DB" ]]; then
    echo "Connection resolved to unexpected database: $connected_database" >&2
    exit 1
fi
echo "OK: connected to ${TARGET_DB}"

schema_exists="$(run_psql -t -A -c "
SELECT count(*) FROM pg_namespace WHERE nspname = '${DB_SCHEMA}';
" | xargs)"
if [[ "$schema_exists" != "1" ]]; then
    echo "Expected schema does not exist: $DB_SCHEMA" >&2
    exit 1
fi
echo "OK: schema ${DB_SCHEMA} exists"

table_count="$(run_psql -t -A -c "
SELECT count(*)
FROM information_schema.tables
WHERE table_schema = '${DB_SCHEMA}' AND table_type = 'BASE TABLE';
" | xargs)"
echo "Application table count: $table_count"

missing=0
echo "Expected table checks:"
for table in "${EXPECTED_TABLES[@]}"; do
    present="$(run_psql -t -A -c "
SELECT count(*)
FROM information_schema.tables
WHERE table_schema = '${DB_SCHEMA}'
  AND table_name = '${table}'
  AND table_type = 'BASE TABLE';
" | xargs)"
    if [[ "$present" == "1" ]]; then
        rows="$(run_psql -t -A -c "SELECT count(*) FROM \"${DB_SCHEMA}\".\"${table}\";" | xargs)"
        echo "  OK: ${table} (rows: ${rows})"
    else
        echo "  MISSING: ${table}" >&2
        missing=$((missing + 1))
    fi
done

wrong_owner="$(run_psql -t -A -c "
SELECT count(*)
FROM pg_tables
WHERE schemaname = '${DB_SCHEMA}' AND tableowner <> '${DB_USER}';
" | xargs)"
if [[ "$wrong_owner" != "0" ]]; then
    echo "Found ${wrong_owner} application table(s) not owned by ${DB_USER}" >&2
    missing=$((missing + 1))
else
    echo "OK: all application tables are owned by ${DB_USER}"
fi

sequence_count="$(run_psql -t -A -c "
SELECT count(*)
FROM pg_class AS class
JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
WHERE class.relkind = 'S' AND namespace.nspname = '${DB_SCHEMA}';
" | xargs)"
if [[ "$sequence_count" == "0" ]]; then
    echo "No application sequences found" >&2
    missing=$((missing + 1))
else
    echo "OK: ${sequence_count} application sequence(s)"
fi

public_migrations="$(run_psql -t -A -c "SELECT to_regclass('public.django_migrations') IS NOT NULL;" | xargs)"
if [[ "$public_migrations" == "t" ]]; then
    echo "WARNING: public.django_migrations also exists; review the target search path" >&2
fi

if [[ "$missing" -ne 0 ]]; then
    echo "Verification failed with ${missing} structural or ownership issue(s)" >&2
    exit 1
fi

echo "Service Index database verification completed successfully"
