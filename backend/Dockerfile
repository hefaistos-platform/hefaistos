# Use the official Python 3.12 image as SHARP runtime baseline
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies including Node.js 20 for SyntaxTide LSP
RUN apt-get update && apt-get install -y \
    git \
    curl \
    docker.io \
    docker-compose \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@11.17.0 \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Normalize entrypoint line endings and ensure it is executable
#RUN sed -i 's/\r$//' /app/entrypoint.sh && \
#	chmod +x /app/entrypoint.sh

# Use entrypoint script to run migrations, generate connector token and start server
CMD ["python", "run_backend.py"]
