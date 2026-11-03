FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir -r requirements.txt
COPY bf4br/ ./bf4br/
COPY tests/ ./tests/
USER 65532:65532
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
