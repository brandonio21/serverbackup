#!/usr/bin/env python3
import json
import hashlib
from io import BytesIO
import tarfile
import subprocess
import os
import sys
import time

DESCRIPTION = "backup wordpress db, /home, /etc, and /srv"
BACKUP_ROOT = "/var/backups"

# (database, user, password)
DATABASES = [
    ("wordpress", "wordpress", "wppass"),
]

DIRS_TO_BACKUP = [
    "/etc",
    "/home",
    "/srv/http",
]

def main() -> int:
    timestamp = int(time.time())
    backup_directory = f"{BACKUP_ROOT}/{timestamp}"
    os.mkdir(backup_directory)

    backup_path = f"{backup_directory}/backup.tar.gz"
    backup = tarfile.open(backup_path, mode="w:gz")

    # Step 1: Dump database and add it to the backup tar
    for database, user, password in DATABASES:
        dump_proc = subprocess.run(
            ["mysqldump", database, f"--user={user}", f"--password={password}"], stdout=subprocess.PIPE
        )
        dump = dump_proc.stdout
        tarinfo = tarfile.TarInfo(name=f"{database}.sql")
        tarinfo.size = len(dump)
        backup.addfile(tarinfo, BytesIO(dump))

    # Step 2: Add all files in DIRS_TO_BACKUP
    for dir_to_backup in DIRS_TO_BACKUP:
        backup.add(dir_to_backup, recursive=True)

    backup.close()

    # Step 3: Create a METADATA file
    with open(backup_path, "rb") as f:
        data = f.read()

    metadata = {}
    metadata["sha256"] = hashlib.sha256(data).hexdigest()
    metadata["len"] = len(data)
    metadata["timestamp"] = timestamp
    metadata["description"] = DESCRIPTION

    with open(f"{backup_directory}/METADATA", "w+") as f:
        f.write(json.dumps(metadata))

if __name__ == "__main__":
    sys.exit(main())
