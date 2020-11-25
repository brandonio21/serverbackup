# serverbackup

a stupid-simple python script to backup brandonio21 server data.

0. create a new directory under /var/backups
1. dump databases
2. cp /home, /var, /etc, /srv/http
3. dump list of installed packages
4. create metadata file
5. tar it all up
6. delete folder
