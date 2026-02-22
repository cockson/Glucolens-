from pydantic import BaseModel, Field

class OrgCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    country_code: str = Field(min_length=2, max_length=2)

class OrgOut(BaseModel):
    id: str
    name: str
    country_code: str

class FacilityCreateIn(BaseModel):
    org_id: str
    name: str = Field(min_length=2, max_length=120)
    facility_type: str = Field(pattern="^(pharmacy|clinic|hospital)$")
    site_code: str = Field(min_length=2, max_length=50)
    city: str | None = None
    state: str | None = None
    address: str | None = None

class FacilityOut(BaseModel):
    id: str
    org_id: str
    name: str
    facility_type: str
    site_code: str
    city: str | None
    state: str | None
    address: str | None