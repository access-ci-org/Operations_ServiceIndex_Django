#!/usr/bin/env bash
set -euo pipefail

umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUMP_DIR="${ROOT_DIR}/database/dump"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TEMP_OUTPUT=""

cleanup() {
    if [[ -n "$TEMP_OUTPUT" && -f "$TEMP_OUTPUT" ]]; then
        rm -f -- "$TEMP_OUTPUT"
    fi
}
trap cleanup EXIT

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

DB_NAME="${DB_DATABASE:-$(load_config_value DB_DATABASE)}"
DB_NAME="${DB_NAME:-serviceindex1}"
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
FORMAT="custom"
OUTPUT=""
DRY_RUN=0

usage() {
    cat <<EOF
Usage: ./database/pg_dump_serviceindex.sh [options]

Create a manual, schema-complete Service Index database dump.

Options:
  --source-db NAME  Source database (default: ${DB_NAME})
  --schema NAME     Application schema (default: ${DB_SCHEMA})
  --format TYPE     custom or sql (default: custom)
  --output PATH     Explicit output path
  --dry-run         Print the resolved pg_dump command without connecting
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
        --source-db)
            [[ $# -ge 2 ]] || { echo "--source-db requires a value" >&2; exit 1; }
            DB_NAME="$2"
            shift 2
            ;;
        --schema)
            [[ $# -ge 2 ]] || { echo "--schema requires a value" >&2; exit 1; }
            DB_SCHEMA="$2"
            shift 2
            ;;
        --format)
            [[ $# -ge 2 ]] || { echo "--format requires a value" >&2; exit 1; }
            FORMAT="$2"
            shift 2
            ;;
        --output)
            [[ $# -ge 2 ]] || { echo "--output requires a value" >&2; exit 1; }
            OUTPUT="$2"
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

validate_identifier "$DB_NAME" "source database"
validate_identifier "$DB_USER" "database user"
validate_identifier "$DB_SCHEMA" "schema"

if [[ "$FORMAT" != "custom" && "$FORMAT" != "sql" ]]; then
    echo "Unsupported format: $FORMAT" >&2
    exit 1
fi

if [[ -z "$OUTPUT" ]]; then
    if [[ "$FORMAT" == "custom" ]]; then
        OUTPUT="${DUMP_DIR}/${DB_NAME}_full_${TIMESTAMP}.dump"
    else
        OUTPUT="${DUMP_DIR}/${DB_NAME}_full_${TIMESTAMP}.sql"
    fi
fi

OUTPUT_DIR="$(dirname "$OUTPUT")"
CMD=(
    pg_dump
    -h "$DB_HOST"
    -p "$DB_PORT"
    -U "$DB_USER"
    -d "$DB_NAME"
    --schema "$DB_SCHEMA"
    --no-owner
    --no-privileges
    --verbose
)

if [[ "$FORMAT" == "custom" ]]; then
    CMD+=(--format=custom)
else
    CMD+=(--format=plain --clean --if-exists)
fi

echo "Preparing Service Index dump"
echo "  database: ${DB_NAME}"
echo "  schema:   ${DB_SCHEMA}"
echo "  user:     ${DB_USER}"
echo "  host:     ${DB_HOST}:${DB_PORT}"
echo "  format:   ${FORMAT}"
echo "  output:   ${OUTPUT}"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry run only. Command:"
    printf '  %q' "${CMD[@]}" --file="$OUTPUT"
    printf '\n'
    exit 0
fi

if [[ -e "$OUTPUT" ]]; then
    echo "Refusing to overwrite existing output: $OUTPUT" >&2
    exit 1
fi

mkdir -p -- "$OUTPUT_DIR"
TEMP_OUTPUT="$(mktemp "${OUTPUT}.tmp.XXXXXX")"

if [[ -n "$DB_SSLMODE" ]]; then
    export PGSSLMODE="$DB_SSLMODE"
fi
if [[ -n "$DB_SSLROOTCERT" ]]; then
    export PGSSLROOTCERT="$DB_SSLROOTCERT"
fi

if [[ -n "$DB_PASS" ]]; then
    PGPASSWORD="$DB_PASS" "${CMD[@]}" --file="$TEMP_OUTPUT"
else
    env -u PGPASSWORD "${CMD[@]}" --file="$TEMP_OUTPUT"
fi

if [[ ! -s "$TEMP_OUTPUT" ]]; then
    echo "Dump failed validation: output is empty" >&2
    exit 1
fi

if [[ "$FORMAT" == "custom" ]]; then
    pg_restore --list "$TEMP_OUTPUT" >/dev/null
else
    if ! LC_ALL=C grep -Eiq "^[[:space:]]*CREATE[[:space:]]+SCHEMA[[:space:]]+\"?${DB_SCHEMA}\"?([[:space:]]|;)" "$TEMP_OUTPUT"; then
        echo "Dump failed validation: expected schema creation was not found" >&2
        exit 1
    fi
fi

mv -- "$TEMP_OUTPUT" "$OUTPUT"
TEMP_OUTPUT=""
echo "Dump complete and validated: ${OUTPUT}"
