# Use the same Python base as the backend
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app/deploy_connector

# Install dependencies
COPY hefaistos-sdk /app/hefaistos-sdk
COPY deploy_connector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the connector code
COPY deploy_connector .

# The command to run when the container starts
CMD ["python", "connector.py"]
