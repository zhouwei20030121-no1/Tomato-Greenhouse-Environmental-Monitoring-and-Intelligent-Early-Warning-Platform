"""Local role-based login. Secrets and session tokens never reach version control."""
import hashlib,hmac,secrets,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse
from . import db
from .config import DATA

COOKIE='verdant_session'
def utc():return datetime.now(timezone.utc)
def password_hash(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),180000).hex()
def init_auth():
    accounts=[]
    with db.connect() as c:
        c.executescript('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,role TEXT NOT NULL,password_salt TEXT NOT NULL,password_hash TEXT NOT NULL); CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires_at TEXT NOT NULL);')
        for username,name,role,env in [('grower','温室管理员','grower','GROWER_PASSWORD'),('operator','系统维护员','operator','OPERATOR_PASSWORD')]:
            if c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone():continue
            password=os.getenv(env) or secrets.token_urlsafe(9);salt=secrets.token_hex(16)
            c.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',(db.uid(),username,name,role,salt,password_hash(password,salt)));accounts.append((username,name,password))
    if accounts:
        file=DATA/'初始账号.txt'
        with file.open('a',encoding='utf-8') as f:
            f.write('本机初始账号（仅本地保管，不上传GitHub）\n')
            for username,name,password in accounts:f.write(f'{name}：用户名 {username}，密码 {password}\n')
def login(username,password):
    r=db.one('SELECT * FROM users WHERE username=?',(username,))
    if not r or not hmac.compare_digest(password_hash(password,r['password_salt']),r['password_hash']):return None
    token=secrets.token_urlsafe(32);db.execute('INSERT INTO auth_sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),r['id'],(utc()+timedelta(hours=12)).isoformat()))
    return token,{k:r[k] for k in ['id','username','display_name','role']}
def user_for(request:Request):
    token=request.cookies.get(COOKIE)
    if not token:return None
    return db.one('SELECT u.id,u.username,u.display_name,u.role FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),utc().isoformat()))
OPERATOR_PATHS=['/api/data','/api/models/train','/api/jobs','/api/replay/control']
async def guard(request,call_next):
    path=request.url.path
    if path.startswith('/api/') and path not in ['/api/health','/api/auth/login','/api/auth/me','/api/auth/logout']:
        user=user_for(request)
        if not user:return JSONResponse({'detail':'请先登录'},status_code=401)
        request.state.user=user
        if user['role']!='operator' and any(path.startswith(prefix) for prefix in OPERATOR_PATHS):return JSONResponse({'detail':'该功能仅限系统维护员'},status_code=403)
        if user['role']!='grower' and (request.method=='PUT' and path=='/api/settings' or request.method=='POST' and path.startswith('/api/alerts/')):return JSONResponse({'detail':'环境参数和事件处理仅限温室管理员'},status_code=403)
    return await call_next(request)

