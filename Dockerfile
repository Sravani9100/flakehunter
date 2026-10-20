FROM python:3.12-slim

# git clones repositories for the fix agent; pytest runs tests in the subprocess sandbox.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[postgres]" pytest
COPY evals ./evals

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "flakehunter.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
