FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/ai-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ai-service/ /app/

# Train model at build time so it's baked into the image
RUN python train_model.py

ENV PYTHONPATH="/app:/app/shared"
ENV PYTHONUNBUFFERED=1
ENV MODEL_DIR=/app/models

EXPOSE 8003

CMD ["python", "main.py"]
