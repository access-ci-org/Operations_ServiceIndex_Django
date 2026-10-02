#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INPUT=""
POSTGRES_BIN="${POSTGRES_BIN:-}"
LOCAL_PG_PORT="${LOCAL_PG_PORT:-55432}"
TEST_ROOT=""

usage() {
    cat <<EOF
Usage: ./database/tests/test_restore_integration.sh --input FILE [options]

Restore a dump into a disposable, Unix-socket-only PostgreSQL cluster and test:
  - offline artifact inspection
  - live dry-run without mutation
  - successful target-confirmed restore and verification
  - transaction rollback after an intentional restore failure

Options:
  --input FILE          Dump to test (required)
  --postgres-bin DIR    Directory containing PostgreSQL server/client tools
  --port NUMBER         Local Unix socket port label (default: 55432)
  --help                Show this help

The temporary cluster is removed on exit. No network listener is started.
EOF
}

cleanup() {
    local exit_code=$?
    local log_file
    trap - EXIT INT TERM

    if [[ -n "$TEST_ROOT" && -d "$TEST_ROOT" ]]; then
        case "$(basename "$TEST_ROOT")" in
            serviceindex-restore-test.*) ;;
            *)
                echo "Refusing to clean unexpected test directory: ${TEST_ROOT}" >&2
                exit 1
                ;;
        esac
        if [[ "$exit_code" -ne 0 ]]; then
            echo "Integration test failed; operational log tails follow:" >&2
            for log_file in initdb.log postgres.log inspect.log dry-run.log restore.log failure.log; do
                if [[ -s "$TEST_ROOT/$log_file" ]]; then
                    echo "--- ${log_file} ---" >&2
                    tail -n 20 "$TEST_ROOT/$log_file" >&2
                fi
            done
        fi
        if [[ -n "$POSTGRES_BIN" ]] && "$POSTGRES_BIN/pg_ctl" \
            -D "$TEST_ROOT/data" status >/dev/null 2>&1; then
            "$POSTGRES_BIN/pg_ctl" -D "$TEST_ROOT/data" stop -m fast >/dev/null
        fi
        rm -rf -- "$TEST_ROOT"
    fi
    exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input)
            [[ $# -ge 2 ]] || { echo "--input requires a value" >&2; exit 1; }
            INPUT="$2"
            shift 2
            ;;
        --postgres-bin)
            [[ $# -ge 2 ]] || { echo "--postgres-bin requires a value" >&2; exit 1; }
            POSTGRES_BIN="$2"
            shift 2
            ;;
        --port)
            [[ $# -ge 2 ]] || { echo "--port requires a value" >&2; exit 1; }
            LOCAL_PG_PORT="$2"
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

if [[ -z "$INPUT" || ! -r "$INPUT" || ! -s "$INPUT" ]]; then
    echo "--input must name a readable, nonempty dump" >&2
    exit 1
fi
if [[ ! "$LOCAL_PG_PORT" =~ ^[0-9]+$ ]] || ((LOCAL_PG_PORT < 1024 || LOCAL_PG_PORT > 65535)); then
    echo "Invalid --port: ${LOCAL_PG_PORT}" >&2
    exit 1
fi
if [[ -z "$POSTGRES_BIN" ]]; then
    POSTGRES_BIN="$(dirname "$(command -v postgres || true)")"
fi
for command_name in initdb postgres pg_ctl pg_isready psql createdb; do
    if [[ ! -x "$POSTGRES_BIN/$command_name" ]]; then
        echo "PostgreSQL tool is unavailable: ${POSTGRES_BIN}/${command_name}" >&2
        echo "Supply --postgres-bin DIR (for example, /opt/homebrew/opt/postgresql@15/bin)." >&2
        exit 1
    fi
done

INPUT="$(cd "$(dirname "$INPUT")" && pwd -P)/$(basename "$INPUT")"
# PostgreSQL Unix socket paths have a small platform limit. macOS TMPDIR paths
# are long enough to exceed it, so keep this disposable cluster directly in /tmp.
TEST_ROOT="$(mktemp -d "/tmp/serviceindex-restore-test.XXXXXX")"
chmod 700 "$TEST_ROOT"
mkdir "$TEST_ROOT/socket"

echo "Initializing disposable PostgreSQL cluster"
"$POSTGRES_BIN/initdb" -D "$TEST_ROOT/data" --no-locale --encoding=UTF8 \
    --auth-local=trust --auth-host=reject >"$TEST_ROOT/initdb.log"
"$POSTGRES_BIN/pg_ctl" -D "$TEST_ROOT/data" -l "$TEST_ROOT/postgres.log" \
    -o "-F -k $TEST_ROOT/socket -p $LOCAL_PG_PORT -h ''" start >/dev/null
"$POSTGRES_BIN/pg_isready" -h "$TEST_ROOT/socket" -p "$LOCAL_PG_PORT" \
    -d postgres >/dev/null

"$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" -p "$LOCAL_PG_PORT" \
    -d postgres -v ON_ERROR_STOP=1 -c 'CREATE ROLE serviceindex_owner LOGIN;' >/dev/null
"$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" -p "$LOCAL_PG_PORT" \
    -d postgres -v ON_ERROR_STOP=1 -c 'CREATE ROLE serviceindex_django LOGIN;' >/dev/null
"$POSTGRES_BIN/createdb" -h "$TEST_ROOT/socket" -p "$LOCAL_PG_PORT" \
    -O serviceindex_owner serviceindex2
"$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" -p "$LOCAL_PG_PORT" \
    -d serviceindex2 -v ON_ERROR_STOP=1 \
    -c 'CREATE SCHEMA serviceindex_django AUTHORIZATION serviceindex_django; CREATE SCHEMA safety_sentinel AUTHORIZATION serviceindex_owner;' >/dev/null
"$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" -p "$LOCAL_PG_PORT" \
    -U serviceindex_owner -d serviceindex2 -v ON_ERROR_STOP=1 \
    -c 'CREATE TABLE safety_sentinel.marker (id integer); INSERT INTO safety_sentinel.marker VALUES (1);' >/dev/null
"$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" -p "$LOCAL_PG_PORT" \
    -U serviceindex_django -d serviceindex2 -v ON_ERROR_STOP=1 \
    -c 'CREATE TABLE serviceindex_django.pre_restore_marker (id integer); INSERT INTO serviceindex_django.pre_restore_marker VALUES (1);' >/dev/null

export PATH="$POSTGRES_BIN:$PATH"
export APP_CONFIG=/nonexistent/serviceindex-integration-test.conf
export DB_HOSTNAME_WRITE="$TEST_ROOT/socket"
export DB_HOSTNAME_READ="$TEST_ROOT/socket"
export DB_PORT="$LOCAL_PG_PORT"
export DB_OWNER=serviceindex_owner
export DB_MAINTENANCE_USER=serviceindex_owner
export DJANGO_USER=serviceindex_django
export DJANGO_PASS=
export DB_SCHEMA=serviceindex_django

RESTORE_SCRIPT="$ROOT_DIR/database/pg_restore_serviceindex.sh"
"$RESTORE_SCRIPT" --input "$INPUT" --target-db serviceindex2 --inspect \
    >"$TEST_ROOT/inspect.log"
"$RESTORE_SCRIPT" --input "$INPUT" --target-db serviceindex2 --dry-run \
    >"$TEST_ROOT/dry-run.log"

application_marker="$("$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" \
    -p "$LOCAL_PG_PORT" -U serviceindex_django -d serviceindex2 -t -A \
    -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM serviceindex_django.pre_restore_marker;')"
unrelated_marker="$("$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" \
    -p "$LOCAL_PG_PORT" -U serviceindex_owner -d serviceindex2 -t -A \
    -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM safety_sentinel.marker;')"
[[ "$application_marker" == "1" && "$unrelated_marker" == "1" ]] || {
    echo "Dry run changed the disposable target" >&2
    exit 1
}
echo "PASS: dry run left both sentinels unchanged"

"$RESTORE_SCRIPT" --input "$INPUT" --target-db serviceindex2 \
    --execute --confirm-target serviceindex2 >"$TEST_ROOT/restore.log"

post_restore="$("$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" \
    -p "$LOCAL_PG_PORT" -d serviceindex2 -t -A -v ON_ERROR_STOP=1 -c \
    "SELECT (SELECT count(*) FROM safety_sentinel.marker), (to_regclass('serviceindex_django.pre_restore_marker') IS NULL), (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'serviceindex_django' AND table_type = 'BASE TABLE'), pg_get_userbyid((SELECT nspowner FROM pg_namespace WHERE nspname = 'serviceindex_django')), has_database_privilege('serviceindex_django', current_database(), 'CREATE');")"
IFS='|' read -r unrelated_count old_marker_absent table_count schema_owner create_privilege <<<"$post_restore"
[[ "$unrelated_count" == "1" && "$old_marker_absent" == "t" ]] || {
    echo "Successful restore crossed its intended schema boundary" >&2
    exit 1
}
[[ "$table_count" -gt 0 && "$schema_owner" == "serviceindex_django" && "$create_privilege" == "f" ]] || {
    echo "Successful restore failed structural or privilege checks" >&2
    exit 1
}
echo "PASS: restore loaded ${table_count} application tables and preserved the unrelated schema"

cat >"$TEST_ROOT/intentional_failure.sql" <<'SQL'
CREATE SCHEMA serviceindex_django;
CREATE TABLE serviceindex_django.rollback_probe (id integer);
SELECT serviceindex_intentional_missing_function();
SQL
chmod 600 "$TEST_ROOT/intentional_failure.sql"
set +e
"$RESTORE_SCRIPT" --input "$TEST_ROOT/intentional_failure.sql" \
    --target-db serviceindex2 --no-verify --execute --confirm-target serviceindex2 \
    >"$TEST_ROOT/failure.log" 2>&1
failure_status=$?
set -e
[[ "$failure_status" -ne 0 ]] || {
    echo "Intentional restore failure unexpectedly succeeded" >&2
    exit 1
}

post_failure="$("$POSTGRES_BIN/psql" -X -h "$TEST_ROOT/socket" \
    -p "$LOCAL_PG_PORT" -d serviceindex2 -t -A -v ON_ERROR_STOP=1 -c \
    "SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'serviceindex_django' AND table_type = 'BASE TABLE'), (to_regclass('serviceindex_django.rollback_probe') IS NULL), (SELECT count(*) FROM safety_sentinel.marker), has_database_privilege('serviceindex_django', current_database(), 'CREATE');")"
IFS='|' read -r tables_after_failure probe_absent unrelated_after_failure privilege_after_failure <<<"$post_failure"
[[ "$tables_after_failure" == "$table_count" && "$probe_absent" == "t" && \
    "$unrelated_after_failure" == "1" && "$privilege_after_failure" == "f" ]] || {
    echo "Failed restore did not roll back cleanly" >&2
    exit 1
}
echo "PASS: failed restore rolled back and temporary privilege was revoked"
echo "Disposable restore integration test completed successfully"
