import ipaddress
import re
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.services import TZ


def clean_text(value):
    if isinstance(value, str):
        return unicodedata.normalize('NFC', ' '.join(value.split()))
    return value


def public_link(value):
    if not value:
        return None
    if not isinstance(value, str) or len(value)>2048 or any(ord(c)<33 for c in value) or '\\' in value or re.search(r'%(?:0[0-9a-f]|1[0-9a-f]|7f)',value,re.I):
        return None
    try:
        p=urlsplit(value)
        if p.scheme not in ('http','https') or p.username or p.password or not p.hostname or p.port not in (None,80,443):
            return None
        host=p.hostname.lower().rstrip('.')
        try:
            address=ipaddress.ip_address(host)
            if not address.is_global or address.is_multicast or address.is_reserved:return None
        except ValueError:
            if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',host):return None
            if host.endswith(('.localhost','.local','.internal','.test','.invalid','.example')):return None
            # Reject alternative numeric IPv4 spellings understood by browsers.
            if re.fullmatch(r'[0-9a-fx.]+',host) and host.split('.')[-1].startswith(('0x','0X')):return None
        return urlunsplit((p.scheme,p.netloc,p.path,p.query,p.fragment))
    except (ValueError, UnicodeError):
        return None


class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid', str_strip_whitespace=True)


class EventDate(StrictModel):
    start_date: date
    end_date: date | None=None
    starts_at: datetime | None=None
    ends_at: datetime | None=None
    timezone: Literal['Europe/Madrid']='Europe/Madrid'
    precision: Literal['date','datetime']='date'

    @model_validator(mode='after')
    def coherent(self):
        if self.end_date and self.end_date<self.start_date:raise ValueError('Fin anterior al inicio')
        if self.precision=='date' and (self.starts_at or self.ends_at):raise ValueError('Una fecha sin hora no admite instantes')
        if self.precision=='datetime' and (not self.starts_at or self.starts_at.utcoffset() is None):raise ValueError('Inicio con offset obligatorio')
        if self.starts_at:
            if self.starts_at.astimezone(TZ).date()!=self.start_date:raise ValueError('Día e instante incoherentes')
            self.starts_at=self.starts_at.astimezone(timezone.utc)
        if self.ends_at:
            if self.ends_at.utcoffset() is None or not self.starts_at or self.ends_at<self.starts_at:raise ValueError('Fin de hora inválido')
            if self.end_date and self.ends_at.astimezone(TZ).date()!=self.end_date:raise ValueError('Fin e instante incoherentes')
            self.ends_at=self.ends_at.astimezone(timezone.utc)
        return self


class Venue(StrictModel):
    name: str | None=Field(default=None,max_length=300)
    municipality_code: str | None=Field(default=None,max_length=20)
    municipality: str | None=Field(default=None,max_length=150)
    address: str | None=Field(default=None,max_length=500)
    latitude: float | None=Field(default=None,ge=-90,le=90,allow_inf_nan=False)
    longitude: float | None=Field(default=None,ge=-180,le=180,allow_inf_nan=False)
    coordinates_verified: bool=False
    _names=field_validator('name','municipality','address',mode='before')(clean_text)

    @model_validator(mode='after')
    def coordinates(self):
        if (self.latitude is None)!=(self.longitude is None):raise ValueError('Coordenadas incompletas')
        if self.coordinates_verified and (self.latitude is None or not (41.7<=self.latitude<=43.9 and -9.6<=self.longitude<=-6.7)):
            raise ValueError('Coordenadas sin coherencia territorial')
        return self


class Price(StrictModel):
    type: Literal['unknown','free','exact','from']='unknown'
    amount_minor: int | None=Field(default=None,ge=0,le=100000000,strict=True)
    currency: str | None=Field(default=None,pattern=r'^[A-Z]{3}$')
    evidence: str | None=Field(default=None,max_length=1000)

    @model_validator(mode='after')
    def honest(self):
        if self.type=='unknown' and (self.amount_minor is not None or self.currency is not None):raise ValueError('Desconocido debe tener importe y divisa nulos')
        if self.type!='unknown' and not self.evidence:raise ValueError('El precio requiere evidencia')
        if self.type=='free' and self.amount_minor!=0:raise ValueError('Gratis debe confirmar cero')
        if self.type in ('exact','from') and (self.amount_minor is None or not self.currency):raise ValueError('Importe y divisa obligatorios')
        return self


class Source(StrictModel):
    name: str=Field(min_length=1,max_length=200)
    url: str | None=None
    _url=field_validator('url',mode='before')(public_link)


class Candidate(StrictModel):
    external_id: str=Field(min_length=1,max_length=100,pattern=r'^[\w.:-]+$')
    occurrence_key: str=Field(default='',max_length=100,pattern=r'^[\w.:-]*$')
    title: str=Field(min_length=1,max_length=300)
    description: str | None=Field(default=None,max_length=20000)
    category: Literal['music','festival','culture']='culture'
    date: EventDate
    venue: Venue=Field(default_factory=Venue)
    price: Price=Field(default_factory=Price)
    source: Source
    tickets_url: str | None=None
    status: Literal['scheduled','cancelled','postponed','unknown']='unknown'
    original_start_date: date | None=None
    provenance: dict=Field(default_factory=dict)
    _tickets=field_validator('tickets_url',mode='before')(public_link)
    _texts=field_validator('title','description',mode='before')(clean_text)

    def dto(self,event_id,verified):
        d=self.model_dump(mode='json',exclude={'external_id','occurrence_key','provenance'})
        d['price'].pop('evidence',None)
        d.update(id=event_id,last_verified_at=verified,is_demo=False,image_path=None)
        return d
