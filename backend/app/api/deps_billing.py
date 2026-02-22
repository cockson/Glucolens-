from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import BillingSubscription, SubscriptionStatus, Role, User
from app.api.deps import get_current_user

BUSINESS_ROLES = {Role.clinician, Role.facility_admin, Role.org_admin, Role.super_admin}

def require_active_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    # Public users are free tier (rate-limited elsewhere)
    if user.role == Role.public:
        return user

    # Super admin can bypass org subscription checks (platform operator)
    if user.role == Role.super_admin:
        return user

    if not user.org_id:
        raise HTTPException(status_code=403, detail="Business access requires org")

    sub = db.query(BillingSubscription).filter(BillingSubscription.org_id == user.org_id).first()
    if not sub or sub.status != SubscriptionStatus.active:
        raise HTTPException(status_code=402, detail="Subscription inactive. Please renew to continue.")
    return user