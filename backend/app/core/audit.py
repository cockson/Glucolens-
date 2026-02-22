import uuid
import datetime as dt
from sqlalchemy.orm import Session
from app.db.models import AuditLog

def _uuid() -> str:
    return str(uuid.uuid4())

def write_audit_log(
    db: Session,
    *,
    actor_user_id: str | None,
    org_id: str | None,
    facility_id: str | None,
    action: str,
    resource: str,
    payload: dict,
    ip: str | None = None,
    user_agent: str | None = None,
):
    # Get last record hash to chain
    last = db.query(AuditLog).order_by(AuditLog.created_at.desc()).first()
    prev_hash = last.record_hash if last else None

    record_hash = AuditLog.compute_hash(prev_hash, payload)

    row = AuditLog(
        id=_uuid(),
        created_at=dt.datetime.utcnow(),
        actor_user_id=actor_user_id,
        org_id=org_id,
        facility_id=facility_id,
        action=action,
        resource=resource,
        ip=ip,
        user_agent=user_agent,
        payload_json=__import__("json").dumps(payload, sort_keys=True),
        prev_hash=prev_hash,
        record_hash=record_hash,
    )
    db.add(row)