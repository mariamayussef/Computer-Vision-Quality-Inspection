import argparse, getpass, os, sys, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alembic.config import Config
from alembic import command
from sqlalchemy import select
from backend.app.db import Session, User, Profile, now, ModelVersion
from backend.app.security import passwords
from backend.app.vision import Detector
p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
sub.add_parser('migrate')
u=sub.add_parser('user'); u.add_argument('username'); u.add_argument('--role',choices=['admin','reviewer','viewer'],default='reviewer')
sub.add_parser('register-model')
a=p.parse_args()
if a.command=='migrate':
    Path('data').mkdir(exist_ok=True); command.upgrade(Config('alembic.ini'),'head')
    with Session.begin() as db:
        if not db.get(Profile,'bottle'): db.add(Profile(id='bottle',description='Centered, top-down bottle images: broken rim/glass and contamination. Match benchmark lighting and framing. No label or assembly checks.'))
elif a.command=='user':
    if not 1 <= len(a.username) <= 80: raise SystemExit('Username must be 1–80 characters')
    password=os.getenv('INITIAL_PASSWORD') or getpass.getpass('New password (12+ characters): ')
    if len(password)<12: raise SystemExit('Password must be at least 12 characters')
    with Session.begin() as db:
        if db.scalar(select(User).where(User.username==a.username)): raise SystemExit('User already exists')
        db.add(User(id=str(uuid.uuid4()),username=a.username,password=passwords.hash(password),role=a.role))
    print('User created')
elif a.command=='register-model':
    model=Detector(os.getenv('MODEL_DIR','models/bottle-v1'))
    with Session.begin() as db:
        existing=db.get(ModelVersion,model.config['version'])
        if existing and existing.config!=model.config: raise SystemExit('Immutable version already registered; choose a new version')
        if not existing: db.add(ModelVersion(id=model.config['version'],profile_id='bottle',config=model.config,registered_at=now()))
    print('Model registered; MODEL_DIR selects it on the next application restart')
