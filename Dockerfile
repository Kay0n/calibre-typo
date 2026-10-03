FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CALIBRE_TYPO_HOST=0.0.0.0 \
    PUID=1000 \
    PGID=1000

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
COPY koreader ./koreader
RUN pip install --no-cache-dir . && rm -rf /build

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8090

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/healthz', timeout=4)"

# Python as PID 1 ignores SIGTERM, but waitress stops cleanly on SIGINT
STOPSIGNAL SIGINT

ENTRYPOINT ["entrypoint.sh"]
CMD ["calibre-typo", "serve"]
