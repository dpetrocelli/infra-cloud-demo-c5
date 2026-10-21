# Small base: Python already installed, nothing else.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first: they change rarely and weigh the most, so this layer
# stays cached when only main.py changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The code changes all the time: last.
COPY main.py .

# Shown on the page: change it at build time to see a rolling update. Declared after
# pip on purpose: a new version must not invalidate the dependency layer.
ARG APP_VERSION=v1
ENV APP_VERSION=${APP_VERSION} DATA_DIR=/data

# Not root. /data is created owned by the app user, so a named volume mounted
# there inherits that owner.
RUN useradd --uid 1000 --create-home app && mkdir -p /data && chown app /data
USER app

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
