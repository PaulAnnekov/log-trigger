FROM python:3.8.2-alpine3.11

ADD log_trigger.py /usr/local/bin

# Flush buffered "print", will output stdout immediately
ENV PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.source https://github.com/PaulAnnekov/log-trigger

CMD ["/usr/local/bin/log_trigger.py", "/etc/log_trigger/log_trigger.conf", "/etc/log_trigger/state/cursor"]
