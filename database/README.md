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
- Restore loads data with the application credentials. Target preparation uses
  the database owner through libpq password lookup, normally
  /home/software/.pgpass with mode 0600.
- Passwords must never appear in commands or logs.

## Retrieve serviceindex1 and restore it to serviceindex2

Run from the active release as the software operating-system user:

~~~bash
sudo -iu software
cd /soft/serviceindex-1.0/PROD
~~~

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

Inspect the artifact offline first:

~~~bash
./database/pg_restore_serviceindex.sh \
  --input "$DUMP" \
  --inspect
~~~

Inspection validates the local artifact, identifies its format, and prints its
SHA-256 digest without connecting to PostgreSQL. Confirm source serviceindex1,
target serviceindex2, schema serviceindex_django, and the expected digest and format.

Next, run the live read-only preflight against serviceindex2:

~~~bash
./database/pg_restore_serviceindex.sh \
  --input "$DUMP" \
  --dry-run
~~~

Dry run authenticates both database roles and checks target ownership, active
connections, schema ownership, and required privileges. It performs no GRANT,
DROP, or restore command.

Before a real restore, an authorized operator must:

1. Confirm serviceindex2 is the intended non-production target.
2. Confirm the maintenance role owns serviceindex2.
3. Confirm the software user's libpq password file covers that role and target.
4. Stop the application using serviceindex2 and disconnect other clients.
5. Back up serviceindex2 first if its current contents may be needed.

Stopping or restarting an application is not performed by these scripts.

Restore and automatically verify:

~~~bash
./database/pg_restore_serviceindex.sh \
  --input "$DUMP" \
  --execute \
  --confirm-target serviceindex2
~~~

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
Custom-format restoration uses pg_restore clean mode. Database ownership,
encoding, database-level grants, and unrelated schemas are preserved.

Plain-SQL and custom-format restore failures roll back the schema replacement
transaction. Connection loss at transaction commit leaves the final database
state uncertain, so verify before retrying.

If the process is forcibly killed after granting serviceindex_django temporary
CREATE permission on serviceindex2, its EXIT cleanup cannot run. An authorized
operator must inspect the database privilege and revoke it if it was temporary.

Migration execution is not part of restoration. Review migration state against
the deployed application and obtain separate authorization before applying one.

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
