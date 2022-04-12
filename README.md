# Log trigger

Consumes stdin in journald json format, watches for docker containers errors and sends emails.

## Features

- watch journald format logs for docker logs
  - can include specific non-docker logs too, e.g. to watch `dockerd` logs too
  - can exclude some containers
- log matchers to filter error logs
- configure log format per-container to match specific log levels
- globs to ignore logs
- watch files
- send to an email 

## How to use

1. [Switch](https://docs.docker.com/config/containers/logging/configure/#configure-the-default-logging-driver) to `journald` Docker logging driver.
2. Better to use systemd service, so it will start as soon as possible during boot. 
Example: [log-trigger.service](/log-trigger.service)

## Config

Check [log_trigger.sample.conf](/log_trigger.sample.conf) for all properties.
