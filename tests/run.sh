#!/bin/sh

docker build -t log-trigger-tests -f Dockerfile ..
docker run \
    --rm \
    --name log-trigger-tests \
    log-trigger-tests
