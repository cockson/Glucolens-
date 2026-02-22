import requests
import hmac
import hashlib
from app.core.config import settings

BASE = "https://api.paystack.co"

def _headers():
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

def create_plan(name: str, amount_kobo: int, interval: str):
    r = requests.post(
        f"{BASE}/plan",
        headers=_headers(),
        json={"name": name, "amount": amount_kobo, "interval": interval},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def initialize_transaction(email: str, amount_kobo: int, callback_url: str, metadata: dict):
    r = requests.post(
        f"{BASE}/transaction/initialize",
        headers=_headers(),
        json={
            "email": email,
            "amount": amount_kobo,
            "callback_url": callback_url,
            "metadata": metadata,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def verify_transaction(reference: str):
    r = requests.get(
        f"{BASE}/transaction/verify/{reference}",
        headers=_headers(),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def create_subscription(customer_code: str, plan_code: str):
    r = requests.post(
        f"{BASE}/subscription",
        headers=_headers(),
        json={"customer": customer_code, "plan": plan_code},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    mac = hmac.new(
        settings.PAYSTACK_WEBHOOK_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(mac, signature)