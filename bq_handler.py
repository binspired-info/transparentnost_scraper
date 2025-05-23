# bq_handler.py
import os
import datetime
from google.cloud import bigquery, storage

# ─── CONFIG ─────────────────────────────────────────────────────────────────────────
PROJECT    = "zagreb-viz"
DATASET    = "transparentnost"
TABLE      = "isplate_master"
CSV_BUCKET = "zagreb-viz-raw-csvs"  # or None to skip archiving
# ────────────────────────────────────────────────────────────────────────────────────

class BQHandler:
    def __init__(self):
        self.client = bigquery.Client(project=PROJECT)
        table_ref = self.client.dataset(DATASET).table(TABLE)
        self.table = self.client.get_table(table_ref)
        if CSV_BUCKET:
            self.storage = storage.Client(project=PROJECT)
            self.bucket  = self.storage.bucket(CSV_BUCKET)

    def get_last_date(self) -> datetime.date:
        row = next(self.client.query(
            f"SELECT MAX(datum) AS last_date "
            f"FROM `{PROJECT}.{DATASET}.{TABLE}`"
        ).result(), None)
        return row.last_date

    def delete_date(self, dt: datetime.date):
        job = self.client.query(
            f"DELETE FROM `{PROJECT}.{DATASET}.{TABLE}` "
            "WHERE DATE(datum) = @dt",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("dt", "DATE", dt)
                ]
            )
        )
        job.result()

    def load_csv(self, path: str, dt: datetime.date):
        # 1) Remove existing rows for dt
        self.delete_date(dt)

        # 2) Load with explicit schema and semicolon delimiter
        job_config = bigquery.LoadJobConfig(
            schema=self.table.schema,
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            field_delimiter=';',                               # ← add this
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND
        )
        with open(path, "rb") as f:
            load_job = self.client.load_table_from_file(
                f, self.table.reference, job_config=job_config
            )
        load_job.result()

        # 3) Archive raw CSV if desired
        if CSV_BUCKET:
            dest = f"raw/{os.path.basename(path)}"
            blob = self.bucket.blob(dest)
            blob.upload_from_filename(path)

if __name__ == "__main__":
    bqh = BQHandler()
    last_date = bqh.get_last_date()
    print(f"Last date in BQ: {last_date}")
    #test_csv_file = "C://Users//grand//OneDrive//ZagrebVIz//transparentnost_scraper//csvs//isplate_2024_01_02.csv"
    #bqh.load_csv(test_csv_file, datetime.date(2024, 1, 2))