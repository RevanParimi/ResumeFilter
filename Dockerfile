# depth-eval-engine — production image.
#   docker build -t depth-eval-engine .
#   docker run -p 8000:8000 --env-file .env depth-eval-engine
# Config: bake config.yaml into the image; override anything per-deploy with
# DEE_* env vars. Secrets (DEE_OPENROUTER_API_KEY, DEE_API_AUTH_KEY, ...)
# arrive ONLY through the environment.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY config.yaml .
# Alembic ships in the image: the app migrates itself on boot (PI-8 blocker 1).
COPY alembic ./alembic
COPY alembic.ini .
# The UI is served by this API at /ui (S8.6). Without this the mount exists and
# every page is a 404 -- and nothing in the app would say why, because a
# missing StaticFiles directory is not a boot error. tests/
# test_image_contents.py derives this requirement from the LIVE APP, so moving
# the directory fails a test rather than shipping a blank container.
COPY frontend ./frontend

# Non-root; /srv/app/data holds sqlite + flywheel (mount a volume in prod).
RUN useradd --create-home appuser \
    && mkdir -p data .chroma \
    && chown -R appuser:appuser /srv/app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD \
    python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
