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

DEFAULT_BACKUP_ROOT = "/var/backups"
CONFIG_FILE = "/etc/serverbackup.conf"

# configure logs
logger = logging.getLogger("serverbackup")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

def delete_local_copies_beyond_max(backup_dir, max_local_copies):
    backups_to_delete = set()
    assert max_local_copies > 0, "max_local_copies must be greater than 0"
    logger.debug(f"Cleaning up old local backups in {backup_dir}")
    backup_paths_with_age = [] # list of tuples (days old, backup path)
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
            except (KeyError, OSError, EOFError, zlib.error):
                logger.warning(f"Backup {backup_file} corrupt - marking for deletion")
                backups_to_delete.add(backup_path)
                continue

            # we use '23 hours' as a day instead of 24 so that if retention_days
            # is set to '1' and this script runs daily, the old backups are
            # guaranteed to be cleared.
            days_old = int((time.time() - backup_timestamp) / (60 * 60 * 23))
            backup_paths_with_age.append((days_old, backup_path))

    backup_paths_sorted_by_age = [
        backup_path
        for (backup_age, backup_path) in sorted(backup_paths_with_age)
    ]
    backup_paths_within_max_copies = backup_paths_sorted_by_age[:max_local_copies]
    backup_paths_beyond_max_copies = backup_paths_sorted_by_age[max_local_copies:]

    logger.debug(
        f"Found {len(backup_paths_sorted_by_age)} local backups. "
        f"Keeping {len(backup_paths_within_max_copies)}, "
        f"marking {len(backup_paths_beyond_max_copies)} for deletion."
    )
    backups_to_delete.update(backup_paths_beyond_max_copies)

    for backup_to_delete in backups_to_delete:
        logger.debug(f"Deleting backup {backup_to_delete}")
        os.remove(backup_to_delete)
        encrypted_backup = f"{backup_to_delete}.gpg"
        if os.path.isfile(encrypted_backup):
            logger.debug(f"Deleting encrypted backup {encrypted_backup}")
            os.remove(encrypted_backup)



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
    max_local_copies = config.get("max_local_copies")
    encryption_password = config.get("encryption_password")
    keep_encrypted_backup_after_upload = config.get("keep_encrypted_backup_after_upload", False)
    backup_root = config.get("backup_root", DEFAULT_BACKUP_ROOT)
    include_timestamp_in_filename = config.get("include_timestamp_in_filename", True)

    # config validation
    if not include_timestamp_in_filename and max_local_copies > 1:
        raise ValueError("Timestamp may only be toggled off if max_local_copies is 1")

    backup_dir = f"{backup_root}/{name}"
    os.makedirs(backup_dir, exist_ok=True)


    # clean up old backups
    # This flow is DEPRECATED. No new development should be done on this
    # flow. Instead, users should prefer max_local_copies.
    # For backwards incompatibility, the max_local_copies flow is not invoked
    # unless retention_days is absent.
    if retention_days is not None:
        backups_to_delete = set()
        logger.warning("retention_days is DEPRECATED. Please switch to max_local_copies")

        assert retention_days > 0, "retention_days must be greater than 0"
        logger.debug(f"Cleaning up old backups in {backup_dir}")
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
                except (KeyError, OSError, EOFError, zlib.error):
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


    elif max_local_copies is not None:
        delete_local_copies_beyond_max(backup_dir, max_local_copies)

    # start backup process
    timestamp = int(time.time())
    timestamp_str = f"-{timestamp}" if include_timestamp_in_filename else ""
    backup_path = f"{backup_dir}/serverbackup-{name}{timestamp_str}.tar.gz"
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

    # Since we guarantee "at most max local copies", we need to perform
    # one more check after backup - if we've gone above the max, we probably
    # need to perform another deletion.
    if retention_days is None and max_local_copies is not None:
        delete_local_copies_beyond_max(backup_dir, max_local_copies)


if __name__ == "__main__":
    sys.exit(main())
