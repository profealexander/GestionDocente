FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Run migrations, then start API + bot in parallel
CMD uv run alembic upgrade head && uv run schoolai-api & uv run schoolai-bot
