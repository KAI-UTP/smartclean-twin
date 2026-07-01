FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/state-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/state-engine/ /app/

ENV PYTHONPATH="/app:/app/shared"
ENV PYTHONUNBUFFERED=1

EXPOSE 8002

CMD ["python", "main.py"]
