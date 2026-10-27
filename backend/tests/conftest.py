import os
import tempfile
from pathlib import Path
import pytest
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp())/'test.db')
os.environ['STORAGE_DIR']=tempfile.mkdtemp()
from backend.app.db import Base, engine, Session, User, Profile, ModelVersion, now
from backend.app.security import passwords
from backend.app.vision import Detector
from backend.app.main import app, login_attempts
from fastapi.testclient import TestClient

@pytest.fixture()
def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    model=Detector('models/bottle-v1')
    with Session.begin() as db:
        db.add(Profile(id='bottle',description='Bottle benchmark'))
        db.flush()
        db.add(ModelVersion(id=model.config['version'],profile_id='bottle',config=model.config,registered_at=now()))
        for role in ['admin','reviewer','viewer']:
            db.add(User(id=role,username=role,password=passwords.hash('testing-only-password'),role=role))
    login_attempts.clear()
    with TestClient(app) as c:
        yield c

def sign_in(client,role='reviewer'):
    response=client.post('/api/auth/login',json={'username':role,'password':'testing-only-password'})
    assert response.status_code==200,response.text

def upload(client,path='demo/broken_large-000.png',key='test-upload-0001',**extra):
    return client.post('/api/inspections',files={'file':('bottle.png',Path(path).read_bytes(),'image/png')},data={'profile':'bottle',**extra},headers={'Idempotency-Key':key})
