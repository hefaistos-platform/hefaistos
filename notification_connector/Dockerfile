
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 1. Set WORKDIR to a subdirectory.
WORKDIR /app/notification_connector

# 2. Copy the SDK folder to the sibling directory (/app/hefaistos-sdk)
COPY hefaistos-sdk /app/hefaistos-sdk

# 3. Copy requirements from the context
COPY notification_connector/requirements.txt .

# 4. Install dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the connector code
COPY notification_connector .

CMD ["python", "notifier.py"]
