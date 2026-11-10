import sqlite3, json, uuid
from datetime import datetime
from contextlib import contextmanager
from .config import DB_PATH, ROOT, DEFAULTS

def now(): return datetime.now().isoformat(timespec='seconds')
def uid(): return uuid.uuid4().hex[:16]
def dumps(x): return json.dumps(x,ensure_ascii=False,allow_nan=False)

@contextmanager
def connect():
    c=sqlite3.connect(DB_PATH,timeout=45)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=45000')
    try: yield c; c.commit()
    except Exception: c.rollback(); raise
    finally: c.close()

def init_db():
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL');c.executescript((ROOT/'backend/schema.sql').read_text('utf-8'))
        c.execute('INSERT OR IGNORE INTO greenhouses VALUES(?,?,?,?)',('GH1','番茄温室 01','比利时 · 公开历史记录','27个LoRaWAN节点；源时间无时区'))
        for n in range(16,43):c.execute('INSERT OR IGNORE INTO nodes VALUES(?,?,?,?)',(f'AF{n}','GH1',(n-16)%3,(n-16)//3))
        for k,v in DEFAULTS.items():c.execute('INSERT OR IGNORE INTO settings VALUES(?,?,?)',(k,dumps(v),now()))
        c.execute('INSERT OR IGNORE INTO replay_state VALUES(1,?,?,?,?,?)',('2020-06-25T13:45:00',60,0,'local',uid()))
        c.execute('UPDATE replay_state SET running=0')

def rows(sql,args=()):
    with connect() as c:return [dict(r) for r in c.execute(sql,args).fetchall()]
def one(sql,args=()):
    v=rows(sql,args);return v[0] if v else None
def execute(sql,args=()):
    with connect() as c:c.execute(sql,args)
def settings():return {r['key']:json.loads(r['value_json']) for r in rows('SELECT * FROM settings')}
def job(kind):
    old=one("SELECT * FROM jobs WHERE kind=? AND status IN ('queued','running')",(kind,))
    if old:return old,False
    j=uid();execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(j,kind,'queued',0,'准备开始','{}',now(),None))
    return one('SELECT * FROM jobs WHERE id=?',(j,)),True
def progress(j,p,message,status='running',result=None):
    execute('UPDATE jobs SET status=?,progress=?,message=?,result_json=?,finished_at=? WHERE id=?',
            (status,p,message,dumps(result or {}),now() if status in ('done','failed') else None,j))
