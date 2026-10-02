#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "boto3",
# ]
# ///
"""List and retrieve Service Index PostgreSQL backups from S3.

Retrieval never runs a restore. After downloading and classifying an artifact,
the script prints a target-explicit restore command for an operator to review.
"""

from __future__ import annotations

import argparse
import gzip
import os
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DUMP_DIR = REPO_ROOT / "database" / "dump"
DEFAULT_BUCKET = "s3://backup.operations.access-ci.org"
DEFAULT_PREFIX = "service-index.operations.access-ci.org/rds.backup/"
DEFAULT_PROFILE = "newbackup"
DEFAULT_PATTERN = "django.serviceindex1.dump"
def parse_s3_url(value: str) -> tuple[str, str]:
    if not value.startswith("s3://"):
        raise ValueError("bucket must start with s3://")
    remainder = value[5:]
    bucket, separator, prefix = remainder.partition("/")
    if not bucket:
        raise ValueError("bucket name is empty")
    if separator and prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def source_database_from_key(key: str) -> str:
    match = re.search(
        r"(?:^|/)django\.([A-Za-z_][A-Za-z0-9_]*)\.dump(?:\.|$)", key
    )
    if not match:
        raise ValueError(f"cannot determine source database from backup key: {key}")
    return match.group(1)


def classify_dump_header(header: bytes) -> str:
    if header.startswith(b"PGDMP"):
        return "custom"
    if header and b"\x00" not in header:
        try:
            header.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            return "sql"
    raise ValueError("unsupported or unrecognized PostgreSQL dump format")


def detect_dump_format(path: Path) -> str:
    with path.open("rb") as dump_file:
        return classify_dump_header(dump_file.read(8192))


def load_boto3() -> tuple[Any, tuple[type[BaseException], ...], type[BaseException]]:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound
    except ImportError as exc:
        raise RuntimeError("boto3 is unavailable; run this script with 'uv run'") from exc
    return boto3, (BotoCoreError, ClientError), ProfileNotFound


def list_objects(
    bucket_url: str, prefix: str, profile: str
) -> list[tuple[str, Any]]:
    boto3, service_errors, profile_error = load_boto3()
    bucket, bucket_prefix = parse_s3_url(bucket_url)
    combined_prefix = f"{bucket_prefix}{prefix.lstrip('/')}"
    if combined_prefix and not combined_prefix.endswith("/"):
        combined_prefix += "/"

    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        client = session.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        objects: list[tuple[str, Any]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=combined_prefix):
            for item in page.get("Contents", []):
                full_key = item["Key"]
                relative = full_key[len(combined_prefix) :]
                if relative:
                    objects.append((relative, item["LastModified"]))
    except profile_error as exc:
        raise RuntimeError(f"AWS profile is unavailable: {profile}") from exc
    except service_errors as exc:
        raise RuntimeError(f"S3 listing failed: {exc}") from exc

    objects.sort(key=lambda item: item[1])
    return objects


def download_object(
    bucket_url: str, prefix: str, profile: str, key: str, destination: Path
) -> None:
    boto3, service_errors, profile_error = load_boto3()
    bucket, bucket_prefix = parse_s3_url(bucket_url)
    combined_prefix = f"{bucket_prefix}{prefix.lstrip('/')}"
    if combined_prefix and not combined_prefix.endswith("/"):
        combined_prefix += "/"
    full_key = f"{combined_prefix}{key}"

    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        session.client("s3").download_file(bucket, full_key, str(destination))
    except profile_error as exc:
        raise RuntimeError(f"AWS profile is unavailable: {profile}") from exc
    except service_errors as exc:
        raise RuntimeError(f"S3 download failed: {exc}") from exc


def decompress_and_classify(source: Path) -> tuple[Path, str]:
    with gzip.open(source, "rb") as compressed:
        dump_format = classify_dump_header(compressed.read(8192))

    suffix = ".dump" if dump_format == "custom" else ".sql"
    destination = source.with_suffix("").with_suffix(source.with_suffix("").suffix + suffix)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite decompressed dump: {destination}")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with gzip.open(source, "rb") as compressed:
                shutil.copyfileobj(compressed, temporary)
        os.link(temporary_path, destination)
        temporary_path.unlink()
        temporary_path = None
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    if destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("decompressed dump is empty")
    return destination, dump_format


def build_restore_command(
    dump_path: Path, source_database: str, target_database: str
) -> str:
    parts = [
        "./database/pg_restore_serviceindex.sh",
        "--input",
        str(dump_path),
        "--source-db",
        source_database,
        "--target-db",
        target_database,
        "--inspect",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List or retrieve Service Index PostgreSQL backups from S3"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("-l", "--list", action="store_true", help="list matching backups")
    mode.add_argument(
        "-r", "--retrieve", action="store_true", help="retrieve the newest match"
    )
    parser.add_argument(
        "pattern",
        nargs="?",
        default=DEFAULT_PATTERN,
        help=f"filename pattern (default: {DEFAULT_PATTERN})",
    )
    parser.add_argument(
        "--source-db",
        default="serviceindex1",
        help=(
            "database represented by legacy backup names that do not encode it "
            "(default: serviceindex1)"
        ),
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="AWS profile")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="S3 bucket URL")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="S3 key prefix")
    parser.add_argument(
        "--dump-dir", type=Path, default=DEFAULT_DUMP_DIR, help="download directory"
    )
    parser.add_argument(
        "--target-db",
        default="serviceindex2",
        help=(
            "target database included in the printed restore command "
            "(default: serviceindex2)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="select and display an object without downloading it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.list and not args.retrieve:
        args.list = True
    identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    if not identifier.fullmatch(args.source_db):
        print("ERROR: invalid --source-db identifier", file=sys.stderr)
        return 2
    if not identifier.fullmatch(args.target_db):
        print("ERROR: invalid --target-db identifier", file=sys.stderr)
        return 2

    try:
        objects = list_objects(args.bucket, args.prefix, args.profile)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    matching = [item for item in objects if args.pattern in item[0]]
    print(f"Found {len(matching)} matching backup(s)", file=sys.stderr)

    if args.list:
        for key, modified in matching:
            print(f"{key}  ({modified:%Y-%m-%d %H:%M %Z})")
        return 0
    if not matching:
        print("ERROR: no matching backups found", file=sys.stderr)
        return 1

    key, modified = matching[-1]
    try:
        source_database = source_database_from_key(key)
    except ValueError:
        source_database = args.source_db
    if source_database == args.target_db:
        print("ERROR: source and target database names match", file=sys.stderr)
        return 1

    destination = args.dump_dir / Path(key).name
    print(f"Selected: {key} ({modified:%Y-%m-%d %H:%M %Z})")
    print(f"Destination: {destination}")
    if args.dry_run:
        print("Dry run only; no file was downloaded.")
        return 0
    if destination.exists():
        print(f"ERROR: refusing to overwrite existing file: {destination}", file=sys.stderr)
        return 1

    args.dump_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=args.dump_dir, prefix=f".{destination.name}.", delete=False
    ) as temporary_file:
        temporary = Path(temporary_file.name)
    try:
        download_object(args.bucket, args.prefix, args.profile, key, temporary)
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise ValueError("downloaded object is empty")
        os.link(temporary, destination)
        temporary.unlink()
        if destination.suffix == ".gz":
            dump_path, dump_format = decompress_and_classify(destination)
        else:
            dump_path = destination
            dump_format = detect_dump_format(destination)
    except (OSError, RuntimeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        print(f"ERROR: retrieval failed: {exc}", file=sys.stderr)
        return 1

    print(f"Dump ready: {dump_path}")
    print(f"Format: {dump_format}")
    print("Next step (review this dry run before any real restore):")
    print(f"  {build_restore_command(dump_path, source_database, args.target_db)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
