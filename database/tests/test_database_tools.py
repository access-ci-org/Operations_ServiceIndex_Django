import gzip
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_DIR = REPO_ROOT / "database"


def load_retrieve_module():
    module_path = DATABASE_DIR / "serviceindex_db_retrieve.py"
    spec = importlib.util.spec_from_file_location("serviceindex_db_retrieve", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RetrieveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_retrieve_module()

    def test_classifies_plain_sql_and_custom_archive(self):
        self.assertEqual(self.module.classify_dump_header(b"PGDMP data"), "custom")
        self.assertEqual(
            self.module.classify_dump_header(b"-- PostgreSQL database dump\n"), "sql"
        )

    def test_extracts_source_database_from_current_object_name(self):
        key = "django.serviceindex1.dump.1790831401.gz"
        self.assertEqual(self.module.source_database_from_key(key), "serviceindex1")

    def test_restore_handoff_is_target_explicit_and_dry_run(self):
        command = self.module.build_restore_command(
            Path("database/dump/example.sql"), "serviceindex1", "serviceindex2"
        )
        self.assertIn("--source-db serviceindex1", command)
        self.assertIn("--target-db serviceindex2", command)
        self.assertTrue(command.endswith("--dry-run"))

    def test_retrieve_defaults_to_serviceindex1_and_serviceindex2(self):
        with patch.object(
            sys,
            "argv",
            ["serviceindex_db_retrieve.py", "-r", "--dry-run"],
        ):
            arguments = self.module.parse_args()
        self.assertEqual(arguments.pattern, "django.serviceindex1.dump")
        self.assertEqual(arguments.source_db, "serviceindex1")
        self.assertEqual(arguments.target_db, "serviceindex2")

    def test_decompresses_current_backup_naming_to_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = (
                Path(directory)
                / "django.serviceindex1.dump.1790831401.gz"
            )
            with gzip.open(archive, "wb") as compressed:
                compressed.write(b"-- PostgreSQL database dump\n")
            dump_path, dump_format = self.module.decompress_and_classify(archive)

            self.assertEqual(dump_format, "sql")
            self.assertEqual(
                dump_path.name,
                "django.serviceindex1.dump.1790831401.sql",
            )
            self.assertGreater(dump_path.stat().st_size, 0)


class ShellToolTests(unittest.TestCase):
    def environment(self):
        environment = os.environ.copy()
        environment.pop("APP_CONFIG", None)
        environment.update(
            {
                "DB_DATABASE": "serviceindex1",
                "DJANGO_USER": "serviceindex_django",
                "DJANGO_PASS": "",
                "DB_SCHEMA": "serviceindex_django",
                "DB_HOSTNAME_READ": "example.invalid",
                "DB_HOSTNAME_WRITE": "example.invalid",
                "DB_PORT": "5432",
                "DB_OWNER": "serviceindex_owner",
            }
        )
        return environment

    def run_tool(self, name, *arguments, environment=None):
        return subprocess.run(
            [str(DATABASE_DIR / name), *arguments],
            cwd=REPO_ROOT,
            env=environment or self.environment(),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_dump_dry_run_is_offline_and_schema_scoped(self):
        result = self.run_tool(
            "pg_dump_serviceindex.sh",
            "--source-db",
            "serviceindex1",
            "--schema",
            "serviceindex_django",
            "--output",
            "/tmp/serviceindex-test.dump",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("schema:   serviceindex_django", result.stdout)
        self.assertIn("--schema", result.stdout)
        self.assertIn("--file=/tmp/serviceindex-test.dump", result.stdout)

    def test_verify_dry_run_requires_explicit_target(self):
        missing = self.run_tool("verify_db.sh", "--dry-run")
        self.assertNotEqual(missing.returncode, 0)

        result = self.run_tool(
            "verify_db.sh", "--target-db", "serviceindex2", "--dry-run"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("target database: serviceindex2", result.stdout)

    def test_restore_dry_run_accepts_safe_schema_dump(self):
        sql = (
            "-- PostgreSQL database dump\n"
            "DROP SCHEMA IF EXISTS serviceindex_django CASCADE;\n"
            "CREATE SCHEMA serviceindex_django;\n"
            "CREATE TABLE serviceindex_django.django_migrations (id bigint);\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "serviceindex.sql"
            dump.write_text(sql, encoding="utf-8")
            result = self.run_tool(
                "pg_restore_serviceindex.sh",
                "--input",
                str(dump),
                "--dry-run",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("source database:  serviceindex1", result.stdout)
        self.assertIn("target database:  serviceindex2", result.stdout)
        self.assertIn("drop only schema serviceindex_django", result.stdout)

    def test_restore_refuses_source_as_target(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "serviceindex.sql"
            dump.write_text(
                "CREATE SCHEMA serviceindex_django;\n", encoding="utf-8"
            )
            result = self.run_tool(
                "pg_restore_serviceindex.sh",
                "--input",
                str(dump),
                "--source-db",
                "serviceindex1",
                "--target-db",
                "serviceindex1",
                "--dry-run",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to restore", result.stderr)

    def test_restore_rejects_plain_sql_reconnect(self):
        sql = (
            "\\connect serviceindex1\n"
            "CREATE SCHEMA serviceindex_django;\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "unsafe.sql"
            dump.write_text(sql, encoding="utf-8")
            result = self.run_tool(
                "pg_restore_serviceindex.sh",
                "--input",
                str(dump),
                "--source-db",
                "serviceindex1",
                "--target-db",
                "serviceindex2",
                "--dry-run",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("database connection command", result.stderr)

    def test_restore_rejects_plain_sql_local_include(self):
        sql = (
            "\\include /tmp/operator-file.sql\n"
            "CREATE SCHEMA serviceindex_django;\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "unsafe.sql"
            dump.write_text(sql, encoding="utf-8")
            result = self.run_tool(
                "pg_restore_serviceindex.sh",
                "--input",
                str(dump),
                "--source-db",
                "serviceindex1",
                "--target-db",
                "serviceindex2",
                "--dry-run",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local-file", result.stderr)

    def test_restore_rejects_other_schema_ddl(self):
        sql = (
            "CREATE SCHEMA serviceindex_django;\n"
            "DROP SCHEMA public CASCADE;\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "unsafe.sql"
            dump.write_text(sql, encoding="utf-8")
            result = self.run_tool(
                "pg_restore_serviceindex.sh",
                "--input",
                str(dump),
                "--source-db",
                "serviceindex1",
                "--target-db",
                "serviceindex2",
                "--dry-run",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema DDL outside", result.stderr)

    def test_dump_execution_with_stubbed_postgresql_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            bin_dir = temp_dir / "bin"
            bin_dir.mkdir()
            pg_dump = bin_dir / "pg_dump"
            pg_dump.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "for argument in \"$@\"; do\n"
                "  case \"$argument\" in --file=*) output=\"${argument#--file=}\" ;; esac\n"
                "done\n"
                "printf 'PGDMPstub' >\"$output\"\n",
                encoding="utf-8",
            )
            pg_restore = bin_dir / "pg_restore"
            pg_restore.write_text(
                "#!/usr/bin/env bash\n"
                "printf '1; 2615 1 SCHEMA - serviceindex_django serviceindex_django\\n'\n",
                encoding="utf-8",
            )
            pg_dump.chmod(0o755)
            pg_restore.chmod(0o755)
            output = temp_dir / "emergency.dump"
            environment = self.environment()
            environment["PATH"] = f"{bin_dir}:{environment['PATH']}"

            result = self.run_tool(
                "pg_dump_serviceindex.sh",
                "--source-db",
                "serviceindex1",
                "--output",
                str(output),
                environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), b"PGDMPstub")
            self.assertIn("Dump complete and validated", result.stdout)

    def test_restore_execution_with_stubbed_psql(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            bin_dir = temp_dir / "bin"
            bin_dir.mkdir()
            psql = bin_dir / "psql"
            psql.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "arguments=\"$*\"\n"
                "printf '%s\\n' \"$arguments\" >>\"${PSQL_LOG:?}\"\n"
                "case \"$arguments\" in\n"
                "  *'pg_get_userbyid(datdba)'*) printf 'serviceindex_owner\\n' ;;\n"
                "  *'FROM pg_roles'*) printf '1\\n' ;;\n"
                "  *'SELECT current_database();'*) printf 'serviceindex2\\n' ;;\n"
                "  *'FROM pg_stat_activity'*) printf '0\\n' ;;\n"
                "  *'pg_get_userbyid(nspowner)'*) printf 'serviceindex_django\\n' ;;\n"
                "  *'has_database_privilege'*) printf 't\\n' ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            psql.chmod(0o755)
            dump = temp_dir / "serviceindex.sql"
            dump.write_text(
                "DROP SCHEMA IF EXISTS serviceindex_django CASCADE;\n"
                "CREATE SCHEMA serviceindex_django;\n",
                encoding="utf-8",
            )
            environment = self.environment()
            environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
            psql_log = temp_dir / "psql.log"
            environment["PSQL_LOG"] = str(psql_log)

            result = self.run_tool(
                "pg_restore_serviceindex.sh",
                "--input",
                str(dump),
                "--source-db",
                "serviceindex1",
                "--target-db",
                "serviceindex2",
                "--no-verify",
                environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Restore complete into serviceindex2", result.stdout)
            self.assertIn(
                'DROP SCHEMA IF EXISTS "serviceindex_django" CASCADE;',
                psql_log.read_text(encoding="utf-8"),
            )

    def test_verify_execution_with_stubbed_psql(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            bin_dir = temp_dir / "bin"
            bin_dir.mkdir()
            psql = bin_dir / "psql"
            psql.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "arguments=\"$*\"\n"
                "case \"$arguments\" in\n"
                "  *'SELECT current_database();'*) printf 'serviceindex2\\n' ;;\n"
                "  *'FROM pg_namespace'*) printf '1\\n' ;;\n"
                "  *'information_schema.tables'*'table_name'*) printf '1\\n' ;;\n"
                "  *'information_schema.tables'*) printf '30\\n' ;;\n"
                "  *'FROM pg_tables'*) printf '0\\n' ;;\n"
                "  *\"class.relkind = 'S'\"*) printf '10\\n' ;;\n"
                "  *\"to_regclass('public.django_migrations')\"*) printf 'f\\n' ;;\n"
                "  *'SELECT count(*) FROM'*) printf '5\\n' ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            psql.chmod(0o755)
            environment = self.environment()
            environment["PATH"] = f"{bin_dir}:{environment['PATH']}"

            result = self.run_tool(
                "verify_db.sh",
                "--target-db",
                "serviceindex2",
                environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("verification completed successfully", result.stdout)


if __name__ == "__main__":
    unittest.main()
