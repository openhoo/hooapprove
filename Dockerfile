FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv
FROM python:3.13-slim@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY hooapprove ./hooapprove
RUN uv sync --frozen --no-dev --no-cache && useradd --uid 10001 --create-home app \
    && mkdir /data && chown app:app /data
USER 10001:10001
ENV HOOAPPROVE_DATABASE=/data/hooapprove.db
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8097
CMD ["/app/.venv/bin/uvicorn", "hooapprove.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8097", "--no-access-log"]
