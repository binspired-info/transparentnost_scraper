#!/usr/bin/env python3
import subprocess
import sys

def run_command(cmd):
    """Run a shell command and exit on failure."""
    print(f"\n▶ Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"\n✖ Command failed with exit code {result.returncode}: {cmd}", file=sys.stderr)
        sys.exit(result.returncode)

def main():
    # 1) Build & push the container image
    run_command("gcloud builds submit --tag gcr.io/zagreb-viz/transparentnost-scraper")

    # 2) Update the Cloud Run job to use the new image
    run_command("gcloud run jobs update transparentnost-job --image gcr.io/zagreb-viz/transparentnost-scraper --region europe-west1")

    # 3) Execute the job immediately
    run_command("gcloud run jobs execute transparentnost-job --region europe-west1")

    print("\n✅ All steps completed successfully.")

if __name__ == "__main__":
    main()