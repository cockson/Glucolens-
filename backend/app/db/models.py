import enum
import datetime as dt
import hashlib
import json

from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, ForeignKey, Enum, Text, Float
)
from sqlalchemy.orm import relationship
from app.db.base import Base

class Role(str, enum.Enum):
    public = "public"
    clinician = "clinician"
    facility_admin = "facility_admin"
    org_admin = "org_admin"
    super_admin = "super_admin"

class FacilityType(str, enum.Enum):
    pharmacy = "pharmacy"
    clinic = "clinic"
    hospital = "hospital"

class SubscriptionStatus(str, enum.Enum):
    active = "active"
    past_due = "past_due"
    cancelled = "cancelled"
    incomplete = "incomplete"

class Org(Base):
    __tablename__ = "orgs"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    country_code = Column(String, nullable=False)  # e.g. NG, KE
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    facilities = relationship("Facility", back_populates="org")
    users = relationship("User", back_populates="org")
    subscription = relationship("BillingSubscription", uselist=False, back_populates="org")

class Facility(Base):
    __tablename__ = "facilities"
    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    name = Column(String, nullable=False)
    facility_type = Column(Enum(FacilityType), nullable=False)
    site_code = Column(String, nullable=False, index=True)  # unique per org ideally
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    address = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    org = relationship("Org", back_populates="facilities")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.public)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=True)
    facility_id = Column(String, ForeignKey("facilities.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    org = relationship("Org", back_populates="users")

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

class BillingPlan(Base):
    __tablename__ = "billing_plans"
    id = Column(String, primary_key=True)
    tier = Column(String, nullable=False)  # pharmacy/clinic/hospital
    interval = Column(String, nullable=False)  # monthly/annually
    amount_kobo = Column(Integer, nullable=False)
    currency = Column(String, default="NGN")
    paystack_plan_code = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"
    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False, unique=True)
    tier = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.incomplete)

    paystack_subscription_code = Column(String, nullable=True)
    paystack_email_token = Column(String, nullable=True)
    paystack_customer_code = Column(String, nullable=True)

    current_period_end = Column(DateTime, nullable=True)
    last_payment_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    org = relationship("Org", back_populates="subscription")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    actor_user_id = Column(String, nullable=True)
    org_id = Column(String, nullable=True)
    facility_id = Column(String, nullable=True)

    action = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    payload_json = Column(Text, nullable=False)
    prev_hash = Column(String, nullable=True)
    record_hash = Column(String, nullable=False)

    @staticmethod
    def compute_hash(prev_hash: str | None, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        raw = (prev_hash or "") + canonical
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class Referral(Base):
    __tablename__ = "referrals"
    id = Column(String, primary_key=True)
    org_id = Column(String, nullable=False)
    from_facility_id = Column(String, nullable=False)
    to_facility_id = Column(String, nullable=True)
    patient_key = Column(String, nullable=False)  # pseudonym, not raw ID
    risk_score = Column(Integer, nullable=False)  # 0..100
    reason = Column(String, nullable=False)
    status = Column(String, default="open")  # open/accepted/completed
    created_at = Column(DateTime, default=dt.datetime.utcnow)

class Outcome(Base):
    __tablename__ = "outcomes"
    id = Column(String, primary_key=True)
    referral_id = Column(String, nullable=True)
    org_id = Column(String, nullable=False)
    facility_id = Column(String, nullable=False)
    patient_key = Column(String, nullable=False)
    outcome_label = Column(String, nullable=False)  # confirmed_t2d / not_t2d etc.
    notes = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=dt.datetime.utcnow)
    linked_prediction_id = Column(String, nullable=True)


class PredictionRecord(Base):
    __tablename__ = "prediction_records"
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    actor_user_id = Column(String, nullable=True)
    org_id = Column(String, nullable=True)
    facility_id = Column(String, nullable=True)

    country_code = Column(String, nullable=True)

    modality = Column(String, nullable=False, default="tabular")  # tabular later retina/skin
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    # Consent capture (versioned, per country)
    consent_version = Column(String, nullable=True)
    consent_json = Column(Text, nullable=True)

    # Input/Output storage (for monitoring; keep PHI out)
    input_json = Column(Text, nullable=False)
    output_json = Column(Text, nullable=False)

    # For calibration & monitoring
    predicted_label = Column(String, nullable=False)
    proba_json = Column(Text, nullable=False)  # probabilities per class


class DriftSnapshot(Base):
    __tablename__ = "drift_snapshots"
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    org_id = Column(String, nullable=True)
    facility_id = Column(String, nullable=True)
    country_code = Column(String, nullable=True)

    modality = Column(String, nullable=False, default="tabular")
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    window = Column(String, nullable=False)  # e.g. "last_7d", "last_30d"
    baseline_window = Column(String, nullable=False)  # e.g. "train"
    metrics_json = Column(Text, nullable=False)  # PSI/KS per feature

class SiteDataset(Base):
    __tablename__ = "site_datasets"
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    org_id = Column(String, nullable=False)
    facility_id = Column(String, nullable=True)
    country_code = Column(String, nullable=True)

    site_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Storage / integrity
    file_path = Column(Text, nullable=False)
    sha256 = Column(String, nullable=False)
    n_rows = Column(Integer, nullable=False, default=0)

    # Schema
    schema_json = Column(Text, nullable=False)  # columns detected

class ValidationRun(Base):
    __tablename__ = "validation_runs"
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    org_id = Column(String, nullable=False)
    dataset_id = Column(String, nullable=False)

    modality = Column(String, nullable=False, default="tabular")
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    status = Column(String, nullable=False, default="completed")  # MVP: completed/failed
    metrics_json = Column(Text, nullable=False)
    report_pdf_path = Column(Text, nullable=True)


class ThresholdPolicy(Base):
    __tablename__ = "threshold_policies"
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    org_id = Column(String, nullable=False)
    facility_id = Column(String, nullable=True)
    country_code = Column(String, nullable=True)

    modality = Column(String, nullable=False, default="fusion")
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    method = Column(String, nullable=False, default="dca_net_benefit_max")
    threshold = Column(Float, nullable=False)

    # governance
    status = Column(String, nullable=False, default="proposed")  # proposed/approved/retired
    approved_by_user_id = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)

    evidence_json = Column(Text, nullable=False)  # store summary of net benefit curve + dataset stats
