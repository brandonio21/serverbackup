# serverbackup

a stupid-simple python script to backup brandonio21 server data.

0. create a new directory under /var/backups
1. dump databases
2. cp /home, /var, /etc, /srv/http
3. tar it all up
4. create metadata file

This backup script is run everyday using a systemd service/timer.

TODO:
* cleanup backups on run. should have backups for the last 14 days (config file)
* cleanup partial backups (backups that do not have METADATA file)
* add logging
* create 'latest' symlink
* don't create new backups if nothing has changed. maybe dump dbs to disk and use rsync to manage this?
