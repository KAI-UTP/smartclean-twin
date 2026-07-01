FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/telemetry-ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/telemetry-ingestion/ /app/

ENV PYTHONPATH="/app:/app/shared"
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["python", "main.py"]
