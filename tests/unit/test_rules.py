from datetime import date,datetime,timezone
import pytest
from app.services import overlaps,sort_key,price_label
from app.schemas.event import Candidate


def test_boundaries_precision_and_order(candidate):
    dto=candidate.dto('evt-one','2026-10-28T10:00:00+00:00')
    assert overlaps(dto,date(2026,10,28),date(2026,10,29))
    assert not overlaps(dto,date(2026,10,29),date(2026,10,30))
    assert not overlaps(dto,date(2026,10,27),date(2026,10,28))
    dto['date']['end_date']='2026-10-30'
    assert overlaps(dto,date(2026,10,30),date(2026,10,31))
    dto['date'].update(starts_at='2026-10-28T10:00:00+00:00',ends_at='2026-10-29T23:00:00+00:00')
    assert not overlaps(dto,date(2026,10,30),date(2026,10,31))
    timed={**dto,'id':'evt-two','date':{**dto['date'],'starts_at':'2026-10-28T18:00:00+00:00'}}
    unknown={**dto,'id':'evt-three','date':{**dto['date'],'starts_at':None,'ends_at':None}}
    assert sorted([unknown,timed],key=sort_key)==[timed,unknown]


def test_amounts_and_currency(candidate):
    assert price_label({'type':'exact','amount_minor':1550,'currency':'EUR'})=='15,50 €'
    assert price_label({'type':'from','amount_minor':0,'currency':'GBP'})=='Desde 0 GBP'


def test_palette_contrast():
    def lum(value):
        rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        rgb=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v,w in zip(rgb,[.2126,.7152,.0722]))
    pairs=[('#F3F5F9','#0D1421',4.5),('#F3F5F9','#1B2739',4.5),('#B7C3D4','#1B2739',4.5),('#FF8066','#1B2739',4.5),('#C7A3FF','#1B2739',4.5),('#0D1421','#FF8066',4.5),('#73839b','#1B2739',3)]
    for a,b,minimum in pairs:
        high,low=sorted([lum(a),lum(b)],reverse=True)
        assert (high+.05)/(low+.05)>=minimum,(a,b)
