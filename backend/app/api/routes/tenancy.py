import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Org, Facility, FacilityType, Role, User
from app.api.deps import require_role, get_current_user
from app.schemas.tenancy import OrgCreateIn, OrgOut, FacilityCreateIn, FacilityOut

router = APIRouter()

def _uuid() -> str:
    return str(uuid.uuid4())

@router.post("/orgs", response_model=OrgOut)
def create_org(payload: OrgCreateIn, db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin))):
    org = Org(id=_uuid(), name=payload.name, country_code=payload.country_code.upper())
    db.add(org)
    db.commit()
    return OrgOut(id=org.id, name=org.name, country_code=org.country_code)

@router.get("/orgs", response_model=list[OrgOut])
def list_orgs(db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin))):
    rows = db.query(Org).all()
    return [OrgOut(id=o.id, name=o.name, country_code=o.country_code) for o in rows]

@router.post("/facilities", response_model=FacilityOut)
def create_facility(payload: FacilityCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # org_admin can create in own org; super_admin can create anywhere
    if user.role != Role.super_admin and user.org_id != payload.org_id:
        raise HTTPException(status_code=403, detail="Cannot create facility outside your org")

    org = db.query(Org).filter(Org.id == payload.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")

    fac = Facility(
        id=_uuid(),
        org_id=payload.org_id,
        name=payload.name,
        facility_type=FacilityType(payload.facility_type),
        site_code=payload.site_code,
        city=payload.city,
        state=payload.state,
        address=payload.address,
    )
    db.add(fac)
    db.commit()
    return FacilityOut(
        id=fac.id, org_id=fac.org_id, name=fac.name, facility_type=fac.facility_type.value,
        site_code=fac.site_code, city=fac.city, state=fac.state, address=fac.address
    )

@router.get("/facilities", response_model=list[FacilityOut])
def list_facilities(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # org users see their org facilities; super_admin sees all
    q = db.query(Facility)
    if user.role != Role.super_admin:
        if not user.org_id:
            return []
        q = q.filter(Facility.org_id == user.org_id)
    rows = q.all()
    return [
        FacilityOut(
            id=f.id, org_id=f.org_id, name=f.name, facility_type=f.facility_type.value,
            site_code=f.site_code, city=f.city, state=f.state, address=f.address
        ) for f in rows
    ]

@router.get("/public/facilities", response_model=list[FacilityOut])
def public_facility_search(
    country_code: str,
    facility_type: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Facility).join(Org, Org.id == Facility.org_id).filter(Org.country_code == country_code.upper())
    if facility_type:
        query = query.filter(Facility.facility_type == FacilityType(facility_type))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Facility.name.ilike(like)) | (Facility.city.ilike(like)) | (Facility.state.ilike(like)))
    rows = query.limit(50).all()
    return [
        FacilityOut(
            id=f.id, org_id=f.org_id, name=f.name, facility_type=f.facility_type.value,
            site_code=f.site_code, city=f.city, state=f.state, address=f.address
        ) for f in rows
    ]