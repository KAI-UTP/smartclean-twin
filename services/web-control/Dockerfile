FROM python:3.11-slim

WORKDIR /app

COPY services/web-control/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/web-control/ /app/

ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

EXPOSE 8005

CMD ["python", "main.py"]
