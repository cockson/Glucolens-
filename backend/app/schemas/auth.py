from pydantic import BaseModel, EmailStr, Field

class RegisterPublicIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class RegisterBusinessIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    org_name: str = Field(min_length=2, max_length=120)
    country_code: str = Field(min_length=2, max_length=2)  # NG, KE...
    facility_name: str = Field(min_length=2, max_length=120)
    facility_type: str = Field(pattern="^(pharmacy|clinic|hospital)$")
    site_code: str = Field(min_length=2, max_length=50)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshIn(BaseModel):
    refresh_token: str

class MeOut(BaseModel):
    id: str
    email: EmailStr
    role: str
    org_id: str | None
    facility_id: str | None