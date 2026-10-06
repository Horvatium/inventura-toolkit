# Inventura Toolkit: web application image.
# Build stage installs the locked dependencies with uv; the runtime stage carries only
# Python, the virtual environment and the files the application reads at run time.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_SYSTEM_CERTS=1
WORKDIR /app

# Optional extra root certificate, for networks where a proxy or an antivirus inspects
# HTTPS: docker build --secret id=extra_ca,src=root-ca.pem .
# It is trusted only while dependencies are downloaded; the runtime image does not get it.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then \
        cp /run/secrets/extra_ca /usr/local/share/ca-certificates/extra_ca.crt \
        && update-ca-certificates; \
    fi

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable


FROM python:3.12-slim
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 1000 inventura
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
USER inventura
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]
ENTRYPOINT ["entrypoint.sh"]
