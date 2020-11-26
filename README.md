# serverbackup
A personal script which I use to backup my servers. Limited to directories and
mysql databases. Of course, as I use more software on my servers, the list of
supported things will grow.

## philosophy
I created this script because:
* my servers need backups of important directories and databases. I've used off-the-shelf
backup solutions before, but I forget about them and forget how to configure them. I'm
hoping that a solution that I create will be more maintainable and easier to remember.
* I don't have much stuff, so I don't put any effort into "optimized stuff": deduping,
multiprocessing, etc.
* All my servers are "in the cloud" and I don't want to keep a computer on 24/7
in my house.
* "object stores" (like s3) are cheaper than full-on VPS, so I push to an s3-like
instead of another host.

## implementation
a stupid-simple python script to backup brandonio21 server data.

0. create a new targz under /var/backups
1. dump databases
2. dump directories from config
3. dump some METADATA
4. tar it all up
5. encrypt
6. upload to s3

## how to install/configure
1. Create a configuration file at /etc/serverbackup.conf using the below template:
(I've included comments that you have to remove since this is JSON)
```
{
  # this name will be encoded in the backup file
  "name": "site_name",
  # (optional) tuples of (database, username, password) to dump with 'mysqldump'
  "databases": [
    ["database", "user", "password"]
  ],
  # (optional) list of directories (recursive) to dump
  "directories": ["/etc", "/home", "/srv/http"],
  # (optional) if uploading to s3, path to s3cfg file
  "s3config": "path/to/.s3cfg",
  # (optional) if uploading to s3, name of s3 bucket
  "s3bucket": "my-s3-bucket",
  # (optional) symmetric password to encryt before uploading to s3
  "encryption_password": "password",
  # (optional) number of days to keep backups. 0 is "keep all backups"
  "retention_days": 30
}
```
2. Install pre-requisites
* Requires python>=3.6
* If you want to upload to s3, install 's3cmd' and create a configuration file using s3cmd --configure
* If you want to encrypt, install 'gpg'
* If you want to dump databases, install 'mysqldump'

3. If you want to use systemd to run this regularly, 
```
cp serverbackup.service /etc/systemd/system/
cp serverbackup.timer /etc/systemd/system
systemctl enable serverbackup.timer
```

4. Create a backup on demand.
If using systemd, `systemctl start serverbackup.service`
Otherwise, `python3 serverbackup.py`
