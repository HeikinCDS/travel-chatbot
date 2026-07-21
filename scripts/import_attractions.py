from pathlib import Path
import sqlite3
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = PROJECT_DIR / "data" / "FYP_Malaysia_Tourism_Dataset.xlsx"
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# The workbook's column headings begin on Excel row 3.
df = pd.read_excel(
    EXCEL_PATH,
    sheet_name="Attractions Entry",
    header=2
)

# Remove empty template rows.
df = df.dropna(subset=["Attraction ID", "Attraction Name"])

# Convert headings into database-friendly column names.
df.columns = (
    df.columns
    .astype(str)
    .str.strip()
    .str.lower()
    .str.replace(r"[^a-z0-9]+", "_", regex=True)
    .str.strip("_")
)

# Store verification dates in ISO format.
if "date_verified" in df.columns:
    df["date_verified"] = pd.to_datetime(
        df["date_verified"],
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")

with sqlite3.connect(DATABASE_PATH) as connection:
    # Replace is convenient while developing because it rebuilds the table.
    df.to_sql(
        "attractions",
        connection,
        if_exists="replace",
        index=False
    )

    # Prevent duplicate attraction IDs.
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_attraction_id
        ON attractions(attraction_id)
    """)

    # Improve commonly used recommendation filters.
    connection.execute("""
    CREATE INDEX IF NOT EXISTS idx_attraction_state
    ON attractions(state_territory)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_attraction_category
        ON attractions(primary_category)
    """)

    count = connection.execute(
        "SELECT COUNT(*) FROM attractions"
    ).fetchone()[0]

print(f"Successfully imported {count} attractions.")
print(f"Database created at: {DATABASE_PATH}")