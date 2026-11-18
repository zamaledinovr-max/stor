# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# gosu lets the container start as root, fix permissions on the Amvera
# persistent volume (/data), and then drop privileges to appuser.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY frontend ./frontend
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./

RUN pip install .

RUN useradd --create-home --uid 10001 appuser \
    && chmod +x /app/scripts/start_all.sh \
    && mkdir -p /app/var/media /data/media \
    && chown -R appuser:appuser /app /data

EXPOSE 8000

# Starts migrations, API and bot in one container. Use RUN_API/RUN_BOT=0 to
# disable one of them (for example when splitting into two Amvera apps).
CMD ["bash", "scripts/start_all.sh"]
