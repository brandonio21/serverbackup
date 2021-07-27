#!/usr/bin/env python3

from io import BytesIO
import zlib
import gzip
import json
import logging
import os
import re
import subprocess
import sys
import tarfile
import time

BACKUP_ROOT = "/var/backups"
CONFIG_FILE = "/etc/serverbackup.conf"

# configure logs
logger = logging.getLogger("serverbackup")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


def main() -> int:
    logger.debug("Parsing config file")
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    # required fields
    name = config["name"]
    # optional fields
    databases = config.get("databases") or []
    dirs_to_backup = config.get("directories") or []
    s3config = config.get("s3config")
    s3bucket = config.get("s3bucket")
    retention_days = config.get("retention_days")
    encryption_password = config.get("encryption_password")
    keep_encrypted_backup_after_upload = (
        config.get("keep_encrypted_backup_after_upload") or False
    )

    backup_dir = f"{BACKUP_ROOT}/{name}"
    os.makedirs(backup_dir, exist_ok=True)

    # clean up old backups
    if retention_days:
        logger.debug(f"Cleaning up old backups in {backup_dir}")
        backups_to_delete = set()
        backup_files = [
            f
            for f in os.listdir(backup_dir)
            if f.startswith("serverbackup-") and f.endswith(".tar.gz")
        ]
        for backup_file in backup_files:
            backup_path = os.path.join(backup_dir, backup_file)
            with tarfile.open(backup_path, mode="r:gz") as f:
                try:
                    metadata = json.loads(f.extractfile("METADATA").read())
                    backup_timestamp = metadata["timestamp"]
                except (KeyError, OSError, zlib.error):
                    logger.warning(
                        f"Backup {backup_file} corrupt - marking for deletion"
                    )
                    backups_to_delete.add(backup_path)
                    continue

                # we use '23 hours' as a day instead of 24 so that if retention_days
                # is set to '1' and this script runs daily, the old backups are
                # guaranteed to be cleared.
                days_old = int((time.time() - backup_timestamp) / (60 * 60 * 23))
                if days_old > retention_days:
                    logger.debug(
                        f"Backup {backup_file} is {days_old} days old - marking for deletion"
                    )
                    backups_to_delete.add(backup_path)

        for backup_to_delete in backups_to_delete:
            logger.debug(f"Deleting backup {backup_to_delete}")
            os.remove(backup_to_delete)
            encrypted_backup = f"{backup_to_delete}.gpg"
            if os.path.isfile(encrypted_backup):
                logger.debug(f"Deleting encrypted backup {encrypted_backup}")
                os.remove(encrypted_backup)

    # start backup process
    timestamp = int(time.time())
    backup_path = f"{backup_dir}/serverbackup-{name}-{timestamp}.tar.gz"
    logger.debug(f"Starting backup of {name} to {backup_path}")
    backup = tarfile.open(backup_path, mode="w:gz")
    # Step 1: Dump database and add it to the backup tar
    for database, user, password in databases:
        logger.debug(f"Dumping database {database}")
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
        logger.debug(f"Adding directory {dir_to_backup}")
        backup.add(dir_to_backup, recursive=True)

    # Step 3: Create a METADATA file
    logger.debug("Adding METADATA")
    metadata = {}
    metadata["timestamp"] = timestamp
    metadata_data = json.dumps(metadata).encode("utf-8")
    metadata_tarinfo = tarfile.TarInfo(name="METADATA")
    metadata_tarinfo.size = len(metadata_data)
    backup.addfile(metadata_tarinfo, BytesIO(metadata_data))

    backup.close()

    # Step 4: If config has data, upload to s3 using s3cmd
    if s3config and s3bucket:
        encrypted_path = None
        if encryption_password:
            logger.debug("Encrypting before uploading to s3")
            encrypted_path = f"{backup_path}.gpg"

            keypipe_r, keypipe_w = os.pipe()
            os.write(keypipe_w, f"{encryption_password}\n".encode())
            os.close(keypipe_w)

            subprocess.run(
                [
                    "gpg",
                    "--passphrase-fd",
                    str(keypipe_r),
                    "--quiet",
                    "--batch",
                    "--output",
                    encrypted_path,
                    "--symmetric",
                    backup_path,
                ],
                pass_fds=(keypipe_r,),
            )
            os.close(keypipe_r)

        logger.debug("Uploading to s3")
        subprocess.run(
            [
                "s3cmd",
                "--config",
                s3config,
                "put",
                encrypted_path or backup_path,
                f"s3://{s3bucket}",
            ]
        )

        logger.debug("Upload complete!")
        if encrypted_path and not keep_encrypted_backup_after_upload:
            logger.debug("Deleting encrypted backup")
            os.remove(encrypted_path)


if __name__ == "__main__":
    sys.exit(main())
