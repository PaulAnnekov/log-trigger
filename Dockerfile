FROM ubuntu:16.04

# Set noninteractive mode for apt-get
ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update
RUN apt-get -qqy install python

ADD trigger.py /usr/local/bin

# Flush buffered "print", will output stdout immediately
CMD PYTHONUNBUFFERED="1" /usr/local/bin/trigger.py
