#!/usr/bin/env python3
import json
from io import BytesIO
import tarfile
import subprocess
import os
import sys
import time

BACKUP_ROOT = "/var/backups"
CONFIG_FILE = "/etc/serverbackup.conf"


def main() -> int:
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    # required fields
    name = config["name"]
    # optional fields
    databases = config.get("databases") or []
    dirs_to_backup = config.get("directories") or []
    s3config = config.get("s3config")
    s3bucket = config.get("s3bucket")

    timestamp = int(time.time())
    backup_path = f"{BACKUP_ROOT}/serverbackup-{name}-{timestamp}.tar.gz"

    backup = tarfile.open(backup_path, mode="w:gz")

    # Step 1: Dump database and add it to the backup tar
    for database, user, password in databases:
        dump_proc = subprocess.run(
            ["mysqldump", database, f"--user={user}", f"--password={password}"],
            stdout=subprocess.PIPE,
        )
        dump = dump_proc.stdout
        tarinfo = tarfile.TarInfo(name=f"{database}.sql")
        tarinfo.size = len(dump)
        backup.addfile(tarinfo, BytesIO(dump))

    # Step 2: Add all files in DIRS_TO_BACKUP
    for dir_to_backup in dirs_to_backup:
        backup.add(dir_to_backup, recursive=True)

    # Step 3: Create a METADATA file
    metadata = {}
    metadata["timestamp"] = timestamp
    metadata_data = json.dumps(metadata).encode("utf-8")
    metadata_tarinfo = tarfile.TarInfo(name="METADATA")
    metadata_tarinfo.size = len(metadata_data)
    backup.addfile(metadata_tarinfo, BytesIO(metadata_data))

    backup.close()

    # Step 4: If config has data, upload to s3 using s3cmd
    if s3config and s3bucket:
        subprocess.run(
            ["s3cmd", "--config", s3config, "put", backup_path, f"s3://{s3bucket}"]
        )


if __name__ == "__main__":
    sys.exit(main())
