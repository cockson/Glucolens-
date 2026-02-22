import uuid
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import BillingPlan, BillingSubscription, SubscriptionStatus, Org
from app.core.config import settings
from app.services import paystack
from app.schemas.billing import (
    PlanOut, BootstrapOut, CheckoutInitIn, CheckoutInitOut, VerifyOut
)
from app.api.deps import require_role, get_current_user
from app.db.models import Role, User
from app.core.audit import write_audit_log

router = APIRouter()

def _uuid() -> str:
    return str(uuid.uuid4())

def _plan_price_kobo(tier: str, interval: str) -> int:
    if tier == "pharmacy":
        return settings.PHARMACY_MONTHLY_KOBO if interval == "monthly" else settings.PHARMACY_ANNUAL_KOBO
    if tier == "clinic":
        return settings.CLINIC_MONTHLY_KOBO if interval == "monthly" else settings.CLINIC_ANNUAL_KOBO
    if tier == "hospital":
        return settings.HOSPITAL_MONTHLY_KOBO if interval == "monthly" else settings.HOSPITAL_ANNUAL_KOBO
    raise ValueError("Unknown tier")

def _interval_paystack(interval: str) -> str:
    # Paystack uses 'monthly' and 'annually'
    return interval

@router.post("/plans/bootstrap", response_model=BootstrapOut)
def bootstrap_plans(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.super_admin)),
):
    created = 0
    updated = 0

    combos = [
        ("pharmacy", "monthly"),
        ("pharmacy", "annually"),
        ("clinic", "monthly"),
        ("clinic", "annually"),
        ("hospital", "monthly"),
        ("hospital", "annually"),
    ]

    for tier, interval in combos:
        amount = _plan_price_kobo(tier, interval)
        name = f"GL_{tier.upper()}_{interval.upper()}"

        plan = db.query(BillingPlan).filter(
            BillingPlan.tier == tier, BillingPlan.interval == interval
        ).first()

        if not plan:
            plan = BillingPlan(
                id=_uuid(),
                tier=tier,
                interval=interval,
                amount_kobo=amount,
                currency="NGN",
                paystack_plan_code=None,
                is_active=True,
            )
            db.add(plan)
            created += 1
        else:
            # update amounts if changed
            if plan.amount_kobo != amount:
                plan.amount_kobo = amount
                updated += 1

        # Create Paystack plan if missing
        if not plan.paystack_plan_code:
            resp = paystack.create_plan(name=name, amount_kobo=amount, interval=_interval_paystack(interval))
            if not resp.get("status"):
                raise HTTPException(status_code=400, detail=f"Paystack plan create failed: {resp}")
            plan.paystack_plan_code = resp["data"]["plan_code"]

    write_audit_log(
        db,
        actor_user_id=user.id,
        org_id=None,
        facility_id=None,
        action="billing.plans.bootstrap",
        resource="billing_plans",
        payload={"created": created, "updated": updated},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return BootstrapOut(created=created, updated=updated)

@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    plans = db.query(BillingPlan).filter(BillingPlan.is_active == True).all()  # noqa
    return [
        PlanOut(
            tier=p.tier,
            interval=p.interval,
            amount_kobo=p.amount_kobo,
            currency=p.currency,
            paystack_plan_code=p.paystack_plan_code,
        )
        for p in plans
    ]

@router.post("/checkout/initialize", response_model=CheckoutInitOut)
def initialize_checkout(
    request: Request,
    payload: CheckoutInitIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only business roles can subscribe for an org
    if user.role == Role.public:
        raise HTTPException(status_code=403, detail="Public users cannot subscribe for businesses")

    org = db.query(Org).filter(Org.id == payload.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")

    if user.org_id != org.id and user.role != Role.super_admin:
        raise HTTPException(status_code=403, detail="Cannot subscribe for another org")

    plan = db.query(BillingPlan).filter(
        BillingPlan.tier == payload.tier,
        BillingPlan.interval == payload.interval,
        BillingPlan.is_active == True,  # noqa
    ).first()

    if not plan or not plan.paystack_plan_code:
        raise HTTPException(status_code=400, detail="Billing plan not available")

    callback_url = f"{settings.FRONTEND_BASE_URL}/billing/callback"

    # metadata helps us tie transaction to org/tier/interval
    metadata = {
        "org_id": org.id,
        "tier": payload.tier,
        "interval": payload.interval,
        "paystack_plan_code": plan.paystack_plan_code,
    }

    resp = paystack.initialize_transaction(
        email=payload.email,
        amount_kobo=plan.amount_kobo,
        callback_url=callback_url,
        metadata=metadata,
    )
    if not resp.get("status"):
        raise HTTPException(status_code=400, detail=f"Paystack init failed: {resp}")

    data = resp["data"]
    write_audit_log(
        db,
        actor_user_id=user.id,
        org_id=org.id,
        facility_id=user.facility_id,
        action="billing.checkout.initialize",
        resource="billing",
        payload={"reference": data.get("reference"), "tier": payload.tier, "interval": payload.interval},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return CheckoutInitOut(authorization_url=data["authorization_url"], reference=data["reference"])

@router.get("/checkout/verify/{reference}", response_model=VerifyOut)
def verify_checkout(
    request: Request,
    reference: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resp = paystack.verify_transaction(reference)
    if not resp.get("status"):
        raise HTTPException(status_code=400, detail=f"Verify failed: {resp}")

    data = resp["data"]
    if data.get("status") != "success":
        raise HTTPException(status_code=402, detail="Payment not successful")

    metadata = data.get("metadata") or {}
    org_id = metadata.get("org_id")
    tier = metadata.get("tier")
    interval = metadata.get("interval")
    plan_code = metadata.get("paystack_plan_code")

    if not org_id or not tier or not interval or not plan_code:
        raise HTTPException(status_code=400, detail="Missing metadata; cannot activate subscription")

    if user.role != Role.super_admin and user.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot verify for another org")

    customer = (data.get("customer") or {})
    customer_code = customer.get("customer_code")
    if not customer_code:
        raise HTTPException(status_code=400, detail="Missing customer_code from Paystack verify")

    # Create subscription
    sub_resp = paystack.create_subscription(customer_code=customer_code, plan_code=plan_code)
    if not sub_resp.get("status"):
        raise HTTPException(status_code=400, detail=f"Subscription create failed: {sub_resp}")

    sub_data = sub_resp["data"]
    subscription_code = sub_data.get("subscription_code")
    email_token = sub_data.get("email_token")
    status = sub_data.get("status") or "active"

    row = db.query(BillingSubscription).filter(BillingSubscription.org_id == org_id).first()
    if not row:
        row = BillingSubscription(
            id=_uuid(),
            org_id=org_id,
            tier=tier,
            interval=interval,
            status=SubscriptionStatus.active if status == "active" else SubscriptionStatus.incomplete,
            paystack_subscription_code=subscription_code,
            paystack_email_token=email_token,
            paystack_customer_code=customer_code,
            last_payment_at=dt.datetime.utcnow(),
        )
        db.add(row)
    else:
        row.tier = tier
        row.interval = interval
        row.paystack_subscription_code = subscription_code
        row.paystack_email_token = email_token
        row.paystack_customer_code = customer_code
        row.last_payment_at = dt.datetime.utcnow()
        row.status = SubscriptionStatus.active if status == "active" else SubscriptionStatus.incomplete

    write_audit_log(
        db,
        actor_user_id=user.id,
        org_id=org_id,
        facility_id=user.facility_id,
        action="billing.checkout.verify",
        resource="billing",
        payload={"reference": reference, "subscription_code": subscription_code, "status": row.status.value},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return VerifyOut(ok=True, subscription_status=row.status.value)

@router.post("/webhook/paystack")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    # Paystack sends x-paystack-signature
    signature = request.headers.get("x-paystack-signature", "")
    raw = await request.body()

    if not signature or not paystack.verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data") or {}

    # Minimal event persistence + lockout logic
    # We map common subscription/payment events to subscription status.
    subscription_code = data.get("subscription_code")
    customer = data.get("customer") or {}
    customer_code = customer.get("customer_code")

    # Find by subscription_code first, else by customer_code (fallback)
    sub = None
    if subscription_code:
        sub = db.query(BillingSubscription).filter(BillingSubscription.paystack_subscription_code == subscription_code).first()
    if not sub and customer_code:
        sub = db.query(BillingSubscription).filter(BillingSubscription.paystack_customer_code == customer_code).first()

    # Update status based on event
    if sub:
        if event in {"subscription.create", "charge.success", "invoice.payment_succeeded"}:
            sub.status = SubscriptionStatus.active
            sub.last_payment_at = dt.datetime.utcnow()
        elif event in {"invoice.payment_failed", "subscription.disable", "subscription.not_renew"}:
            # Immediate lockout requirement
            sub.status = SubscriptionStatus.past_due if event == "invoice.payment_failed" else SubscriptionStatus.cancelled

        write_audit_log(
            db,
            actor_user_id=None,
            org_id=sub.org_id,
            facility_id=None,
            action="billing.webhook",
            resource="billing",
            payload={"event": event, "subscription_code": subscription_code, "new_status": sub.status.value},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    db.commit()
    return {"ok": True}