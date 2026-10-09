from __future__ import annotations
import os, re, json, hashlib, ipaddress, socket
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Any
from urllib.parse import urlparse, urlunparse

import httpx
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends, HTTPException, status, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON, select, or_
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from pwdlib import PasswordHash
from jose import jwt, JWTError

APP_NAME = os.getenv('APP_NAME', 'Hermes Job Analyzer')
SECRET_KEY = os.getenv('SECRET_KEY', 'local-only-change-this-secret')
ALGORITHM = 'HS256'
TOKEN_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '720'))
SERPAPI_KEY = os.getenv('SERPAPI_API_KEY', '').strip()
SERPAPI_TIMEOUT = float(os.getenv('SERPAPI_TIMEOUT_SECONDS', '15'))
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./hermes.db')
DEMO_MODE = os.getenv('DEMO_MODE', 'true').lower() in ('1','true','yes')
password_hash = PasswordHash.recommended()

engine_args = {'connect_args': {'check_same_thread': False}} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
class Base(DeclarativeBase): pass

class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    email: Mapped[str]=mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str]=mapped_column(String(120), default='')
    password_hash: Mapped[str]=mapped_column(String(255))
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    profile: Mapped[Optional['Profile']]=relationship(back_populates='user', cascade='all, delete-orphan', uselist=False)
    applications: Mapped[list['Application']]=relationship(back_populates='user', cascade='all, delete-orphan')

class Profile(Base):
    __tablename__='profiles'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True)
    education_level: Mapped[str]=mapped_column(String(100), default='Undergraduate')
    college: Mapped[str]=mapped_column(String(200), default='')
    degree: Mapped[str]=mapped_column(String(120), default='')
    graduation_year: Mapped[Optional[int]]=mapped_column(Integer, nullable=True)
    skills: Mapped[list]=mapped_column(JSON, default=list)
    target_roles: Mapped[list]=mapped_column(JSON, default=list)
    preferred_locations: Mapped[list]=mapped_column(JSON, default=list)
    employment_types: Mapped[list]=mapped_column(JSON, default=list)
    experience_level: Mapped[str]=mapped_column(String(80), default='Internship / Entry-level')
    remote_preference: Mapped[str]=mapped_column(String(30), default='any')
    updated_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped[User]=relationship(back_populates='profile')

class Opportunity(Base):
    __tablename__='opportunities'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    source: Mapped[str]=mapped_column(String(40), default='demo', index=True)
    source_job_id: Mapped[Optional[str]]=mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str]=mapped_column(String(300), index=True)
    company: Mapped[str]=mapped_column(String(250), default='Not provided', index=True)
    location: Mapped[str]=mapped_column(String(250), default='Not provided')
    description: Mapped[str]=mapped_column(Text, default='')
    application_url: Mapped[Optional[str]]=mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]]=mapped_column(Text, nullable=True)
    employment_type: Mapped[Optional[str]]=mapped_column(String(100), nullable=True)
    compensation: Mapped[Optional[str]]=mapped_column(String(200), nullable=True)
    posted_at: Mapped[Optional[str]]=mapped_column(String(100), nullable=True)
    deadline: Mapped[Optional[str]]=mapped_column(String(100), nullable=True)
    first_seen: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    is_demo: Mapped[bool]=mapped_column(Boolean, default=False)
    raw_data: Mapped[dict]=mapped_column(JSON, default=dict)

class Application(Base):
    __tablename__='applications'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    opportunity_id: Mapped[int]=mapped_column(ForeignKey('opportunities.id', ondelete='CASCADE'), index=True)
    status: Mapped[str]=mapped_column(String(40), default='Saved', index=True)
    applied_date: Mapped[Optional[str]]=mapped_column(String(30), nullable=True)
    deadline: Mapped[Optional[str]]=mapped_column(String(40), nullable=True)
    follow_up_date: Mapped[Optional[str]]=mapped_column(String(40), nullable=True)
    interview_date: Mapped[Optional[str]]=mapped_column(String(40), nullable=True)
    notes: Mapped[str]=mapped_column(Text, default='')
    contact: Mapped[str]=mapped_column(String(200), default='')
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped[User]=relationship(back_populates='applications')
    opportunity: Mapped[Opportunity]=relationship()

class SearchRun(Base):
    __tablename__='search_runs'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    query: Mapped[str]=mapped_column(String(500))
    location: Mapped[str]=mapped_column(String(200), default='India')
    result_count: Mapped[int]=mapped_column(Integer, default=0)
    mode: Mapped[str]=mapped_column(String(30), default='demo')
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
app=FastAPI(title=APP_NAME, version='1.0.0', description='Trust-first career intelligence API. Unknown evidence remains unknown.')
origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'], allow_headers=['Authorization','Content-Type'])

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

class RegisterIn(BaseModel):
    email: EmailStr
    password: str=Field(min_length=8, max_length=128)
    display_name: str=Field(min_length=1, max_length=120)
class LoginIn(BaseModel): email: EmailStr; password: str
class ProfileIn(BaseModel):
    education_level: str='Undergraduate'; college: str=''; degree: str=''; graduation_year: Optional[int]=None
    skills: list[str]=[]; target_roles: list[str]=[]; preferred_locations: list[str]=[]; employment_types: list[str]=[]
    experience_level: str='Internship / Entry-level'; remote_preference: str='any'
class SearchIn(BaseModel):
    query: str=Field(min_length=2, max_length=250); location: str='India'; employment_type: Optional[str]=None
    remote: Optional[str]=None; company: Optional[str]=None; page: int=1
class AppIn(BaseModel):
    opportunity_id: int; status: str='Saved'; applied_date: Optional[str]=None; deadline: Optional[str]=None
    follow_up_date: Optional[str]=None; interview_date: Optional[str]=None; notes: str=''; contact: str=''
class AppPatch(BaseModel):
    status: Optional[str]=None; applied_date: Optional[str]=None; deadline: Optional[str]=None
    follow_up_date: Optional[str]=None; interview_date: Optional[str]=None; notes: Optional[str]=None; contact: Optional[str]=None

STATUSES=['Discovered','Saved','Ready to apply','Applied','Assessment','Interview','Offer received','Rejected','Withdrawn','Archived']
DEMO_JOBS=[
 {'title':'Python Developer Intern','company':'Northstar Labs (Demo)','location':'Bengaluru, India','description':'DEMO DATA. Build Python APIs, write tests, and collaborate with engineers. Required skills: Python, SQL, REST API. Internship; deadline not provided.','employment_type':'Internship','compensation':'Not provided','application_url':'https://example.com/careers/python-intern','source_url':'https://example.com/jobs/python-intern','source_job_id':'demo-python-01','is_demo':True},
 {'title':'Machine Learning Intern','company':'Aster Analytics (Demo)','location':'Remote, India','description':'DEMO DATA. Assist with data preparation and model evaluation. Required skills: Python, machine learning, pandas. Preferred: PyTorch.','employment_type':'Internship','compensation':'Not provided','application_url':'https://example.com/careers/ml-intern','source_url':'https://example.com/jobs/ml-intern','source_job_id':'demo-ml-02','is_demo':True},
 {'title':'Graduate Software Engineer','company':'Cobalt Systems (Demo)','location':'Chennai, India','description':'DEMO DATA. Entry-level role using Java, SQL, Git and software testing. Posting may be stale; refresh details with an employer source.','employment_type':'Full-time','compensation':'Not provided','application_url':None,'source_url':None,'source_job_id':'demo-grad-03','is_demo':True},
 {'title':'Data Science Trainee','company':'Sample Data Co. (Demo)','location':'Hyderabad, India','description':'DEMO DATA. Work with Python, SQL and analytics. This sample intentionally has incomplete source evidence and no deadline.','employment_type':'Internship','compensation':None,'application_url':'https://example.com/jobs/data-trainee','source_url':'https://example.com/jobs/data-trainee','source_job_id':'demo-data-04','is_demo':True},
 {'title':'Frontend Engineering Intern','company':'Juniper Digital (Demo)','location':'Pune, India','description':'DEMO DATA. React, TypeScript, CSS and accessibility. Sample listing is illustrative and is not a real vacancy.','employment_type':'Internship','compensation':'Not provided','application_url':'https://example.com/jobs/frontend-intern','source_url':'https://example.com/jobs/frontend-intern','source_job_id':'demo-front-05','is_demo':True},
]

def norm_text(v): return re.sub(r'\s+',' ',str(v or '')).strip()
def canonical_url(url):
    if not url: return None
    try:
        p=urlparse(url.strip())
        if p.scheme not in ('http','https') or not p.hostname: return None
        return urlunparse((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),'',p.query,''))
    except Exception: return None

def skills_from(text):
    terms=['python','java','javascript','typescript','react','sql','postgresql','machine learning','pytorch','tensorflow','pandas','numpy','django','fastapi','rest api','git','html','css','data analysis','communication']
    t=(text or '').lower()
    return [x for x in terms if x in t]

def match_job(profile: dict, job: dict):
    user_skills={str(s).strip().lower() for s in profile.get('skills',[]) if str(s).strip()}
    required=skills_from(job.get('description','')+' '+job.get('title',''))
    matched=sorted(set(required)&user_skills)
    missing=sorted(set(required)-user_skills)
    title=(job.get('title') or '').lower()
    roles=[str(x).lower() for x in profile.get('target_roles',[])]
    role_match=not roles or any(r and (r in title or title in r) for r in roles)
    location=(job.get('location') or '').lower()
    prefs=[str(x).lower() for x in profile.get('preferred_locations',[])]
    location_match=not prefs or 'remote' in location or any(p in location for p in prefs)
    remote_pref=profile.get('remote_preference','any')
    remote_match=remote_pref=='any' or (remote_pref=='remote' and 'remote' in location) or (remote_pref in ('onsite','on-site') and 'remote' not in location)
    skill_ratio=len(matched)/max(1,len(set(required))) if required else 0.25
    score=round(50*skill_ratio + 25*(1 if role_match else 0.25) + 12*(1 if location_match else 0.35) + 8*(1 if remote_match else 0.4) + 5*(1 if profile.get('education_level') else 0.5))
    score=max(0,min(100,score))
    category='Strong' if score>=75 else 'Moderate' if score>=55 else 'Partial' if score>=35 else 'Low'
    reasons=[]
    if matched: reasons.append('Matching skills: '+', '.join(matched))
    if missing: reasons.append('Skills not listed in your profile: '+', '.join(missing))
    reasons.append('Role title '+('aligns with' if role_match else 'may not align with')+' your target roles.')
    reasons.append('Location '+('fits' if location_match else 'may not fit')+' your saved preferences.')
    return {'score':score,'category':category,'matched_skills':matched,'missing_skills':missing,'role_match':role_match,'location_match':location_match,'reasons':reasons,'confidence':'limited' if not user_skills or not job.get('description') else 'standard','disclaimer':'Compatibility estimate only; not a probability of being hired.'}

def job_dict(j, profile=None):
    d={k:getattr(j,k) for k in ['id','source','source_job_id','title','company','location','description','application_url','source_url','employment_type','compensation','posted_at','deadline','is_demo']}
    d.update({'first_seen':j.first_seen.isoformat()+'Z' if j.first_seen else None,'last_seen':j.last_seen.isoformat()+'Z' if j.last_seen else None})
    if profile is not None: d['match']=match_job(profile,d)
    return d

def current_user(authorization: str=Header(default=''), db: Session=Depends(get_db)):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Please log in to continue.')
    try:
        payload=jwt.decode(authorization[7:],SECRET_KEY,algorithms=[ALGORITHM]); uid=int(payload['sub'])
    except (JWTError,ValueError,KeyError): raise HTTPException(401,'Session expired or invalid. Please log in again.')
    user=db.get(User,uid)
    if not user: raise HTTPException(401,'Account no longer exists.')
    return user

def token_for(user):
    now=datetime.now(timezone.utc)
    return jwt.encode({'sub':str(user.id),'iat':now,'exp':now+timedelta(minutes=TOKEN_MINUTES)},SECRET_KEY,algorithm=ALGORITHM)
def get_profile(user, db):
    p=db.scalar(select(Profile).where(Profile.user_id==user.id))
    if not p:
        p=Profile(user_id=user.id); db.add(p); db.commit(); db.refresh(p)
    return p
def profile_dict(p):
    return {k:getattr(p,k) for k in ['education_level','college','degree','graduation_year','skills','target_roles','preferred_locations','employment_types','experience_level','remote_preference']}
def find_or_add_job(db, item, source='serpapi'):
    url=canonical_url(item.get('application_url') or item.get('source_url'))
    sid=str(item.get('source_job_id') or item.get('job_id') or '').strip() or None
    existing=None
    if sid: existing=db.scalar(select(Opportunity).where(Opportunity.source_job_id==sid, Opportunity.source==source))
    if not existing and url:
        existing=db.scalar(select(Opportunity).where(or_(Opportunity.application_url==url,Opportunity.source_url==url)))
    if not existing:
        existing=db.scalar(select(Opportunity).where(Opportunity.title==norm_text(item.get('title')),Opportunity.company==norm_text(item.get('company')),Opportunity.location==norm_text(item.get('location'))))
    now=datetime.utcnow()
    if existing:
        # Keep existing evidence if a later result has an empty field.
        for k in ['title','company','location','description','application_url','source_url','employment_type','compensation','posted_at','deadline']:
            val=item.get(k)
            if val not in (None,'',[]): setattr(existing,k,norm_text(val) if isinstance(val,str) else val)
        existing.last_seen=now
        if item.get('raw_data'): existing.raw_data=item['raw_data']
        db.add(existing); db.commit(); db.refresh(existing); return existing,False
    j=Opportunity(source=source,source_job_id=sid,title=norm_text(item.get('title')) or 'Untitled role',company=norm_text(item.get('company')) or 'Not provided',location=norm_text(item.get('location')) or 'Not provided',description=norm_text(item.get('description')),application_url=url,source_url=canonical_url(item.get('source_url')) or url,employment_type=item.get('employment_type'),compensation=item.get('compensation'),posted_at=item.get('posted_at'),deadline=item.get('deadline'),first_seen=now,last_seen=now,is_demo=bool(item.get('is_demo')),raw_data=item.get('raw_data') or {})
    db.add(j); db.commit(); db.refresh(j); return j,True

def seed_demo(db):
    for item in DEMO_JOBS:
        if not db.scalar(select(Opportunity).where(Opportunity.source_job_id==item['source_job_id'])):
            find_or_add_job(db,item,'demo')

@app.get('/api/health')
def health(): return {'status':'ok','service':APP_NAME,'live_search_configured':bool(SERPAPI_KEY),'demo_mode':DEMO_MODE}
@app.post('/api/auth/register')
def register(body:RegisterIn,db:Session=Depends(get_db)):
    email=body.email.lower()
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,'Unable to create account with those details.')
    user=User(email=email,display_name=body.display_name.strip(),password_hash=password_hash.hash(body.password))
    db.add(user); db.commit(); db.refresh(user); get_profile(user,db)
    return {'access_token':token_for(user),'token_type':'bearer','user':{'id':user.id,'email':user.email,'display_name':user.display_name}}
@app.post('/api/auth/login')
def login(body:LoginIn,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.lower()))
    if not user or not password_hash.verify(body.password,user.password_hash): raise HTTPException(401,'Email or password is incorrect.')
    return {'access_token':token_for(user),'token_type':'bearer','user':{'id':user.id,'email':user.email,'display_name':user.display_name}}
@app.post('/api/auth/logout')
def logout(user:User=Depends(current_user)): return {'message':'Logged out. Remove the local access token in the client.'}
@app.get('/api/auth/me')
def me(user:User=Depends(current_user)): return {'id':user.id,'email':user.email,'display_name':user.display_name}
@app.get('/api/profile')
def profile_get(user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=get_profile(user,db); return profile_dict(p)
@app.put('/api/profile')
def profile_put(body:ProfileIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=get_profile(user,db)
    for k,v in body.model_dump().items(): setattr(p,k,v)
    db.commit(); return profile_dict(p)

@app.post('/api/search')
def search(body:SearchIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    query=body.query.strip(); mode='demo'; items=[]
    if SERPAPI_KEY:
        params={'engine':'google_jobs','q':query,'location':body.location or 'India','api_key':SERPAPI_KEY,'hl':'en','gl':'in','start':max(0,(body.page-1)*10)}
        if body.employment_type: params['employment_type']=body.employment_type
        try:
            with httpx.Client(timeout=SERPAPI_TIMEOUT,follow_redirects=False) as client:
                response=client.get('https://serpapi.com/search.json',params=params)
            if response.status_code==429: raise HTTPException(503,'SerpApi rate limit reached. Try again later.')
            response.raise_for_status(); payload=response.json()
            if payload.get('error'): raise HTTPException(502,'SerpApi could not complete this search. Check your key and query.')
            for x in payload.get('jobs_results',[]):
                detected=x.get('detected_extensions') or {}
                apply_opts=x.get('apply_options') or []
                link=(apply_opts[0].get('link') if apply_opts else None) or x.get('share_link')
                related=x.get('related_links') or []
                items.append({'source_job_id':x.get('job_id'),'title':x.get('title'),'company':x.get('company_name'),'location':x.get('location'),'description':x.get('description'),'application_url':link,'source_url':x.get('share_link') or (related[0].get('link') if related else None),'employment_type':detected.get('schedule_type'),'compensation':detected.get('salary'),'posted_at':detected.get('posted_at'),'deadline':None,'raw_data':x,'is_demo':False})
            mode='serpapi'
        except HTTPException: raise
        except httpx.TimeoutException: raise HTTPException(504,'SerpApi timed out. Please retry the search.')
        except httpx.HTTPError: raise HTTPException(502,'SerpApi is temporarily unavailable. Please retry.')
        except (ValueError,TypeError): raise HTTPException(502,'SerpApi returned an unexpected response.')
    else:
        if not DEMO_MODE: raise HTTPException(503,'Live search is not configured. Add SERPAPI_API_KEY to backend/.env.')
        seed_demo(db)
        qwords=set(query.lower().split())
        for d in DEMO_JOBS:
            if not qwords or any(w in (d['title']+' '+d['description']+' '+d['company']).lower() for w in qwords if len(w)>2): items.append(d)
        if not items: items=DEMO_JOBS[:3]
    p=get_profile(user,db); normalized=[]
    for item in items:
        if body.company and body.company.lower() not in str(item.get('company','')).lower(): continue
        j,_=find_or_add_job(db,item,'demo' if item.get('is_demo') else 'serpapi')
        normalized.append(job_dict(j,profile_dict(p)))
    run=SearchRun(user_id=user.id,query=query,location=body.location or 'India',result_count=len(normalized),mode=mode); db.add(run); db.commit()
    return {'search_id':run.id,'query':query,'location':body.location or 'India','mode':mode,'is_demo':mode=='demo','result_count':len(normalized),'message':'Demo examples only; not real vacancies.' if mode=='demo' else 'Live results returned by SerpApi Google Jobs. Fields may be incomplete.','results':normalized}
@app.get('/api/search/history')
def search_history(user:User=Depends(current_user),db:Session=Depends(get_db)):
    runs=db.scalars(select(SearchRun).where(SearchRun.user_id==user.id).order_by(SearchRun.created_at.desc()).limit(30)).all()
    return [{'id':r.id,'query':r.query,'location':r.location,'result_count':r.result_count,'mode':r.mode,'created_at':r.created_at.isoformat()+'Z'} for r in runs]
@app.get('/api/opportunities')
def opportunities(q:Optional[str]=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),user:User=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(Opportunity).order_by(Opportunity.last_seen.desc())
    if q: stmt=stmt.where(or_(Opportunity.title.ilike(f'%{q}%'),Opportunity.company.ilike(f'%{q}%'),Opportunity.description.ilike(f'%{q}%')))
    jobs=db.scalars(stmt.offset(offset).limit(limit)).all(); p=get_profile(user,db)
    saved={a.opportunity_id for a in db.scalars(select(Application).where(Application.user_id==user.id)).all()}
    return {'items':[dict(job_dict(j,profile_dict(p)),saved=j.id in saved) for j in jobs],'limit':limit,'offset':offset}
@app.get('/api/opportunities/{opportunity_id}')
def opportunity_detail(opportunity_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    j=db.get(Opportunity,opportunity_id)
    if not j: raise HTTPException(404,'Opportunity not found.')
    p=get_profile(user,db); d=job_dict(j,profile_dict(p)); d['evidence']=evidence_for(j); return d

def evidence_for(j):
    url=j.application_url
    return [
      {'field':'Application URL','value':url or 'Not provided','status':'partially_checked' if url else 'missing_information','source':j.source,'evidence_url':url,'checked_at':datetime.utcnow().isoformat()+'Z','note':'A URL being present does not prove the vacancy or employer is genuine.'},
      {'field':'Posting date','value':j.posted_at or 'Unknown','status':'supported' if j.posted_at else 'missing_information','source':j.source,'evidence_url':j.source_url,'checked_at':datetime.utcnow().isoformat()+'Z','note':'Source-provided posting information only.'},
      {'field':'Application deadline','value':j.deadline or 'Unknown / not provided','status':'supported' if j.deadline else 'missing_information','source':j.source,'evidence_url':j.source_url,'checked_at':datetime.utcnow().isoformat()+'Z','note':'No deadline is inferred when the source does not provide one.'},
      {'field':'Listing freshness','value':'Potentially stale' if (datetime.utcnow()-j.last_seen).days>7 else 'Recently observed','status':'potentially_stale' if (datetime.utcnow()-j.last_seen).days>7 else 'partially_checked','source':'Hermes observation history','evidence_url':j.source_url,'checked_at':j.last_seen.isoformat()+'Z','note':'Last seen by Hermes is not the same as source posting date.'},
    ]
@app.post('/api/opportunities/{opportunity_id}/save')
def save_job(opportunity_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    j=db.get(Opportunity,opportunity_id)
    if not j: raise HTTPException(404,'Opportunity not found.')
    apprec=db.scalar(select(Application).where(Application.user_id==user.id,Application.opportunity_id==j.id))
    if not apprec: db.add(Application(user_id=user.id,opportunity_id=j.id,status='Saved')); db.commit()
    return {'saved':True,'opportunity_id':j.id}
@app.delete('/api/opportunities/{opportunity_id}/save')
def unsave_job(opportunity_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.user_id==user.id,Application.opportunity_id==opportunity_id))
    if a and a.status in ('Saved','Discovered'): db.delete(a); db.commit()
    return {'saved':False}
@app.post('/api/opportunities/{opportunity_id}/verify')
def verify_job(opportunity_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    j=db.get(Opportunity,opportunity_id)
    if not j: raise HTTPException(404,'Opportunity not found.')
    # Deliberately avoid arbitrary server-side fetching; syntactic and IP safety checks only.
    url=j.application_url; result='missing_information'; detail='No application URL was provided.'
    if url:
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname: result='unsupported_or_invalid'; detail='URL is not a valid HTTP(S) URL.'
        else:
            host=parsed.hostname.lower()
            if host in ('localhost',) or host.endswith('.local'):
                result='unsupported_or_invalid'; detail='Local/private destinations are not checked.'
            else:
                try:
                    ips=socket.getaddrinfo(host,None)
                    unsafe=any(not ipaddress.ip_address(x[4][0]).is_global for x in ips)
                    result='unsupported_or_invalid' if unsafe else 'partially_checked'
                    detail='Resolves to a non-public IP and was not fetched.' if unsafe else 'URL syntax and public DNS resolution look acceptable; destination content and employer identity are not verified.'
                except Exception: result='not_checked'; detail='DNS lookup failed or was unavailable; destination was not fetched.'
    return {'opportunity_id':j.id,'checked_at':datetime.utcnow().isoformat()+'Z','status':result,'detail':detail,'evidence':evidence_for(j),'warning':'This is not a scam detector and does not prove a listing is legitimate.'}
@app.get('/api/verification/summary')
def verification_summary(user:User=Depends(current_user),db:Session=Depends(get_db)):
    saved=db.scalars(select(Application).where(Application.user_id==user.id)).all(); jobs=[a.opportunity for a in saved]
    return {'needs_attention':sum(1 for j in jobs if not j.application_url or not j.deadline),'missing_application_link':sum(1 for j in jobs if not j.application_url),'unknown_deadline':sum(1 for j in jobs if not j.deadline),'potentially_stale':sum(1 for j in jobs if (datetime.utcnow()-j.last_seen).days>7)}
@app.get('/api/applications')
def applications(status_filter:Optional[str]=None,user:User=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(Application).where(Application.user_id==user.id).order_by(Application.updated_at.desc())
    if status_filter: stmt=stmt.where(Application.status==status_filter)
    rows=db.scalars(stmt).all()
    return [app_dict(a) for a in rows]
def app_dict(a):
    return {'id':a.id,'opportunity_id':a.opportunity_id,'opportunity':job_dict(a.opportunity),'status':a.status,'applied_date':a.applied_date,'deadline':a.deadline,'follow_up_date':a.follow_up_date,'interview_date':a.interview_date,'notes':a.notes,'contact':a.contact,'created_at':a.created_at.isoformat()+'Z','updated_at':a.updated_at.isoformat()+'Z'}
@app.post('/api/applications')
def create_application(body:AppIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if body.status not in STATUSES: raise HTTPException(422,'Unknown application status.')
    j=db.get(Opportunity,body.opportunity_id)
    if not j: raise HTTPException(404,'Opportunity not found.')
    a=db.scalar(select(Application).where(Application.user_id==user.id,Application.opportunity_id==j.id))
    if a:
        for k,v in body.model_dump(exclude={'opportunity_id'}).items(): setattr(a,k,v)
    else: a=Application(user_id=user.id,**body.model_dump())
    db.add(a); db.commit(); db.refresh(a); return app_dict(a)
@app.patch('/api/applications/{application_id}')
def patch_application(application_id:int,body:AppPatch,user:User=Depends(current_user),db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.id==application_id,Application.user_id==user.id))
    if not a: raise HTTPException(404,'Application not found.')
    values=body.model_dump(exclude_unset=True)
    if values.get('status') and values['status'] not in STATUSES: raise HTTPException(422,'Unknown application status.')
    for k,v in values.items(): setattr(a,k,v)
    db.commit(); db.refresh(a); return app_dict(a)
@app.delete('/api/applications/{application_id}')
def delete_application(application_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.id==application_id,Application.user_id==user.id))
    if not a: raise HTTPException(404,'Application not found.')
    db.delete(a); db.commit(); return {'deleted':True}
@app.get('/api/applications/board')
def applications_board(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Application).where(Application.user_id==user.id)).all()
    return {s:[app_dict(a) for a in rows if a.status==s] for s in STATUSES}
@app.get('/api/dashboard')
def dashboard(user:User=Depends(current_user),db:Session=Depends(get_db)):
    jobs=db.scalars(select(Opportunity).order_by(Opportunity.last_seen.desc()).limit(100)).all(); p=get_profile(user,db)
    apps=db.scalars(select(Application).where(Application.user_id==user.id)).all()
    deadlines=[]
    today=date.today()
    for a in apps:
        d=a.deadline or a.opportunity.deadline
        if d:
            try:
                dd=date.fromisoformat(d[:10]); delta=(dd-today).days
                if delta<=7: deadlines.append({'application_id':a.id,'title':a.opportunity.title,'company':a.opportunity.company,'date':d,'days_remaining':delta,'source':'user-entered' if a.deadline else 'source-provided'})
            except ValueError: pass
    recent=[dict(job_dict(j,profile_dict(p)),saved=any(a.opportunity_id==j.id for a in apps)) for j in jobs[:6]]
    return {'metrics':{'opportunities_seen':len(jobs),'strong_matches':sum(1 for j in jobs if match_job(profile_dict(p),job_dict(j))['category']=='Strong'),'saved':len(apps),'applications_submitted':sum(1 for a in apps if a.status in ('Applied','Assessment','Interview','Offer received','Rejected')),'interviews':sum(1 for a in apps if a.status=='Interview'),'deadlines_approaching':len(deadlines),'needs_verification':sum(1 for a in jobs if not a.application_url or not a.deadline)},'recent_opportunities':recent,'applications_by_status':{s:sum(1 for a in apps if a.status==s) for s in STATUSES},'deadlines':deadlines}
@app.get('/api/reminders')
def reminders(user:User=Depends(current_user),db:Session=Depends(get_db)):
    dash=dashboard(user,db); return {'deadlines':dash['deadlines'],'timezone':'Asia/Kolkata','note':'Deadlines appear only when explicitly provided by the source or entered by you.'}
@app.get('/api/digests/latest')
def digest(user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=get_profile(user,db); prof=profile_dict(p); jobs=db.scalars(select(Opportunity).order_by(Opportunity.last_seen.desc()).limit(100)).all()
    apps=db.scalars(select(Application).where(Application.user_id==user.id)).all(); applied={a.opportunity_id for a in apps}
    candidates=[]
    for j in jobs:
        if j.id in applied: continue
        d=job_dict(j); m=match_job(prof,d)
        if m['score']>=30: candidates.append({'opportunity':d,'match':m,'reason':m['reasons'][0] if m['reasons'] else 'Relevant to your profile','is_demo':j.is_demo})
    candidates.sort(key=lambda x:(x['match']['score'],x['opportunity']['last_seen']),reverse=True)
    return {'generated_at':datetime.utcnow().isoformat()+'Z','mode':'deterministic','items':candidates[:5],'deadlines':dashboard(user,db)['deadlines'],'note':'Newness is not inferred from rediscovery. Demo records are synthetic.'}
@app.get('/api/analytics/overview')
def analytics(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Application).where(Application.user_id==user.id)).all()
    return {'total_tracked':len(rows),'by_status':{s:sum(1 for a in rows if a.status==s) for s in STATUSES},'applied_count':sum(1 for a in rows if a.applied_date or a.status in ('Applied','Assessment','Interview','Offer received','Rejected')),'interview_count':sum(1 for a in rows if a.status=='Interview'),'offer_count':sum(1 for a in rows if a.status=='Offer received'),'definition':'Counts reflect records in your tracker, not hiring probability or market-wide success rates.'}
@app.get('/api/export')
def export_data(user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=get_profile(user,db); rows=db.scalars(select(Application).where(Application.user_id==user.id)).all()
    return {'exported_at':datetime.utcnow().isoformat()+'Z','user':{'email':user.email,'display_name':user.display_name},'profile':profile_dict(p),'applications':[app_dict(a) for a in rows]}
@app.delete('/api/account')
def delete_account(user:User=Depends(current_user),db:Session=Depends(get_db)):
    db.delete(user); db.commit(); return {'deleted':True,'message':'Account, profile, and application records deleted. Shared opportunity catalogue records are retained without user notes.'}

@app.on_event('startup')
def startup():
    if DEMO_MODE and not SERPAPI_KEY:
        with SessionLocal() as db: seed_demo(db)
