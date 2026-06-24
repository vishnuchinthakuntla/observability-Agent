"""Module: Dockerfile"""

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["uvicorn", "observability_redis_api.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
 
