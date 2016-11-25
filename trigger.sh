#!/bin/bash
log=/var/log/journald.log
match="\"PRIORITY\" : \"3\""
email_host=exim
email_port=25
sender=journald@sr-server.home.annekov.com
to=paul.annekov@gmail.com
cat |
grep --line-buffered "$match" |
while read line
do
    container=`echo "$line" | jq --raw-output '.CONTAINER_NAME'`
    message=`echo "$line" | jq --raw-output '.MESSAGE'`
    hostname=`echo "$line" | jq --raw-output '._HOSTNAME'`
    echo -e "Error:\n$message" | mailx -S smtp=$email_host:$email_port -s "Error on $hostname in container $container" -v -r $sender $to
done
