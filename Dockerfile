FROM python:3.8.18-slim-bookworm as build

RUN apt update && apt install -yy build-essential libsystemd-dev
# Need to build from sources to handle the bug in pre-built wheels: https://github.com/mosquito/cysystemd/issues/59
RUN python3.8 -m pip install cysystemd --no-binary :all:

FROM python:3.8.18-slim-bookworm
COPY --from=build /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
ADD log_trigger.py /usr/local/bin

# Flush buffered "print", will output stdout immediately
ENV PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.source https://github.com/PaulAnnekov/log-trigger

CMD ["/usr/local/bin/log_trigger.py", "/etc/log_trigger/log_trigger.conf", "/etc/log_trigger/cursor"]
