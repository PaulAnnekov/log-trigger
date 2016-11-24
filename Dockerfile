FROM ubuntu:16.04

# Set noninteractive mode for apt-get
ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update
RUN apt-get -qqy install heirloom-mailx

ADD trigger.sh /usr/bin

CMD /usr/bin/trigger.sh
