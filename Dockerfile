# 1. Use an official Python runtime as a parent image
FROM python:3.9-slim

# 2. Install Chrome + driver dependencies and Google Cloud SDK
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl apt-transport-https ca-certificates \
    chromium chromium-driver \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - \
    && apt-get update && apt-get install -y google-cloud-sdk \
    && rm -rf /var/lib/apt/lists/*

# 3. Create working directory
WORKDIR /app

# 4. Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy your application code
COPY . .

# 6. Set environment variables for Cloud Run
#    In production, Cloud Run will override these via --set-env-vars
ENV PRODUCTION="true" \
    DOWNLOAD_DIR="/tmp/downloads" \
    LOG_DIR="/tmp/logs" \
    SNAPSHOT_DIR="/tmp/snapshots" \
    OUTPUT_BUCKET="gs://zagreb-viz-snapshots"

# 7. Ensure the directories exist
RUN mkdir -p /tmp/downloads
RUN mkdir -p /tmp/logs
RUN mkdir -p /tmp/snapshots
# Create a bucket mount point
RUN mkdir -p /workspace/output

# 8. Default command to run your scraper (remove gsutil copy)
CMD ["python", "transparentnost_scraper.py"]