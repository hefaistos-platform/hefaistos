# Use the same Python base as the backend
FROM python:3.12-slim-bookworm

# Install git
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app/git_push_connector

# Copy the SDK first so it can be installed
COPY ./hefaistos-sdk /app/hefaistos-sdk

# Install dependencies
COPY ./git_push_connector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the connector code
COPY ./git_push_connector .

# Create a directory to clone repos into
RUN mkdir /tmp/git_pushes

CMD ["python", "connector.py"]
