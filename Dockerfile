# 1. Use an official Python runtime as a parent image
FROM python:3.9-slim

# 2. Install Chrome + driver dependencies
RUN apt-get update && apt-get install -y \
    wget gnupg unzip \
    chromium chromium-driver \
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
    DOWNLOAD_DIR="/tmp/downloads" 
    #SCREENSHOTS_DIR="/tmp/screenshots"

# 7. Ensure the download directory exists
RUN mkdir -p /tmp/downloads
#    Ensure the screenshots directory exists
#RUN mkdir -p /tmp/screenshots

# 8. Default command to run your scraper
ENTRYPOINT ["python", "transparentnost_scraper.py"]