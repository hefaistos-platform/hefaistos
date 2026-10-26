# Use the same Debian and Node/npm baseline as the frontend build.
FROM node:24.22.1-bookworm-slim AS node-runtime
RUN npm install -g npm@11.19.1

# Use the official Python 3.12 image as SHARP runtime baseline
FROM python:3.12-slim-bookworm

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies and expose npm/npx for SyntaxTide LSP.
RUN apt-get update && apt-get install -y \
    git \
    curl \
    libatomic1 \
    libstdc++6 \
    docker.io \
    docker-compose \
    && ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -s /usr/local/bin/node /usr/local/bin/nodejs \
    && test "$(node --version)" = "v24.22.1" \
    && test "$(npm --version)" = "11.19.1" \
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
