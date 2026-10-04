# Single-container public demo for Render (build context: the repository root).
# The Compose image (./Dockerfile) has no CMD and no data; this one builds the data and the model
# and serves the dashboard.
FROM python:3.12-slim

# libgomp1: OpenMP runtime required by LightGBM; make: `make pipeline` stays the single
# definition of the pipeline.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 make \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 app
WORKDIR /app

ENV UV_NO_SYNC=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache

COPY Makefile ./
COPY deploy/render/start.sh ./
COPY data_platform ./data_platform
COPY dbt ./dbt
COPY ml ./ml
COPY services ./services

RUN mkdir -p data mlruns dbt/target dbt/logs && chown -R app:app data mlruns dbt
USER app

# The data is synthetic, so the warehouse and the model are built into the image: start-up is fast
# and every deployment serves identical numbers.
RUN make pipeline

EXPOSE 10000
CMD ["./start.sh"]
