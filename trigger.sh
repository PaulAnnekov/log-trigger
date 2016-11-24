#!/bin/bash
log=/var/log/journald.log
match="\"PRIORITY\" : \"3\""
host=exim
port=25
sender=journald@sr-server.home.annekov.com
to=paul.annekov@gmail.com
tail -f $log |
grep --line-buffered "$match" |
while read line
do
    echo "$line" | mailx -S smtp=$host:$port -s "Error on sr-server" -v -r $sender $to
done
