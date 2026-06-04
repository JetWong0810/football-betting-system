FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY scraper-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper-service/ .
COPY deploy/scraper-service/entrypoint.py .

CMD ["python", "-u", "entrypoint.py"]
