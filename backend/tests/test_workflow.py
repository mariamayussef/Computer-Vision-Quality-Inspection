import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from backend.app.vision import Detector, decode, MAX_BYTES
from backend.app.db import Session, Inspection
from backend.app.main import app
import backend.app.main as application
from conftest import sign_in, upload

def test_real_workflow_correction_audit_export_restart(client):
    sign_in(client)
    response=upload(client,product='BTL-001',batch='LOT-024')
    assert response.status_code==201,response.text
    row=response.json();id=row['id'];original=dict(row['result'])
    assert original['status']=='complete' and isinstance(original['score'],float)
    assert client.get(f'/api/inspections/{id}/image/heatmap').status_code==200
    decision='normal' if original['suggestion']=='suspected_defect' else 'defect'
    review=client.post(f'/api/inspections/{id}/reviews',json={'decision':decision,'reason':'Operator checked visible rim','expected_revision':0})
    assert review.status_code==200,review.text
    result=review.json();assert result['result']==original;assert result['final_decision']==decision
    assert result['reviews'][0]['reviewer_name']=='reviewer'
    conflict=client.post(f'/api/inspections/{id}/reviews',json={'decision':'needs_review','reason':'Second assessment','expected_revision':0})
    assert conflict.status_code==409
    reviewed=client.post(f'/api/inspections/{id}/reviews',json={'decision':'needs_review','reason':'Request a closer photograph','expected_revision':1})
    assert reviewed.status_code==200 and len(reviewed.json()['reviews'])==2
    exported=client.get('/api/export.csv?batch=LOT-024&review=reviewed')
    assert exported.status_code==200 and id in exported.text and 'needs_review' in exported.text
    assert id not in client.get('/api/export.csv?batch=OTHER').text
    assert client.get('/api/inspections?batch=LOT-024').json()['counts']['reviewed']==1
    # A fresh app lifespan against the same DB and storage must retain evidence and session.
    with TestClient(app) as restarted:
        restarted.cookies.update(client.cookies)
        persisted=restarted.get(f'/api/inspections/{id}').json()
        assert persisted['result']==original and len(persisted['reviews'])==2
        assert restarted.get(f'/api/inspections/{id}/image/original').status_code==200

def test_idempotency_and_payload_conflict(client):
    sign_in(client)
    first=upload(client).json();second=upload(client).json()
    assert first['id']==second['id']
    assert client.get('/api/inspections').json()['total']==1
    assert upload(client,batch='different').status_code==409
    # A new intentional inspection is allowed for the same product image.
    third=upload(client,key='intentional-second').json()
    assert third['id']!=first['id'] and third['result']['score']==first['result']['score']

def test_auth_roles_and_private_files(client):
    assert client.get('/api/inspections').status_code==401
    assert client.get('/api/export.csv').status_code==401
    sign_in(client,'viewer')
    assert client.get('/api/profiles').status_code==200
    assert upload(client).status_code==403
    assert client.get('/api/export.csv').status_code==403
    assert client.post('/api/feedback/export').status_code==403
    assert client.get('/api/diagnostics').status_code==403
    assert client.post('/api/users',json={'username':'x','password':'long-test-password','role':'admin'}).status_code==403
    sign_in(client);row=upload(client).json()
    assert client.request('DELETE','/api/inspections/'+row['id'],json={'reason':'Remove input'}).status_code==403
    assert client.get('/api/diagnostics').status_code==403
    client.post('/api/auth/logout')
    assert client.get('/api/inspections/'+row['id']+'/image/original').status_code==401

def test_bad_images_missing_model_and_inference_failure(client,monkeypatch):
    sign_in(client)
    def raw_upload(raw,mime='image/png'):
        return client.post('/api/inspections',files={'file':('input.png',raw,mime)},headers={'Idempotency-Key':'invalid-test-key'})
    assert raw_upload(b'not an image').status_code==422
    assert raw_upload(b'<svg></svg>','image/svg+xml').status_code==415
    assert raw_upload(b'x'*(MAX_BYTES+1)).status_code==413
    tiny=io.BytesIO();Image.new('RGB',(32,32)).save(tiny,format='PNG')
    assert raw_upload(tiny.getvalue()).status_code==422
    huge=io.BytesIO();Image.new('L',(5000,5000)).save(huge,format='PNG')
    assert raw_upload(huge.getvalue()).status_code==422
    assert client.get('/api/inspections').json()['total']==0
    monkeypatch.setattr(application,'detector',None)
    missing=upload(client,key='missing-model-key').json()
    assert missing['result']['status']=='error' and missing['result']['suggestion']=='needs_review'
    class Broken:
        config=Detector('models/bottle-v1').config
        def predict(self,_): raise RuntimeError('simulated failure')
    monkeypatch.setattr(application,'detector',Broken())
    failed=upload(client,key='inference-failure-key').json()
    assert failed['result']['status']=='error' and failed['result']['suggestion']=='needs_review'

def test_unsupported_profile_and_timestamp(client):
    sign_in(client)
    response=client.post('/api/inspections',files={'file':('b.png',Path('demo/good-000.png').read_bytes(),'image/png')},data={'profile':'label-check'},headers={'Idempotency-Key':'unsupported-category'})
    assert response.status_code==422
    assert upload(client,captured_at='2026-10-27T09:00:00').status_code==422

def test_quality_reproducibility_and_checkpoint_integrity():
    model=Detector('models/bottle-v1');rgb=decode(Path('demo/good-000.png').read_bytes())
    first=model.predict(rgb);second=model.predict(rgb)
    assert first['score']==second['score'] and np.array_equal(first['map'],second['map'])
    for rgb in [np.zeros((128,128,3),dtype=np.uint8),np.full((128,128,3),255,dtype=np.uint8)]:
        result=model.predict(rgb);assert result['warnings'] and result['suggestion']=='needs_review'
    import tempfile,shutil
    tmp=Path(tempfile.mkdtemp());shutil.copy('models/bottle-v1/config.json',tmp)
    (tmp/'normal_bank.npz').write_bytes(b'invalid')
    import pytest
    with pytest.raises(ValueError,match='checksum'):Detector(tmp)

def test_admin_retention_and_feedback_no_model_update(client):
    sign_in(client,'admin');row=upload(client).json();id=row['id']
    client.post('/api/inspections/'+id+'/reviews',json={'decision':'defect','reason':'Visible glass damage','expected_revision':0})
    before=application.detector.config.copy()
    response=client.post('/api/feedback/export');assert response.status_code==200
    assert response.json()['excluded_official_test']==1 and response.json()['items']==[]
    assert application.detector.config==before
    removed=client.request('DELETE','/api/inspections/'+id,json={'reason':'Retention request'})
    assert removed.status_code==200
    assert client.get('/api/inspections/'+id+'/image/original').status_code==404
    assert client.get('/api/inspections').json()['total']==0
    detail=client.get('/api/inspections/'+id).json()
    assert detail['deleted_at'] and detail['result']==row['result'] and len(detail['reviews'])==1

def test_csrf_and_csv_injection(client):
    sign_in(client)
    assert client.post('/api/auth/logout',headers={'Origin':'https://evil.example'}).status_code==403
    row=upload(client,product='=HYPERLINK("evil")',batch='batch').json()
    text=client.get('/api/export.csv').text
    assert "'=HYPERLINK" in text
    assert row['id'] in text

def test_concurrent_idempotent_uploads(client):
    sign_in(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:upload(client,key='concurrent-retry-key'),range(2)))
    assert all(r.status_code==201 for r in results)
    assert results[0].json()['id']==results[1].json()['id']
    rows=client.get('/api/inspections').json()
    assert rows['total']==1 and rows['items'][0]['result']['status']=='complete'

def test_interrupted_process_becomes_error_on_restart(client):
    sign_in(client);row=upload(client).json()
    with Session.begin() as db:
        record=db.get(Inspection,row['id']);record.result={'status':'processing','suggestion':'needs_review','warnings':[]}
    with TestClient(app) as restarted:
        restarted.cookies.update(client.cookies)
        actual=restarted.get('/api/inspections/'+row['id']).json()
        assert actual['result']['status']=='error' and actual['result']['suggestion']=='needs_review'
