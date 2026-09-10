FROM ghcr.io/astral-sh/uv:0.11.19 AS uv

FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --create-home --uid 10001 dj-digger

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY schema-bundle.json ./schema-bundle.json

RUN uv sync --frozen --no-dev \
    && chown -R dj-digger:dj-digger /app

ENV PATH="/app/.venv/bin:$PATH"
USER dj-digger

ENTRYPOINT ["dj-digger"]
