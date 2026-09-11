# Use the same Python base as the backend
FROM python:3.12-slim-bookworm

# Install git
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app/rule_connector

# Copy the SDK first so it can be installed (context is repo root)
COPY hefaistos-sdk /app/hefaistos-sdk

# Install dependencies (requirements located under rule_connector/ in repo root)
COPY rule_connector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the connector code directory into workdir
COPY rule_connector/ .

# Create a directory to clone repos into
RUN mkdir /tmp/rule_repos

CMD ["python", "connector.py"]
