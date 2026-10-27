import csv
import hashlib
import io
import json
import logging
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from PIL import Image
from typing import Literal
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .db import Session, User, Login, Profile, ModelVersion, Inspection, Review, Audit, now
from .security import current_user, roles, passwords, digest
from .storage import LocalStorage
from .vision import Detector, decode, MAX_BYTES

log = logging.getLogger(__name__)
storage = LocalStorage(os.getenv('STORAGE_DIR','data/private'))
detector = None
model_error = 'No model loaded'
inference_slots = threading.BoundedSemaphore(2)
login_attempts = defaultdict(deque)
login_lock = threading.Lock()

def uid(): return str(uuid.uuid4())
def audit(db, user, action, payload):
    db.add(Audit(id=uid(),actor_id=user.id,action=action,created_at=now(),payload=payload))

@asynccontextmanager
async def lifespan(app):
    global detector, model_error
    try:
        candidate = Detector(os.getenv('MODEL_DIR','models/bottle-v1'))
        with Session() as db:
            registered = db.get(ModelVersion, candidate.config['version'])
            if not registered or registered.config != candidate.config: raise ValueError('Model must be registered before activation')
        detector = candidate; model_error = None
    except Exception as ex:
        detector = None; model_error = str(ex); log.warning('Model unavailable: %s', ex)
    # One application process; a persisted processing marker means the previous run was interrupted.
    with Session.begin() as db:
        for row in db.scalars(select(Inspection)).all():
            if row.result.get('status') == 'processing':
                row.result = {'status':'error','suggestion':'needs_review','error':'Processing interrupted; submit a new inspection to rerun','warnings':[]}
                row.processed_at = now()
    yield

app = FastAPI(title='Quality Inspection',version='1.0.0',lifespan=lifespan)

@app.middleware('http')
async def request_safety(request, call_next):
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin = request.headers.get('origin')
        allowed = {request.url.netloc, *os.getenv('ALLOWED_ORIGIN_HOSTS','localhost:8000,127.0.0.1:8000,localhost:5173,127.0.0.1:5173').split(',')}
        if origin and urlparse(origin).netloc not in allowed:
            return Response('Cross-origin mutation denied',status_code=403)
    length = request.headers.get('content-length')
    if length and (not length.isdigit() or int(length)>MAX_BYTES+65536):
        return Response('Request exceeds 10 MiB image limit',status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

class Credentials(BaseModel):
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=256)

@app.post('/api/auth/login')
def login(body: Credentials, request: Request, response: Response):
    ip = request.client.host if request.client else 'unknown'
    with login_lock:
        if len(login_attempts)>4096: login_attempts.clear()
        attempts=login_attempts[ip]; cutoff=time.monotonic()-600
        while attempts and attempts[0]<cutoff: attempts.popleft()
        if len(attempts)>=10: raise HTTPException(429,'Too many attempts; wait 10 minutes')
        attempts.append(time.monotonic())
    with Session.begin() as db:
        user=db.scalar(select(User).where(User.username==body.username))
        if not user:
            passwords.hash(body.password)
            raise HTTPException(401,'Invalid username or password')
        if not passwords.verify(body.password,user.password): raise HTTPException(401,'Invalid username or password')
        token=secrets.token_urlsafe(32)
        db.add(Login(token_hash=digest(token),user_id=user.id,expires=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
    response.set_cookie('inspection_session',token,httponly=True,samesite='strict',secure=os.getenv('COOKIE_SECURE','false')=='true',max_age=28800)
    return {'username':user.username,'role':user.role}

@app.get('/api/auth/me')
def me(user=Depends(current_user)): return {'username':user.username,'role':user.role}

@app.post('/api/auth/logout')
def logout(request: Request,response: Response,user=Depends(current_user)):
    with Session.begin() as db:
        session=db.get(Login,digest(request.cookies.get('inspection_session','')))
        if session: db.delete(session)
    response.delete_cookie('inspection_session'); return {'ok':True}

@app.get('/api/health')
def health(): return {'status':'ok'}

@app.get('/api/profiles')
def profiles(user=Depends(current_user)):
    with Session() as db:
        return [{'id':p.id,'description':p.description,'model_available':detector is not None,
                 'model_version':detector.config['version'] if detector else None} for p in db.scalars(select(Profile))]

@app.get('/api/vocabulary')
def vocabulary(user=Depends(current_user)):
    return {'decisions':['normal','defect','needs_review'],'suggestions':['normal','suspected_defect','needs_review'], 'capture_methods':['upload','webcam']}

@app.get('/api/diagnostics')
def diagnostics(user=Depends(roles('admin'))):
    return {'model_error':model_error,'model':detector.config if detector else None}

def reviews_for(db,id): return db.scalars(select(Review).where(Review.inspection_id==id).order_by(Review.revision)).all()
def serialize(db,row,detail=False):
    reviews=reviews_for(db,row.id)
    latest=reviews[-1] if reviews else None
    value={k:getattr(row,k) for k in ['id','profile_id','model_version','product','batch','capture_method','captured_at','submitted_at','processed_at','width','height','source_hash','result','review_revision','deleted_at']}
    value['review_status']='reviewed' if latest else 'pending'
    value['final_decision']=latest.decision if latest else None
    value['reviewed_at']=latest.created_at if latest else None
    if detail: value['reviews']=[{k:getattr(r,k) for k in ['id','decision','reason','reviewer_name','created_at','revision']} for r in reviews]
    return value

@app.post('/api/inspections',status_code=201)
def inspect(file: UploadFile=File(...), profile: str=Form('bottle'), product: str=Form('',max_length=120),
            batch: str=Form('',max_length=120), capture_method: Literal['upload','webcam']=Form('upload'),
            captured_at: datetime | None=Form(None), idempotency_key: str=Header(...,min_length=8,max_length=100),
            user=Depends(roles('admin','reviewer'))):
    if file.content_type not in {'image/png','image/jpeg','image/webp'}: raise HTTPException(415,'PNG, JPEG or WebP required')
    raw=file.file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise HTTPException(413,'Image exceeds 10 MiB')
    try: rgb=decode(raw)
    except ValueError as ex: raise HTTPException(422,str(ex))
    actual_mime = Image.MIME[Image.open(io.BytesIO(raw)).format]
    if actual_mime != file.content_type: raise HTTPException(415,'Declared MIME type does not match image content')
    if captured_at and captured_at.tzinfo is None: raise HTTPException(422,'Capture time requires timezone')
    capture=captured_at.astimezone(timezone.utc).isoformat() if captured_at else None
    source_hash=hashlib.sha256(raw).hexdigest()
    request_hash=hashlib.sha256(json.dumps([source_hash,profile,product,batch,capture_method,capture]).encode()).hexdigest()
    key=user.id+':'+idempotency_key
    with Session() as db:
        if not db.get(Profile,profile): raise HTTPException(422,'Unsupported inspection profile')
        existing=db.scalar(select(Inspection).where(Inspection.idempotency_key==key))
        if existing:
            if existing.request_hash!=request_hash: raise HTTPException(409,'Idempotency key used for a different request')
            return serialize(db,existing,True)
        row=Inspection(id=uid(),idempotency_key=key,submitted_by=user.id,request_hash=request_hash,source_hash=source_hash,
                       profile_id=profile,model_version=detector.config['version'] if detector else None,product=product,batch=batch,
                       capture_method=capture_method,captured_at=capture,submitted_at=now(),width=rgb.shape[1],height=rgb.shape[0],
                       result={'status':'processing','suggestion':'needs_review','warnings':[]},review_revision=0)
        db.add(row)
        try: db.commit()
        except IntegrityError:
            db.rollback(); row=db.scalar(select(Inspection).where(Inspection.idempotency_key==key))
            if not row or row.request_hash!=request_hash: raise HTTPException(409,'Conflicting submission')
            return serialize(db,row,True)
        try:
            storage.write(row.id+'.source',raw)
            if detector is None: raise RuntimeError('Model unavailable; ask an administrator to register a model')
            with inference_slots:
                prediction=detector.predict(rgb)
                h,w=rgb.shape[:2]; ratio=min(1,1024/max(h,w))
                storage.write(row.id+'.heat.png',detector.heatmap(prediction.pop('map'),(max(1,int(w*ratio)),max(1,int(h*ratio)))))
            row.result={'status':'complete',**prediction,'threshold':detector.config['threshold'],
                        'review_band_fraction':.9,'preprocessing':detector.config['preprocessing'],
                        'artifact_sha256':detector.config['artifact_sha256'],'mime':file.content_type}
        except Exception:
            log.exception('Inspection %s failed',row.id)
            row.result={'status':'error','suggestion':'needs_review','error':'Model unavailable' if detector is None else 'Inference or storage failed', 'warnings':[],'mime':file.content_type}
        row.processed_at=now(); db.commit()
        return serialize(db,row,True)

def filtered(db,q='',batch='',product='',profile='',review='',suggestion='',date_from=None,date_to=None):
    statement=select(Inspection).where(Inspection.deleted_at.is_(None)).order_by(Inspection.submitted_at.desc())
    if q: statement=statement.where((Inspection.product.contains(q,autoescape=True)) | (Inspection.batch.contains(q,autoescape=True)) | (Inspection.id.contains(q,autoescape=True)))
    if batch: statement=statement.where(Inspection.batch==batch)
    if product: statement=statement.where(Inspection.product==product)
    if profile: statement=statement.where(Inspection.profile_id==profile)
    if date_from: statement=statement.where(Inspection.submitted_at>=date_from.isoformat())
    if date_to: statement=statement.where(Inspection.submitted_at<(date_to+timedelta(days=1)).isoformat())
    # A bounded single-organization prototype; pagination happens after the review filter.
    values=[serialize(db,row) for row in db.scalars(statement)]
    if review: values=[r for r in values if r['review_status']==review]
    if suggestion: values=[r for r in values if r['result'].get('suggestion')==suggestion]
    return values

class Filters(BaseModel):
    q: str=Field('',max_length=120)
    batch: str=Field('',max_length=120)
    product: str=Field('',max_length=120)
    profile: str=Field('',max_length=40)
    review: Literal['','pending','reviewed']=''
    suggestion: Literal['','normal','suspected_defect','needs_review']=''
    date_from: date | None=None
    date_to: date | None=None

def get_filters(q: str='',batch: str='',product: str='',profile: str='',review: Literal['','pending','reviewed']='',
                suggestion: Literal['','normal','suspected_defect','needs_review']='',date_from: date|None=None,date_to: date|None=None):
    return dict(q=q,batch=batch,product=product,profile=profile,review=review,suggestion=suggestion,date_from=date_from,date_to=date_to)

@app.get('/api/inspections')
def history(filters=Depends(get_filters),offset: int=Query(0,ge=0),limit: int=Query(50,ge=1,le=100),user=Depends(current_user)):
    with Session() as db:
        values=filtered(db,**filters)
        return {'items':values[offset:offset+limit],'total':len(values), 'counts':{
            'inspected':len(values),'pending':sum(r['review_status']=='pending' for r in values),
            'suspected_defective':sum(r['result'].get('suggestion')=='suspected_defect' for r in values),
            'human_normal':sum(r['final_decision']=='normal' for r in values),
            'human_defect':sum(r['final_decision']=='defect' for r in values),
            'human_needs_review':sum(r['final_decision']=='needs_review' for r in values),
            'reviewed':sum(r['review_status']=='reviewed' for r in values)}}

def safe_csv(value):
    value='' if value is None else str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value

@app.get('/api/export.csv')
def export(filters=Depends(get_filters),user=Depends(roles('admin','reviewer'))):
    with Session() as db:
        values=filtered(db,**filters)
        audit(db,user,'csv_export',{'filters':{k:str(v) for k,v in filters.items()},'count':len(values)}); db.commit()
    buf=io.StringIO(); writer=csv.writer(buf)
    fields=['id','product','batch','profile_id','model_version','source_hash','capture_method','captured_at','submitted_at','processed_at','suggestion','score','threshold','status','review_status','final_decision','reviewed_at']
    writer.writerow(fields)
    for row in values:
        flat={**row,**row['result']}; writer.writerow([safe_csv(flat.get(k)) for k in fields])
    return Response(buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=inspections.csv'})

@app.get('/api/inspections/{id}')
def detail(id: str,user=Depends(current_user)):
    with Session() as db:
        row=db.get(Inspection,id)
        if not row: raise HTTPException(404,'Inspection not found')
        return serialize(db,row,True)

@app.get('/api/inspections/{id}/image/{kind}')
def image(id: str,kind: Literal['original','heatmap'],user=Depends(current_user)):
    with Session() as db:
        row=db.get(Inspection,id)
        if not row or row.deleted_at: raise HTTPException(404,'Image not found')
        path=storage.path(id+('.source' if kind=='original' else '.heat.png'))
        if not path.is_file(): raise HTTPException(404,'Image unavailable')
        return FileResponse(path,media_type=row.result.get('mime','image/png') if kind=='original' else 'image/png')

class ReviewBody(BaseModel):
    decision: Literal['normal','defect','needs_review']
    reason: str=Field(min_length=3,max_length=2000)
    expected_revision: int=Field(ge=0)

@app.post('/api/inspections/{id}/reviews')
def review(id: str,body: ReviewBody,user=Depends(roles('admin','reviewer'))):
    if not body.reason.strip() or len(body.reason.strip())<3: raise HTTPException(422,'A meaningful reason is required')
    with Session.begin() as db:
        row=db.get(Inspection,id)
        if not row or row.deleted_at: raise HTTPException(404,'Inspection not found')
        if row.result['status']=='processing': raise HTTPException(409,'Inspection is still processing')
        change=db.execute(update(Inspection).where(Inspection.id==id,Inspection.review_revision==body.expected_revision).values(review_revision=body.expected_revision+1))
        if change.rowcount!=1: raise HTTPException(409,'Another reviewer changed this inspection; refresh')
        db.add(Review(id=uid(),inspection_id=id,reviewer_id=user.id,reviewer_name=user.username,
                      decision=body.decision,reason=body.reason.strip(),created_at=now(),revision=body.expected_revision+1))
        audit(db,user,'review',{'inspection_id':id,'revision':body.expected_revision+1})
    return detail(id,user)

class DeleteBody(BaseModel): reason: str=Field(min_length=3,max_length=2000)
@app.delete('/api/inspections/{id}')
def delete(id: str,body: DeleteBody,user=Depends(roles('admin'))):
    with Session.begin() as db:
        row=db.get(Inspection,id)
        if not row: raise HTTPException(404,'Inspection not found')
        if row.result['status']=='processing': raise HTTPException(409,'Wait for processing to finish')
        storage.delete(id+'.source'); storage.delete(id+'.heat.png')
        row.deleted_at=now()
        # Scrub free-form identifying content; preserve immutable technical evidence and audit decisions.
        row.product=''; row.batch=''
        audit(db,user,'delete_images',{'inspection_id':id,'reason':body.reason})
    return {'deleted':id,'policy':'Images and product/batch removed; technical result and review audit retained'}

@app.post('/api/feedback/export')
def feedback(user=Depends(roles('admin'))):
    # Exclude official test images by content hash. This export is candidate labels, never a model update.
    manifest=Path(os.getenv('DATASET_MANIFEST','models/dataset-manifest.json'))
    if not manifest.exists(): raise HTTPException(409,'Dataset manifest is required to exclude benchmark test examples')
    excluded={e['sha256'] for e in json.loads(manifest.read_text()) if '/test/' in e['path']}
    with Session.begin() as db:
        rows=filtered(db,review='reviewed')
        candidates=[r for r in rows if r['source_hash'] not in excluded]
        version=uid()
        payload={'version':version,'created_at':now(),'purpose':'Candidate labels; not automatically trained or activated',
                 'excluded_official_test':len(rows)-len(candidates),'items':candidates}
        storage.write('feedback-'+version+'.json',json.dumps(payload,indent=2).encode())
        audit(db,user,'feedback_export',{'version':version,'count':len(candidates)})
    return payload

class NewUser(BaseModel):
    username: str=Field(min_length=1,max_length=80)
    password: str=Field(min_length=12,max_length=256)
    role: Literal['admin','reviewer','viewer']
@app.post('/api/users',status_code=201)
def create_user(body: NewUser,user=Depends(roles('admin'))):
    with Session.begin() as db:
        if db.scalar(select(User).where(User.username==body.username)): raise HTTPException(409,'Username exists')
        db.add(User(id=uid(),username=body.username,password=passwords.hash(body.password),role=body.role))
        audit(db,user,'create_user',{'username':body.username,'role':body.role})
    return {'username':body.username,'role':body.role}

# Production frontend is served same-origin. API routes are registered first.
dist=Path('frontend/dist')
if dist.is_dir(): app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
