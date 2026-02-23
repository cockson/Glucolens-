import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import AuditLog, Role
from app.api.deps import require_role

router = APIRouter()

@router.get("/verify")
def verify_audit_chain(db: Session = Depends(get_db), user=Depends(require_role(Role.super_admin))):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.asc()).all()
    if not rows:
        return {"ok": True, "checked": 0, "message": "No audit records"}

    prev_hash = None
    for idx, r in enumerate(rows):
        payload = json.loads(r.payload_json)
        expected = AuditLog.compute_hash(prev_hash, payload)
        if expected != r.record_hash:
            raise HTTPException(
                status_code=500,
                detail={
                    "ok": False,
                    "index": idx,
                    "audit_id": r.id,
                    "expected": expected,
                    "found": r.record_hash,
                },
            )
        prev_hash = r.record_hash

    return {"ok": True, "checked": len(rows)}