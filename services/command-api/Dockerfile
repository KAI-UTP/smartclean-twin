FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/command-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/command-api/ /app/

ENV PYTHONPATH="/app:/app/shared"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "main.py"]
