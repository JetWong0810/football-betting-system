FROM python:3.9-slim

WORKDIR /app

# 与竞彩墙钟一致；开赛戳解析仍显式按 +08:00，不依赖本变量
ENV TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

COPY scraper-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper-service/ .
COPY deploy/scraper-service/entrypoint.py .

CMD ["python", "-u", "entrypoint.py"]
