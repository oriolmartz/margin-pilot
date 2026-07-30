# Single image for both services -- docker-compose (or two separate hosted
# services pointed at the same image) picks the command. Keeps the API and
# the dashboard guaranteed to run the exact same code, never two builds
# that can drift apart.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/outputs

EXPOSE 8000 8501

# Overridden per-service in docker-compose.yml / your hosting platform's
# start-command field.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
