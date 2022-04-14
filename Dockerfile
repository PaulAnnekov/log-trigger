FROM python:3.8.13-slim-bullseye

RUN python3.8 -m pip install \
   https://github.com/mosquito/cysystemd/releases/download/1.4.8/cysystemd-1.4.8-cp38-cp38-manylinux2014_x86_64.whl

ADD log_trigger.py /usr/local/bin

# Flush buffered "print", will output stdout immediately
ENV PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.source https://github.com/PaulAnnekov/log-trigger

CMD ["/usr/local/bin/log_trigger.py", "/etc/log_trigger/log_trigger.conf", "/etc/log_trigger/cursor"]
