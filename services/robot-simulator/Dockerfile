FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/robot-simulator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/robot-simulator/ /app/

ENV PYTHONPATH="/app:/app/shared"
ENV PYTHONUNBUFFERED=1

EXPOSE 8004

CMD ["python", "main.py"]
