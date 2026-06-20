# syntax=docker/dockerfile:1

# The pywebview native window needs a GUI, so the container does not run app.py.
# Instead it serves the same FastAPI engine + web UI directly with uvicorn, which
# you open in a browser — equivalent to running `python app.py --browser`.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Copy the project (see .dockerignore for what is excluded from the build context).
COPY . .

# Install the app and its runtime dependencies. The install is editable on purpose:
# server/main.py resolves WEB_DIR and the SQLite path as Path(__file__).parent.parent,
# so the package must stay at /app. A regular install would relocate it into
# site-packages and break those relative paths. The pip cache mount keeps the large
# dictionary downloads (SudachiDict, JMdict) warm across rebuilds.
RUN --mount=type=cache,target=/root/.cache/pip pip install -e .

# The SQLite database is written here; mount a volume to persist it across runs.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8764

# "/" serves index.html and does not need the tokenizer, so it answers as soon as
# the server is up. The generous start period covers dictionary load at import time.
HEALTHCHECK --interval=30s --timeout=3s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8764/').status == 200 else 1)"

# Bind 0.0.0.0 inside the container so the published host port can reach it.
# Localhost-only exposure is enforced by the host-side port mapping (127.0.0.1:8764).
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8764"]
