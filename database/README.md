# Service Index database operator toolkit

These tools support manual backup retrieval, emergency live backup, restore, and
verification for the ACCESS Operations Service Index. They are not imported by
Django, run by the web service, scheduled, or invoked automatically.

Service Index has no media archive. Recovery uses only PostgreSQL backups.

## Database contract

| Item | Value |
| --- | --- |
| Production/source database | serviceindex1 |
| Non-production restore target | serviceindex2 |
| Application role and schema | serviceindex_django |
| Expected database owner | serviceindex_owner (verify before restoring) |
| Deployed configuration | /soft/serviceindex-1.0/conf/serviceindex.conf |
| S3 prefix | s3://backup.operations.access-ci.org/service-index.operations.access-ci.org/rds.backup/ |
| Production pattern | django.serviceindex1.dump.EPOCH.gz |

The normal workflow defaults to source serviceindex1 and target serviceindex2.
Both remain overridable for deliberate operator use, but serviceindex1 is always a
protected restore target and matching source/target names are also refused.

Never print or commit application configuration, PostgreSQL password files, AWS
credentials, or database dumps.

## Files

- serviceindex_db_retrieve.py lists and retrieves S3 artifacts. It never restores.
- pg_dump_serviceindex.sh creates and validates a manual live database dump.
- pg_restore_serviceindex.sh replaces the application schema in an explicit target.
- verify_db.sh verifies schema structure, key tables, ownership, and sequences.

Generated artifacts go under database/dump/, which is ignored by Git.

## Credentials

- S3 retrieval uses the selected AWS profile. Deployed hosts use newbackup.
- Dump and verification use application credentials from APP_CONFIG. A deployed
  release auto-discovers ../../conf/serviceindex.conf.
- Restore loads data as serviceindex_django with the application credentials.
  Target preparation authenticates directly as serviceindex_owner. The PostgreSQL
  commands use libpq, which automatically reads PGPASSFILE when set and otherwise
  reads $HOME/.pgpass. For the deployed software user this normally resolves to
  /home/software/.pgpass and must have mode 0600. “libpq password lookup” describes
  this automatic behavior; it is not a separate command. The current script does
  not authenticate as opsdba and then SET ROLE serviceindex_owner.
- Passwords must never appear in commands or logs.

## Retrieve serviceindex1 and restore it to serviceindex2

Follow these steps in order. A failed inspection, credential check, target backup,
or dry run is a stopping condition; do not skip forward to execute mode.

### 1. Enter the active release

Run from the active release as the software operating-system user:

~~~bash
sudo -iu software
cd /soft/serviceindex-1.0/PROD
~~~

The database helper scripts below automatically discover
`/soft/serviceindex-1.0/conf/serviceindex.conf`; they do not require an
`APP_CONFIG` export. Direct Django management commands do require the config.
Pass it for one command without leaving it exported in the shell:

~~~bash
APP_CONFIG=/soft/serviceindex-1.0/conf/serviceindex.conf \
  uv run python Operations_ServiceIndex_Django/manage.py shell
~~~

`manage.py shell` opens a Python console. Use `manage.py dbshell` for SQL against
the configured application database, normally serviceindex1 as
serviceindex_django. Continue to use direct `psql` with an explicit host,
database, and role for serviceindex_owner access to serviceindex2.

Other Django management commands use the same pattern. For example, inspect the
deployed application or preview its migration state without changing it:

~~~bash
APP_CONFIG=/soft/serviceindex-1.0/conf/serviceindex.conf \
  uv run python Operations_ServiceIndex_Django/manage.py check

APP_CONFIG=/soft/serviceindex-1.0/conf/serviceindex.conf \
  uv run python Operations_ServiceIndex_Django/manage.py showmigrations --plan
~~~

Commands such as `createsuperuser` write to the configured application database
and require explicit authorization:

~~~bash
APP_CONFIG=/soft/serviceindex-1.0/conf/serviceindex.conf \
  uv run python Operations_ServiceIndex_Django/manage.py createsuperuser
~~~

Do not generate or apply migrations as an ad hoc database-recovery step.
`makemigrations` changes application source, and `migrate` changes the database
schema; both require their normal review and deployment authorization.

Confirm that psql, pg_dump, and pg_restore are from the same supported, patched
PostgreSQL major release before handling an artifact:

~~~bash
psql --version
pg_dump --version
pg_restore --version
~~~

### 2. Select and retrieve the source backup

List recent production backups:

~~~bash
uv run database/serviceindex_db_retrieve.py -l
~~~

Preview selection of the newest backup. This reads the S3 listing but does not
download anything:

~~~bash
uv run database/serviceindex_db_retrieve.py -r --dry-run
~~~

Retrieve and classify it:

~~~bash
uv run database/serviceindex_db_retrieve.py -r
~~~

The script downloads into database/dump/, decompresses gzip artifacts, detects
plain SQL versus PostgreSQL custom format from their contents, and prints a
offline inspection command. Use the exact path printed as Dump ready:

~~~bash
DUMP="database/dump/django.serviceindex1.dump.EPOCH.sql"
~~~

The suffix may instead be .dump; use the path actually printed.

### 3. Inspect the source artifact offline

Inspect the artifact offline first:

~~~bash
./database/pg_restore_serviceindex.sh \
  --input "$DUMP" \
  --inspect
~~~

Inspection validates the local artifact, identifies its format, and prints its
SHA-256 digest without connecting to PostgreSQL. Confirm source serviceindex1,
target serviceindex2, schema serviceindex_django, and the expected digest and format.

Record the resolved dump path and SHA-256 digest in the operator notes for the
current run. Do not put a dump, password, or application configuration in Git.

### 4. Back up the current serviceindex2 schema

Preview a logical backup of the target before changing it:

~~~bash
./database/pg_dump_serviceindex.sh \
  --source-db serviceindex2 \
  --dry-run
~~~

Confirm database serviceindex2, schema serviceindex_django, and the expected RDS
host. Then create the backup:

~~~bash
./database/pg_dump_serviceindex.sh \
  --source-db serviceindex2
~~~

Do not continue unless the command ends with `Dump complete and validated`.
Record the exact output path and its digest:

~~~bash
sha256sum database/dump/serviceindex2_full_TIMESTAMP.dump
~~~

The default target backup is a PostgreSQL custom archive validated with
`pg_restore --list`. It is local only and is not an RDS snapshot or S3 upload.
The current custom-archive restore path uses `pg_restore --clean`, which drops
only objects represented in the archive; it does not guarantee removal of extra
target objects. Treat rollback from this artifact as a separate, reviewed
operation until full schema replacement for custom archives is implemented and
tested. Do not assume the forward synchronization command is a rollback command.

### 5. Verify target ownership and credentials

The two database roles have different responsibilities:

- serviceindex_django reads and writes application data, owns the application
  schema, and performs the actual load. Its password comes from APP_CONFIG.
- serviceindex_owner owns serviceindex2, performs the privileged preflight, and
  temporarily grants and revokes CREATE when necessary. Its password comes from
  the software user's libpq password file.

Check the password-file metadata without displaying any passwords:

~~~bash
stat -c '%U %G %a %n' "$HOME/.pgpass"
awk -F: 'NF >= 5 {print $1 ":" $2 ":" $3 ":" $4 ":<redacted>"}' \
  "$HOME/.pgpass"
~~~

The file must be owned by software with mode 0600. It must contain a matching
entry for the owner login; `PASSWORD` below is a placeholder and must never be
copied literally or placed in shell history:

~~~text
RDS_HOST:5432:serviceindex2:serviceindex_owner:PASSWORD
~~~

Test direct owner authentication without allowing an interactive fallback:

~~~bash
psql -X \
  -h RDS_HOST \
  -p 5432 \
  -U serviceindex_owner \
  -d serviceindex2 \
  -w \
  -Atc 'SELECT current_database(), current_user;'
~~~

The expected result is `serviceindex2|serviceindex_owner`. `no password supplied`
means no password-file entry matched. `password authentication failed` means an
entry matched but its credential was invalid or incorrectly escaped. In .pgpass,
escape a colon in the password as `\:` and a backslash as `\\`; do not quote the
password. Obtain or reset credentials only through an authorized process.

PostgreSQL may report that opsdba is a member of serviceindex_owner, but that does
not satisfy the current implementation. The script does not issue SET ROLE and
requires direct authentication as the database owner. Supporting opsdba plus role
assumption requires a separate code and test change.

### 6. Stop target users and run the live dry run

The application using serviceindex2 must be stopped and its other clients must be
disconnected through the authorized operational process before the dry run. The
preflight refuses any other active client connection. These scripts do not stop or
restart services.

Run the live read-only preflight against serviceindex2:

~~~bash
./database/pg_restore_serviceindex.sh \
  --input "$DUMP" \
  --dry-run
~~~

Dry run authenticates both database roles and checks target ownership, active
connections, schema ownership, and required privileges. It performs no GRANT,
DROP, or restore command.

Do not proceed unless it reports `Live read-only preflight passed` followed by
`Dry run passed`. Before execute mode, an authorized operator must confirm:

1. Confirm serviceindex2 is the intended non-production target.
2. Confirm the maintenance role owns serviceindex2.
3. Confirm the software user's libpq password file covers that role and target.
4. Stop the application using serviceindex2 and disconnect other clients.
5. Confirm the validated serviceindex2 backup path and digest were recorded.

### 7. Execute the synchronization

Restore and automatically verify:

~~~bash
./database/pg_restore_serviceindex.sh \
  --input "$DUMP" \
  --execute \
  --confirm-target serviceindex2
~~~

Do not substitute serviceindex1 in `--confirm-target`. Save the complete command
output with the operator record, excluding secrets.

The restore:

1. Unconditionally refuses serviceindex1 as a target and also refuses matching
   source and target names.
2. Rejects empty or unrecognized artifacts.
3. Requires a matching alphanumeric psql `\restrict`/`\unrestrict` envelope
   in plain SQL, permits backslashes only inside COPY data, and rejects every
   other psql meta-command.
4. Requires serviceindex_django in the artifact.
5. Requires an existing target owned by the maintenance role.
6. Refuses a target with other active client connections.
7. Requires the schema to be absent or owned by serviceindex_django.
8. Requires both --execute and an exact --confirm-target value.
9. Drops only serviceindex_django in the target transaction.
10. Restores as serviceindex_django.
11. Runs verify_db.sh unless --no-verify is supplied.

Do not manually empty or drop serviceindex2 first. Plain-SQL restoration drops
serviceindex_django inside the restore transaction before loading the dump.
Custom-format restoration uses pg_restore clean mode subject to the rollback
caveat in step 4. Database ownership, encoding, database-level grants, and
unrelated schemas are preserved.

Plain-SQL and custom-format restore failures roll back the schema replacement
transaction. Connection loss at transaction commit leaves the final database
state uncertain, so verify before retrying.

If the process is forcibly killed after granting serviceindex_django temporary
CREATE permission on serviceindex2, its EXIT cleanup cannot run. An authorized
operator must inspect the database privilege and revoke it if it was temporary.

Migration execution is not part of restoration. Review migration state against
the deployed application and obtain separate authorization before applying one.

### 8. Verify before returning the target to service

Successful execute mode runs verify_db.sh automatically. Run an explicit read-only
verification as well when recording the completed operation:

~~~bash
./database/verify_db.sh \
  --target-db serviceindex2
~~~

Review the structural checks and row counts. Do not restart or redirect an
application to serviceindex2 until verification passes and the authorized operator
has reviewed the result.

### Resume checklist

When pausing an operation, record these non-secret values outside the repository:

1. Active release path.
2. Retrieved source artifact path, format, and SHA-256 digest.
3. Validated serviceindex2 safety-backup path and SHA-256 digest.
4. Last completed numbered step and its exit status.
5. Whether the target application is running or stopped.
6. Any failed credential or connection check, without its password.

After resuming, repeat offline inspection, direct owner authentication, and the
live dry run even if they passed in an earlier shell session. Never reuse an old
shell variable without resetting it to the recorded artifact path.

## Local pre-host integration test

Before copying a release to a host, exercise a real artifact in a disposable local
PostgreSQL cluster. This test starts no network listener and deletes its temporary
cluster on exit:

~~~bash
./database/tests/test_restore_integration.sh \
  --input database/dump/django.serviceindex1.dump.EPOCH.sql \
  --postgres-bin /opt/homebrew/opt/postgresql@15/bin
~~~

The integration test runs offline inspection, proves the live dry run does not
change either schema, performs the confirmed restore and normal verification,
checks that an unrelated schema survives, and injects a restore error to prove
transaction rollback and temporary-privilege cleanup. It never connects to RDS,
S3, or a deployed application. The PostgreSQL major version should match the dump
source when practical.

## Emergency live backup

pg_dump_serviceindex.sh provides the manual “back up the live database now”
path. The default custom format is compressed internally by PostgreSQL and
validated with pg_restore --list.

Preview the resolved command:

~~~bash
./database/pg_dump_serviceindex.sh \
  --source-db serviceindex1 \
  --dry-run
~~~

Create a current local backup:

~~~bash
./database/pg_dump_serviceindex.sh \
  --source-db serviceindex1
~~~

Choose an explicit destination:

~~~bash
./database/pg_dump_serviceindex.sh \
  --source-db serviceindex1 \
  --output database/dump/serviceindex1-emergency.dump
~~~

This reads the live database and adds load, but does not modify it. The dump
contains sensitive data and must be protected. It is not uploaded automatically.

For a portable plain-SQL dump:

~~~bash
./database/pg_dump_serviceindex.sh \
  --source-db serviceindex1 \
  --format sql
~~~

## Verify a target explicitly

Preview:

~~~bash
./database/verify_db.sh \
  --target-db serviceindex2 \
  --dry-run
~~~

Run:

~~~bash
./database/verify_db.sh \
  --target-db serviceindex2
~~~

Verification displays structural metadata and row counts, never row contents.

## Safety boundaries

- No media workflow exists or is needed.
- Retrieval never restores.
- Dumping never uploads or applies retention.
- Restore never drops or creates a database.
- Restore never targets its declared source database.
- Restore never targets the protected production database serviceindex1, even if
  a different source name is supplied.
- No script schedules itself.
- No script runs migrations, starts or stops services, or deploys code.
- Production scheduling, S3 upload, retention, and monitoring remain
  infrastructure responsibilities.
