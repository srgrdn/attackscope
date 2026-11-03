FROM python:3.12-alpine@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app/src
WORKDIR /app
RUN addgroup -g 10001 attackscope && adduser -D -u 10001 -G attackscope attackscope \
    && mkdir /data && chown attackscope:attackscope /data
COPY backend/requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY fixtures ./fixtures

FROM base AS test
COPY backend/requirements-dev.lock ./requirements-dev.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements-dev.lock
COPY backend/tests ./tests
COPY backend/benchmarks ./benchmarks
USER 10001:10001
CMD ["python", "-m", "pytest"]

FROM base AS runtime
USER 10001:10001
EXPOSE 8000 8001
CMD ["python", "-m", "attackscope"]
