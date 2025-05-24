#!/usr/bin/env python3
import subprocess
import sys
import os
import platform
import winsound


def notify_sound():
    """Play a notification sound when the script finishes."""
    if platform.system() == "Windows":
        winsound.Beep(1000, 1000)  # 1000 Hz for 1000 ms (louder and longer)

def download_results(run_id=None, download_dir=None):
    """
    Download results from GCS bucket.
    Args:
        run_id (str, optional): Specific run ID to download. If None, downloads latest.
        download_dir (str, optional): Directory to download files to. Defaults to current directory.
    """
    # Create download directory if it doesn't exist
    if download_dir:
        subdir = os.path.join(download_dir, run_id) if run_id else download_dir
        os.makedirs(subdir, exist_ok=True)
        dest_path = subdir
    else:
        dest_path = "."

    if run_id:
        # Download specific run
        _run_command(f'gsutil -m cp -r gs://zagreb-viz-snapshots/{run_id}/* "{dest_path}"')
    else:
        # Download latest run (assuming runs are date-formatted)
        _run_command(f"""
            latest=$(gsutil ls gs://zagreb-viz-snapshots/ | sort | tail -n 1)
            gsutil -m cp -r $latest* "{dest_path}"
        """)


def _run_command(cmd):
    """Run a shell command and exit on failure."""
    print(f"\n▶ Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"\n✖ Command failed with exit code {result.returncode}: {cmd}", file=sys.stderr)
        sys.exit(result.returncode)

def main():
    # 1) Build & push the container image
    _run_command("gcloud builds submit --tag gcr.io/zagreb-viz/transparentnost-scraper")

    # 2) Update the Cloud Run job with proper configuration
    _run_command("""
        gcloud run jobs update transparentnost-job \
        --image gcr.io/zagreb-viz/transparentnost-scraper \
        --region europe-west1 \
        --set-env-vars "BUCKET_NAME=zagreb-viz-snapshots" \
        --max-retries 0 \
        --tasks 1 \
        --task-timeout 3600 \
        --execute-now
    """)

    # 3) Run the Cloud Run job
    _run_command("""gcloud run jobs execute transparentnost-job --region europe-west1""")

    print("\n✅ All steps completed successfully.")
    notify_sound()

if __name__ == "__main__":
    if True:
        main()
    else:
        download_dir = "C:\\Users\\grand\\OneDrive\\ZagrebVIz\\transparentnost_scraper\\gcloud_snapshots"
        download_results(run_id="20250523_141037", download_dir=download_dir)  # Example run_id