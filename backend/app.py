import asyncio,json,threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from fastapi import FastAPI,HTTPException,Query,Request,Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from . import db,data,forecast,events,replay,rag,auth
from .config import ROOT,API_KEY,API_BASE,API_MODEL,DEFAULTS

@asynccontextmanager
async def lifespan(app):
    db.init_db();auth.init_auth();rag.init_knowledge();replay.GATEWAY.start();forecast.SERVICE.reload()
    task=asyncio.create_task(replay.loop())
    yield
    task.cancel();replay.GATEWAY.stop()
    try:await task
    except asyncio.CancelledError:pass

app=FastAPI(title='Verdant · 番茄温室智能监测平台',version='1.0.0',lifespan=lifespan)
app.middleware('http')(auth.guard)
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173'],allow_methods=['GET','POST','PUT'],allow_headers=['Content-Type'])

class LoginInput(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=160)

@app.post('/api/auth/login')
def login(body:LoginInput,response:Response):
    result=auth.login(body.username,body.password)
    if not result:raise HTTPException(401,'用户名或密码错误')
    token,user=result;response.set_cookie(auth.COOKIE,token,httponly=True,samesite='strict',max_age=43200)
    return user
@app.get('/api/auth/me')
def current_user(request:Request):
    return {'user':auth.user_for(request)}
@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    import hashlib
    token=request.cookies.get(auth.COOKIE)
    if token:db.execute('DELETE FROM auth_sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(auth.COOKIE);return {'ok':True}

class ReplayInput(BaseModel):
    action:Literal['play','pause','seek','step','speed']
    cursor:datetime|None=None
    speed:float|None=None
class Note(BaseModel): note:str=Field(default='',max_length=1500)
class ExecuteInput(Note):
    action:Literal['ventilate','open_window','shade']
    command_id:str=Field(min_length=8,max_length=80)
class AskInput(BaseModel):
    question:str=Field(min_length=2,max_length=1200)
    node_id:str|None='AF16'
    event_id:str|None=None
    session_id:str=Field(default='default',max_length=80)
class TrainInput(BaseModel): epochs:int=Field(default=12,ge=2,le=40)
class Thresholds(BaseModel):
    temperature_min:float=Field(ge=-10,le=50)
    temperature_max:float=Field(ge=0,le=65)
    humidity_min:float=Field(ge=0,le=100)
    humidity_max:float=Field(ge=0,le=100)
    vpd_min:float=Field(ge=0,le=6)
    vpd_max:float=Field(ge=0,le=8)
    persistence:int=Field(ge=2,le=12)
    cooldown_minutes:int=Field(ge=1,le=120)
    freshness_minutes:int=Field(ge=5,le=120)

def check_node(node):
    if node and not db.one('SELECT id FROM nodes WHERE id=?',(node,)):raise HTTPException(404,'节点不存在')
def safe_call(fun,*args):
    try:return fun(*args)
    except ValueError as e:raise HTTPException(409,str(e)) from None
def run_import(j):
    data.import_source(j)
    if db.one('SELECT status FROM jobs WHERE id=?',(j,))['status']=='done':replay.process(True)

@app.get('/api/health')
def health():return {'ok':True,'service':'greenhouse-platform','api_configured':bool(API_KEY),'llm_base':API_BASE,'configured_model':API_MODEL,'source':'real_dataset_replay','simulation':True}
@app.get('/api/overview')
def overview():
    s=replay.state();nodes=data.snapshot(s['cursor']);valid=[n for n in nodes if n['state'] in ('normal','warning')]
    def avg(k):
        vs=[n[k] for n in valid if n[k] is not None];return round(sum(vs)/len(vs),2) if vs else None
    alerts=events.list_alerts(s['session_id']);model=db.one("SELECT id,trained_at,status FROM model_versions WHERE status='active'")
    return {'replay':s,'nodes':nodes,'metrics':{'temperature':avg('temperature'),'humidity':avg('humidity'),'vpd':avg('vpd'),'fresh_nodes':len(valid),'total_nodes':27,'open_alerts':sum(a['status']!='closed' for a in alerts)},'alerts':alerts[:8],'model':model,'data_ready':bool(db.one("SELECT id FROM sources WHERE status='ready'"))}
@app.get('/api/nodes')
def nodes():return data.snapshot(replay.state()['cursor'])
@app.get('/api/nodes/{node_id}/series')
def series(node_id:str,hours:int=Query(8,ge=2,le=72)):
    check_node(node_id);cursor=replay.state()['cursor'];return {'node_id':node_id,'cursor':cursor,'points':data.series(node_id,cursor,hours)}
@app.get('/api/forecast/{node_id}')
def predict(node_id:str):check_node(node_id);return forecast.SERVICE.predict(node_id,replay.state()['cursor'])
@app.get('/api/alerts')
def alerts(all_sessions:bool=False):return events.list_alerts(None if all_sessions else replay.state()['session_id'])
@app.post('/api/alerts/{event_id}/confirm')
def confirm(event_id:str,body:Note):return safe_call(events.confirm,event_id,body.note)
@app.post('/api/alerts/{event_id}/execute')
def execute(event_id:str,body:ExecuteInput):return safe_call(events.execute_event,event_id,body.action,body.command_id,body.note)
@app.post('/api/alerts/{event_id}/close')
def close(event_id:str,body:Note):return safe_call(events.close,event_id,body.note)
@app.get('/api/commands')
def commands():return db.rows('SELECT c.*,a.node_id FROM commands c JOIN alerts a ON a.id=c.event_id ORDER BY requested_at DESC LIMIT 100')
@app.get('/api/replay/state')
def replay_state():return replay.state()
@app.post('/api/replay/control')
def replay_control(body:ReplayInput):return safe_call(replay.control,body.action,body.cursor.isoformat(timespec='seconds') if body.cursor else None,body.speed)
@app.get('/api/settings')
def get_settings():return db.settings()
@app.put('/api/settings')
def put_settings(body:Thresholds):
    values=body.model_dump()
    for a,b in [('temperature_min','temperature_max'),('humidity_min','humidity_max'),('vpd_min','vpd_max')]:
        if values[a]>=values[b]:raise HTTPException(422,'参考下限必须小于上限')
    with db.connect() as c:
        for k,v in values.items():c.execute('UPDATE settings SET value_json=?,updated_at=? WHERE key=?',(db.dumps(v),db.now(),k))
    data.snapshot.cache_clear();replay.process(True);return values
@app.get('/api/data/status')
def data_status():return data.status()
@app.post('/api/data/import')
def data_import():
    j,new=db.job('import')
    if new:threading.Thread(target=run_import,args=(j['id'],),daemon=True).start()
    return j
@app.get('/api/jobs/{job_id}')
def job_status(job_id:str):
    j=db.one('SELECT * FROM jobs WHERE id=?',(job_id,))
    if not j:raise HTTPException(404,'任务不存在')
    return j
@app.get('/api/models')
def models():
    rr=db.rows('SELECT * FROM model_versions ORDER BY trained_at DESC')
    for r in rr:r['metrics']=json.loads(r['metrics']);r['feature_spec']=json.loads(r['feature_spec']);r.pop('path',None)
    return {'models':rr,'job':db.one("SELECT * FROM jobs WHERE kind='train' ORDER BY started_at DESC LIMIT 1")}
@app.post('/api/models/train')
def train_model(body:TrainInput):
    if not db.one("SELECT id FROM sources WHERE status='ready'"):raise HTTPException(409,'请先完成真实数据导入')
    j,new=db.job('train')
    if new:threading.Thread(target=forecast.train,args=(j['id'],body.epochs),daemon=True).start()
    return j
@app.post('/api/assistant/ask')
def ask(body:AskInput):
    check_node(body.node_id);return rag.ask(body.question,body.node_id,replay.state()['cursor'],body.event_id,body.session_id)
@app.get('/api/knowledge')
def knowledge():return db.rows('SELECT id,title,url,license FROM knowledge_documents')
@app.get('/api/assistant/history')
def history():return db.rows('SELECT id,role,content,provider,created_at FROM chat_messages ORDER BY created_at DESC LIMIT 15')
dist=ROOT/'frontend/dist'
if dist.is_dir():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{full_path:path}')
    def frontend(full_path:str):
        if full_path.startswith('api/'):raise HTTPException(404,'接口不存在')
        return FileResponse(dist/'index.html')

