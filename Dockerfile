FROM ubuntu:16.04

# Set noninteractive mode for apt-get
ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update
RUN apt-get -qqy install python

ADD log_trigger.py /usr/local/bin
ADD log_trigger.conf /etc/log_trigger/log_trigger.conf

# Flush buffered "print", will output stdout immediately
CMD PYTHONUNBUFFERED="1" /usr/local/bin/log_trigger.py /etc/log_trigger/log_trigger.conf