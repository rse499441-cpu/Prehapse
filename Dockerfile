FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY 01-dungeon-explorer/requirements.txt /tmp/dungeon-requirements.txt
COPY 02-yan-qingchuan-casino/requirements.txt /tmp/casino-requirements.txt
RUN pip install --no-cache-dir \
    -r /tmp/dungeon-requirements.txt \
    -r /tmp/casino-requirements.txt

COPY . /app

RUN mkdir -p /app/01-dungeon-explorer/data

CMD ["python", "-u", "deploy/start_bots.py"]
