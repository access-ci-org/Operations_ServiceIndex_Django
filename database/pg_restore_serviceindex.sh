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

SOURCE_DB="${RESTORE_SOURCE_DB:-serviceindex1}"
TARGET_DB="${RESTORE_TARGET_DB:-serviceindex2}"
PROTECTED_DB="serviceindex1"
INPUT=""
DB_USER="${DJANGO_USER:-$(load_config_value DJANGO_USER)}"
DB_USER="${DB_USER:-serviceindex_django}"
DB_PASS="${DJANGO_PASS:-$(load_config_value DJANGO_PASS)}"
DB_SCHEMA="${DB_SCHEMA:-$(load_config_value DB_SCHEMA)}"
DB_SCHEMA="${DB_SCHEMA:-$DB_USER}"
DB_OWNER="${DB_OWNER:-$(load_config_value DB_OWNER)}"
DB_OWNER="${DB_OWNER:-serviceindex_owner}"
MAINTENANCE_USER="${DB_MAINTENANCE_USER:-$DB_OWNER}"
DB_HOST="${DB_HOSTNAME_WRITE:-$(load_config_value DB_HOSTNAME_WRITE)}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-$(load_config_value DB_PORT)}"
DB_PORT="${DB_PORT:-5432}"
DB_SSLMODE="${DB_SSLMODE:-$(load_config_value DB_SSLMODE)}"
DB_SSLROOTCERT="${DB_SSLROOTCERT:-$(load_config_value DB_SSLROOTCERT)}"
INSPECT_ONLY=0
DRY_RUN=0
EXECUTE=0
CONFIRM_TARGET=""
VERIFY_AFTER=1
INPUT_FORMAT=""
ARTIFACT_SHA256=""
TEMP_LIST_FILE=""
CREATE_GRANT_ADDED=0
SCHEMA_OWNER=""
APPLICATION_CAN_CREATE=""

usage() {
    cat <<EOF
Usage: ./database/pg_restore_serviceindex.sh --input FILE [options]

Replace the Service Index application schema in an explicit existing target database.

Required:
  --input FILE              Plain SQL or PostgreSQL custom-format dump

Options:
  --source-db NAME          Database represented by the dump (default: serviceindex1)
  --target-db NAME          Existing target database (default: serviceindex2)
  --schema NAME             Application schema (default: serviceindex_django)
  --maintenance-user NAME   Existing target database owner (default: serviceindex_owner)
  --no-verify               Skip post-restore database verification
  --inspect                 Validate the artifact without connecting to PostgreSQL
  --dry-run                 Run artifact checks and live read-only target preflight
  --execute                 Perform the restore after repeating all preflight checks
  --confirm-target NAME     Required with --execute; must equal the resolved target
  --help                    Show this help

The script always refuses production database serviceindex1 and also refuses source
and target database names that match. It never creates, drops, or alters a database;
it replaces only the application schema in the target.
Exactly one of --inspect, --dry-run, or --execute is required.
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

cleanup() {
    local exit_code=$?
    local cleanup_failed=0
    trap - EXIT

    if [[ "$CREATE_GRANT_ADDED" -eq 1 ]]; then
        if ! run_maintenance psql -X -h "$DB_HOST" -p "$DB_PORT" \
            -U "$MAINTENANCE_USER" -d "$TARGET_DB" -w -v ON_ERROR_STOP=1 \
            -c "REVOKE CREATE ON DATABASE \"${TARGET_DB}\" FROM \"${DB_USER}\";"; then
            echo "WARNING: failed to revoke temporary CREATE privilege from ${DB_USER}" >&2
            cleanup_failed=1
        fi
    fi
    if [[ -n "$TEMP_LIST_FILE" && -f "$TEMP_LIST_FILE" ]]; then
        rm -f -- "$TEMP_LIST_FILE"
    fi
    if [[ "$exit_code" -eq 0 && "$cleanup_failed" -eq 1 ]]; then
        exit_code=1
    fi
    exit "$exit_code"
}
trap cleanup EXIT

run_maintenance() {
    env -u PGPASSWORD "$@"
}

run_application() {
    if [[ -n "$DB_PASS" ]]; then
        PGPASSWORD="$DB_PASS" "$@"
    else
        env -u PGPASSWORD "$@"
    fi
}

maintenance_query() {
    run_maintenance psql -X -h "$DB_HOST" -p "$DB_PORT" \
        -U "$MAINTENANCE_USER" -d "$TARGET_DB" -w \
        -v ON_ERROR_STOP=1 -t -A "$@"
}

detect_input_format() {
    local magic
    magic="$(LC_ALL=C head -c 5 "$INPUT")"
    if [[ "$magic" == "PGDMP" ]]; then
        printf 'custom\n'
    elif LC_ALL=C grep -Iq '' "$INPUT"; then
        printf 'sql\n'
    else
        echo "Unsupported or unrecognized dump format: $INPUT" >&2
        exit 1
    fi
}

validate_plain_sql() {
    if LC_ALL=C grep -Eiq '^[[:space:]]*\\(connect|c)([[:space:]]|$)' "$INPUT"; then
        echo "Refusing SQL containing a psql database connection command" >&2
        exit 1
    fi
    if LC_ALL=C grep -Eiq '^[[:space:]]*(CREATE|DROP|ALTER)[[:space:]]+DATABASE([[:space:]]|;)' "$INPUT"; then
        echo "Refusing SQL containing database-level DDL" >&2
        exit 1
    fi
    if LC_ALL=C grep -Eiq '^[[:space:]]*\\(copy|i|include|include_relative|ir|o|out|setenv|!|cd)([[:space:]]|$)' "$INPUT"; then
        echo "Refusing SQL containing a local-file, shell, or output psql command" >&2
        exit 1
    fi
    if ! LC_ALL=C grep -Eiq "^[[:space:]]*CREATE[[:space:]]+SCHEMA([[:space:]]+IF[[:space:]]+NOT[[:space:]]+EXISTS)?[[:space:]]+\"?${DB_SCHEMA}\"?([[:space:]]|;)" "$INPUT"; then
        echo "Plain SQL dump does not create expected schema '${DB_SCHEMA}'" >&2
        exit 1
    fi
    if LC_ALL=C grep -Ei '^[[:space:]]*(CREATE|DROP|ALTER)[[:space:]]+SCHEMA([[:space:]]|$)' "$INPUT" |
        LC_ALL=C grep -Eiv "\"${DB_SCHEMA}\"" |
        LC_ALL=C grep -Eiv "([[:space:]]|^)${DB_SCHEMA}([[:space:]]|;|$)" >/dev/null; then
        echo "Refusing SQL containing schema DDL outside '${DB_SCHEMA}'" >&2
        exit 1
    fi
}

validate_custom_archive() {
    TEMP_LIST_FILE="$(mktemp)"
    pg_restore --list "$INPUT" >"$TEMP_LIST_FILE"
    if ! awk -v schema="$DB_SCHEMA" 'index($0, " SCHEMA - " schema " ") { found=1 } END { exit !found }' "$TEMP_LIST_FILE"; then
        echo "Custom archive does not contain expected schema '${DB_SCHEMA}'" >&2
        exit 1
    fi
}

read_only_preflight() {
    local database_owner
    local role_exists
    local application_connection
    local active_connections

    database_owner="$(maintenance_query -c "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database();")"
    if [[ "$database_owner" != "$MAINTENANCE_USER" ]]; then
        echo "Maintenance role '${MAINTENANCE_USER}' does not own target '${TARGET_DB}'" >&2
        exit 1
    fi

    role_exists="$(maintenance_query -c "SELECT count(*) FROM pg_roles WHERE rolname = '${DB_USER}';")"
    if [[ "$role_exists" != "1" ]]; then
        echo "Application database role '${DB_USER}' does not exist" >&2
        exit 1
    fi

    application_connection="$(run_application psql -X -h "$DB_HOST" -p "$DB_PORT" \
        -U "$DB_USER" -d "$TARGET_DB" -w -v ON_ERROR_STOP=1 -t -A \
        -c "SELECT current_database();")"
    if [[ "$application_connection" != "$TARGET_DB" ]]; then
        echo "Application role could not authenticate to target '${TARGET_DB}'" >&2
        exit 1
    fi

    active_connections="$(maintenance_query -c "
SELECT count(*)
FROM pg_stat_activity
WHERE datname = current_database()
  AND backend_type = 'client backend'
  AND pid <> pg_backend_pid();
")"
    if [[ "$active_connections" != "0" ]]; then
        echo "Target '${TARGET_DB}' has ${active_connections} active client connection(s)" >&2
        echo "Stop its application and disconnect clients before retrying" >&2
        exit 1
    fi

    SCHEMA_OWNER="$(maintenance_query -c "
SELECT pg_get_userbyid(nspowner)
FROM pg_namespace
WHERE nspname = '${DB_SCHEMA}';
")"
    if [[ -n "$SCHEMA_OWNER" && "$SCHEMA_OWNER" != "$DB_USER" ]]; then
        echo "Schema '${DB_SCHEMA}' must be absent or owned by '${DB_USER}'" >&2
        echo "Current owner: ${SCHEMA_OWNER}" >&2
        exit 1
    fi

    APPLICATION_CAN_CREATE="$(maintenance_query -c "
SELECT CASE WHEN has_database_privilege('${DB_USER}', current_database(), 'CREATE')
            THEN 't' ELSE 'f' END;
")"
}

prepare_restore_privileges() {
    if [[ "$APPLICATION_CAN_CREATE" != "t" ]]; then
        maintenance_query -c "GRANT CREATE ON DATABASE \"${TARGET_DB}\" TO \"${DB_USER}\";" >/dev/null
        CREATE_GRANT_ADDED=1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input)
            [[ $# -ge 2 ]] || { echo "--input requires a value" >&2; exit 1; }
            INPUT="$2"
            shift 2
            ;;
        --source-db)
            [[ $# -ge 2 ]] || { echo "--source-db requires a value" >&2; exit 1; }
            SOURCE_DB="$2"
            shift 2
            ;;
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
        --maintenance-user)
            [[ $# -ge 2 ]] || { echo "--maintenance-user requires a value" >&2; exit 1; }
            MAINTENANCE_USER="$2"
            shift 2
            ;;
        --no-verify)
            VERIFY_AFTER=0
            shift
            ;;
        --inspect)
            INSPECT_ONLY=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --execute)
            EXECUTE=1
            shift
            ;;
        --confirm-target)
            [[ $# -ge 2 ]] || { echo "--confirm-target requires a value" >&2; exit 1; }
            CONFIRM_TARGET="$2"
            shift 2
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

MODE_COUNT=$((INSPECT_ONLY + DRY_RUN + EXECUTE))
if [[ "$MODE_COUNT" -ne 1 ]]; then
    echo "Exactly one of --inspect, --dry-run, or --execute is required" >&2
    exit 1
fi

if [[ -z "$INPUT" ]]; then
    usage >&2
    exit 1
fi
if [[ ! -r "$INPUT" || ! -s "$INPUT" ]]; then
    echo "Input file is missing, unreadable, or empty: $INPUT" >&2
    exit 1
fi

validate_identifier "$SOURCE_DB" "source database"
validate_identifier "$TARGET_DB" "target database"
validate_identifier "$DB_USER" "application database user"
validate_identifier "$DB_SCHEMA" "application schema"
validate_identifier "$MAINTENANCE_USER" "maintenance user"
if [[ -n "$CONFIRM_TARGET" ]]; then
    validate_identifier "$CONFIRM_TARGET" "confirmed target database"
fi

if [[ "$TARGET_DB" == "$SOURCE_DB" ]]; then
    echo "Refusing to restore into source database '${SOURCE_DB}'" >&2
    exit 1
fi
if [[ "$TARGET_DB" == "$PROTECTED_DB" ]]; then
    echo "Refusing to restore into protected production database '${PROTECTED_DB}'" >&2
    exit 1
fi
if [[ "$EXECUTE" -eq 1 && "$CONFIRM_TARGET" != "$TARGET_DB" ]]; then
    echo "--execute requires --confirm-target '${TARGET_DB}'" >&2
    exit 1
fi
if [[ "$EXECUTE" -ne 1 && -n "$CONFIRM_TARGET" ]]; then
    echo "--confirm-target is only valid with --execute" >&2
    exit 1
fi

INPUT_FORMAT="$(detect_input_format)"
if [[ "$INPUT_FORMAT" == "sql" ]]; then
    validate_plain_sql
else
    validate_custom_archive
fi

ARTIFACT_SHA256="$(python3 - "$INPUT" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as artifact:
    for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"

if [[ -n "$DB_SSLMODE" ]]; then
    export PGSSLMODE="$DB_SSLMODE"
fi
if [[ -n "$DB_SSLROOTCERT" ]]; then
    export PGSSLROOTCERT="$DB_SSLROOTCERT"
fi

echo "Preparing Service Index restore"
echo "  input:            ${INPUT}"
echo "  source database:  ${SOURCE_DB}"
echo "  target database:  ${TARGET_DB}"
echo "  schema:           ${DB_SCHEMA}"
echo "  format:           ${INPUT_FORMAT}"
echo "  sha256:           ${ARTIFACT_SHA256}"
echo "  host:             ${DB_HOST}:${DB_PORT}"
echo "  application user: ${DB_USER}"
echo "  maintenance user: ${MAINTENANCE_USER}"
echo "  verify afterward: ${VERIFY_AFTER}"

if [[ "$INSPECT_ONLY" -eq 1 ]]; then
    echo "Inspection passed. No PostgreSQL connection was made."
    exit 0
fi

read_only_preflight

echo "Live read-only preflight passed"
echo "  database owner:          ${MAINTENANCE_USER}"
echo "  current schema owner:    ${SCHEMA_OWNER:-<absent>}"
echo "  application can CREATE:  ${APPLICATION_CAN_CREATE}"
echo "  active client sessions:  0"
echo "Planned destructive scope:"
echo "  - drop only schema ${DB_SCHEMA} in ${TARGET_DB}"
echo "  - restore the validated artifact as ${DB_USER}"
echo "  - verify the restored schema unless --no-verify is supplied"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry run passed. No GRANT, DROP, or restore command was executed."
    exit 0
fi

prepare_restore_privileges

if [[ "$INPUT_FORMAT" == "custom" ]]; then
    RESTORE_CMD=(
        pg_restore
        -h "$DB_HOST"
        -p "$DB_PORT"
        -U "$DB_USER"
        -d "$TARGET_DB"
        --schema "$DB_SCHEMA"
        --no-owner
        --no-privileges
        --clean
        --if-exists
        --exit-on-error
        --single-transaction
        --verbose
        "$INPUT"
    )
else
    RESTORE_CMD=(
        psql
        -X
        -h "$DB_HOST"
        -p "$DB_PORT"
        -U "$DB_USER"
        -d "$TARGET_DB"
        -v ON_ERROR_STOP=1
        --single-transaction
        -c "DROP SCHEMA IF EXISTS \"${DB_SCHEMA}\" CASCADE;"
        -f "$INPUT"
    )
fi

run_application "${RESTORE_CMD[@]}"

echo "Restore complete into ${TARGET_DB}"

if [[ "$VERIFY_AFTER" -eq 1 ]]; then
    VERIFY_ARGS=(
        "${ROOT_DIR}/database/verify_db.sh"
        --target-db "$TARGET_DB"
        --schema "$DB_SCHEMA"
    )
    DB_HOSTNAME_READ="$DB_HOST" DB_PORT="$DB_PORT" DJANGO_USER="$DB_USER" \
        DJANGO_PASS="$DB_PASS" DB_SSLMODE="$DB_SSLMODE" DB_SSLROOTCERT="$DB_SSLROOTCERT" \
        "${VERIFY_ARGS[@]}"
fi
