FROM python:3.14-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .
RUN mkdir -p session data
VOLUME ["/app/session", "/app/data"]
CMD ["python", "-m", "src.main"]
