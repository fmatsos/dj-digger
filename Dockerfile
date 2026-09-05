FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config/analysis.toml ./config/analysis.toml
COPY schema-bundle.json ./schema-bundle.json
COPY schemas ./schemas

RUN pip install --no-cache-dir .

ENTRYPOINT ["dj-digger"]
