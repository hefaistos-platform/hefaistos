FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 1. Set WORKDIR to a subdirectory.
WORKDIR /app/threat_intel_connector

# 2. Copy the SDK folder to the sibling directory (/app/hefaistos-sdk)
COPY hefaistos-sdk /app/hefaistos-sdk

# 3. Copy requirements from the context
COPY threat_intel_connector/requirements.txt .

# 4. Install dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the connector code
COPY threat_intel_connector .

CMD ["python", "connector.py"]
