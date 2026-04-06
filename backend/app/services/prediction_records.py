from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import PredictionRecord


def save_prediction_record(db: Session, **record_data) -> str | None:
    try:
        bind = db.get_bind()
        if bind is None:
            return None

        inspector = inspect(bind)
        if not inspector.has_table("prediction_records"):
            return None

        column_names = {col["name"] for col in inspector.get_columns("prediction_records")}
        payload = {key: value for key, value in record_data.items() if key in column_names}
        if not payload:
            return None

        record = PredictionRecord(**payload)
        db.add(record)
        db.commit()
        return getattr(record, "id", None)
    except SQLAlchemyError:
        db.rollback()
        return None
