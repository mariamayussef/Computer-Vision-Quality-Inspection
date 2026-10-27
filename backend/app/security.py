import hashlib
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from .db import Session, Login, User
passwords = PasswordHash.recommended()
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def current_user(request: Request):
    token = request.cookies.get('inspection_session', '')
    with Session() as db:
        session = db.get(Login, digest(token))
        if not session or session.expires <= datetime.now(timezone.utc).isoformat():
            raise HTTPException(401, 'Please sign in')
        return db.get(User, session.user_id)
def roles(*allowed):
    def check(user=Depends(current_user)):
        if user.role not in allowed: raise HTTPException(403, 'Your role cannot perform this action')
        return user
    return check
