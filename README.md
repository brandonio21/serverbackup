# serverbackup

a stupid-simple python script to backup brandonio21 server data.

0. create a new targz under /var/backups
1. dump databases
2. dump directories from config
3. dump some METADATA
4. tar it all up
5. upload to s3

configure at /etc/serverbackup.conf ; example:
```
{
  "name": "site_name",
  "databases": [
    ["database", "user", "password"]
  ],
  "directories": ["/etc", "/home", "/srv/http"],
  "s3config": "path/to/.s3cfg",
  "s3bucket": "my-s3-bucket",
  "retention_days": 30
}
```

This backup script is run everyday using a systemd service/timer.

TODO:
* cleanup partial backups (backups that do not have METADATA file)
* don't create new backups if nothing has changed. maybe dump dbs to disk and use rsync to manage this?
* allow multiple backups
