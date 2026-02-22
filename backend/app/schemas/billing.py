from pydantic import BaseModel, EmailStr, Field

class PlanOut(BaseModel):
    tier: str
    interval: str
    amount_kobo: int
    currency: str
    paystack_plan_code: str | None

class BootstrapOut(BaseModel):
    created: int
    updated: int

class CheckoutInitIn(BaseModel):
    org_id: str
    tier: str = Field(pattern="^(pharmacy|clinic|hospital)$")
    interval: str = Field(pattern="^(monthly|annually)$")
    email: EmailStr

class CheckoutInitOut(BaseModel):
    authorization_url: str
    reference: str

class VerifyOut(BaseModel):
    ok: bool
    subscription_status: str