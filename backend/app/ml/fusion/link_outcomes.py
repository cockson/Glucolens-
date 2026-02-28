import os
from sqlalchemy import create_engine, text
from app.core.config import settings

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def ensure_linked_prediction_column(conn):
    conn.execute(text("""
        ALTER TABLE outcomes
        ADD COLUMN IF NOT EXISTS linked_prediction_id VARCHAR
    """))

def backfill_links(conn):
    # Link outcomes to latest tabular prediction for same org + patient_key (substring match)
    # Only fill where linked_prediction_id is NULL.
    conn.execute(text("""
        UPDATE outcomes o
        SET linked_prediction_id = p.id
        FROM LATERAL (
            SELECT pr.id
            FROM prediction_records pr
            WHERE pr.org_id = o.org_id
              AND pr.modality = 'tabular'
              AND pr.input_json ILIKE '%' || o.patient_key || '%'
              AND pr.created_at <= o.recorded_at
            ORDER BY pr.created_at DESC
            LIMIT 1
        ) p
        WHERE o.linked_prediction_id IS NULL
          AND o.patient_key IS NOT NULL
          AND o.patient_key <> ''
          AND p.id IS NOT NULL
    """))

def main():
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        ensure_linked_prediction_column(conn)
        backfill_links(conn)
    print("Done: ensured outcomes.linked_prediction_id and backfilled where possible.")

if __name__ == "__main__":
    main()
