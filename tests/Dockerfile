FROM python:3.8.2-alpine3.11

RUN pip install pytest==6.2.4 pytest-mock==3.6.1

COPY log_trigger.py /app/
COPY tests /app/tests/

# Flush buffered "print", will output stdout immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app/tests

CMD ["pytest", "test.py"]
