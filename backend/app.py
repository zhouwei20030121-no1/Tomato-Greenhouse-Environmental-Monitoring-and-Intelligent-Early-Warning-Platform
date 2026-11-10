import asyncio,json,threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from fastapi import FastAPI,HTTPException,Query,Request,Response,Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from . import db,data,forecast,events,replay,rag,auth,catalog
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

def greenhouse_scope(greenhouse_id:str=Query('GH1')):
    try:catalog.get(greenhouse_id)
    except ValueError:raise HTTPException(404,'温室不存在')
    return greenhouse_id

def check_event(event_id,greenhouse_id):
    row=db.one('SELECT a.id FROM alerts a JOIN nodes n ON n.id=a.node_id WHERE a.id=? AND n.greenhouse_id=?',(event_id,greenhouse_id))
    if not row:raise HTTPException(404,'当前温室没有这条事件')

def check_node(node,greenhouse_id='GH1'):
    if node and not db.one('SELECT id FROM nodes WHERE id=? AND greenhouse_id=?',(node,greenhouse_id)):raise HTTPException(404,'节点不存在')
def safe_call(fun,*args):
    try:return fun(*args)
    except ValueError as e:raise HTTPException(409,str(e)) from None
def run_import(j,greenhouse_id='GH1'):
    data.import_source(j,greenhouse_id)
    if db.one('SELECT status FROM jobs WHERE id=?',(j,))['status']=='done':replay.process(True,greenhouse_id)

@app.get('/api/health')
def health():return {'ok':True,'service':'greenhouse-platform','api_configured':bool(API_KEY),'llm_base':API_BASE,'configured_model':API_MODEL,'source':'real_dataset_replay','simulation':True}
@app.get('/api/greenhouses')
def greenhouses():
    return [catalog.public(gid)|{'bounds':data.source_bounds(gid)} for gid in catalog.DEPLOYMENTS]

@app.get('/api/overview')
def overview(greenhouse_id:str=Depends(greenhouse_scope)):
    s=replay.state(greenhouse_id);nodes=data.snapshot(s['cursor'],greenhouse_id);valid=[n for n in nodes if n['state'] in ('normal','warning')]
    def avg(k):
        vs=[n[k] for n in valid if n[k] is not None];return round(sum(vs)/len(vs),2) if vs else None
    alerts=events.list_alerts(s['session_id'],greenhouse_id);model=db.one("SELECT id,trained_at,status FROM model_versions WHERE status='active' AND greenhouse_id=?",(greenhouse_id,))
    return {'greenhouse':catalog.public(greenhouse_id),'replay':s,'nodes':nodes,'metrics':{'temperature':avg('temperature'),'humidity':avg('humidity'),'vpd':avg('vpd'),'fresh_nodes':len(valid),'total_nodes':len(nodes),'open_alerts':sum(a['status']!='closed' for a in alerts)},'alerts':alerts[:8],'model':model,'data_ready':bool(db.one("SELECT id FROM sources WHERE status='ready' AND greenhouse_id=?",(greenhouse_id,)))}
@app.get('/api/nodes')
def nodes(greenhouse_id:str=Depends(greenhouse_scope)):return data.snapshot(replay.state(greenhouse_id)['cursor'],greenhouse_id)
@app.get('/api/nodes/{node_id}/series')
def series(node_id:str,hours:int=Query(8,ge=2,le=72),greenhouse_id:str=Depends(greenhouse_scope)):
    check_node(node_id,greenhouse_id);cursor=replay.state(greenhouse_id)['cursor'];return {'node_id':node_id,'cursor':cursor,'points':data.series(node_id,cursor,hours)}
@app.get('/api/forecast/{node_id}')
def predict(node_id:str,greenhouse_id:str=Depends(greenhouse_scope)):check_node(node_id,greenhouse_id);return forecast.SERVICE.predict(node_id,replay.state(greenhouse_id)['cursor'])
@app.get('/api/alerts')
def alerts(all_sessions:bool=False,greenhouse_id:str=Depends(greenhouse_scope)):return events.list_alerts(None if all_sessions else replay.state(greenhouse_id)['session_id'],greenhouse_id)
@app.post('/api/alerts/{event_id}/confirm')
def confirm(event_id:str,body:Note,greenhouse_id:str=Depends(greenhouse_scope)):
    check_event(event_id,greenhouse_id);return safe_call(events.confirm,event_id,body.note)
@app.post('/api/alerts/{event_id}/execute')
def execute(event_id:str,body:ExecuteInput,greenhouse_id:str=Depends(greenhouse_scope)):
    check_event(event_id,greenhouse_id);return safe_call(events.execute_event,event_id,body.action,body.command_id,body.note)
@app.post('/api/alerts/{event_id}/close')
def close(event_id:str,body:Note,greenhouse_id:str=Depends(greenhouse_scope)):
    check_event(event_id,greenhouse_id);return safe_call(events.close,event_id,body.note)
@app.post('/api/alerts/{event_id}/recommend')
def recommend(event_id:str,greenhouse_id:str=Depends(greenhouse_scope)):
    check_event(event_id,greenhouse_id)
    event=db.one('SELECT * FROM alerts WHERE id=?',(event_id,))
    return safe_call(rag.recommend,event,replay.state(greenhouse_id)['cursor'],greenhouse_id)

@app.get('/api/commands')
def commands(greenhouse_id:str=Depends(greenhouse_scope)):return db.rows('SELECT c.*,a.node_id FROM commands c JOIN alerts a ON a.id=c.event_id JOIN nodes n ON n.id=a.node_id WHERE n.greenhouse_id=? ORDER BY requested_at DESC LIMIT 100',(greenhouse_id,))
@app.get('/api/replay/state')
def replay_state(greenhouse_id:str=Depends(greenhouse_scope)):return replay.state(greenhouse_id)
@app.post('/api/replay/control')
def replay_control(body:ReplayInput,greenhouse_id:str=Depends(greenhouse_scope)):return safe_call(replay.control,body.action,body.cursor.isoformat(timespec='seconds') if body.cursor else None,body.speed,greenhouse_id)
@app.get('/api/settings')
def get_settings(greenhouse_id:str=Depends(greenhouse_scope)):return db.settings(greenhouse_id)
@app.put('/api/settings')
def put_settings(body:Thresholds,greenhouse_id:str=Depends(greenhouse_scope)):
    values=body.model_dump()
    for a,b in [('temperature_min','temperature_max'),('humidity_min','humidity_max'),('vpd_min','vpd_max')]:
        if values[a]>=values[b]:raise HTTPException(422,'参考下限必须小于上限')
    with db.connect() as c:
        for k,v in values.items():c.execute('UPDATE greenhouse_settings SET value_json=?,updated_at=? WHERE greenhouse_id=? AND key=?',(db.dumps(v),db.now(),greenhouse_id,k))
    data.snapshot.cache_clear();replay.process(True,greenhouse_id);return values
@app.get('/api/data/status')
def data_status(greenhouse_id:str=Depends(greenhouse_scope)):return data.status(greenhouse_id)
@app.post('/api/data/import')
def data_import(greenhouse_id:str=Depends(greenhouse_scope)):
    j,new=db.job('import',greenhouse_id)
    if new:threading.Thread(target=run_import,args=(j['id'],greenhouse_id),daemon=True).start()
    return j
@app.get('/api/jobs/{job_id}')
def job_status(job_id:str,greenhouse_id:str=Depends(greenhouse_scope)):
    j=db.one('SELECT * FROM jobs WHERE id=? AND greenhouse_id=?',(job_id,greenhouse_id))
    if not j:raise HTTPException(404,'任务不存在')
    return j
@app.get('/api/models')
def models(greenhouse_id:str=Depends(greenhouse_scope)):
    rr=db.rows('SELECT * FROM model_versions WHERE greenhouse_id=? ORDER BY trained_at DESC',(greenhouse_id,))
    for r in rr:r['metrics']=json.loads(r['metrics']);r['feature_spec']=json.loads(r['feature_spec']);r.pop('path',None)
    return {'models':rr,'job':db.one("SELECT * FROM jobs WHERE kind='train' AND greenhouse_id=? ORDER BY started_at DESC LIMIT 1",(greenhouse_id,))}
@app.post('/api/models/train')
def train_model(body:TrainInput,greenhouse_id:str=Depends(greenhouse_scope)):
    if not db.one("SELECT id FROM sources WHERE status='ready' AND greenhouse_id=?",(greenhouse_id,)):raise HTTPException(409,'请先完成真实数据导入')
    j,new=db.job('train',greenhouse_id)
    if new:threading.Thread(target=forecast.train,args=(j['id'],body.epochs,greenhouse_id),daemon=True).start()
    return j
@app.post('/api/assistant/ask')
def ask(body:AskInput,greenhouse_id:str=Depends(greenhouse_scope)):
    check_node(body.node_id,greenhouse_id)
    if body.event_id:check_event(body.event_id,greenhouse_id)
    return safe_call(rag.ask,body.question,body.node_id,replay.state(greenhouse_id)['cursor'],body.event_id,body.session_id,greenhouse_id)
@app.get('/api/knowledge')
def knowledge():return db.rows('SELECT id,title,url,license FROM knowledge_documents')
@app.get('/api/assistant/history')
def history(greenhouse_id:str=Depends(greenhouse_scope)):return db.rows('SELECT id,role,content,provider,created_at FROM chat_messages WHERE greenhouse_id=? ORDER BY created_at DESC LIMIT 15',(greenhouse_id,))
dist=ROOT/'frontend/dist'
if dist.is_dir():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{full_path:path}')
    def frontend(full_path:str):
        if full_path.startswith('api/'):raise HTTPException(404,'接口不存在')
        return FileResponse(dist/'index.html')

