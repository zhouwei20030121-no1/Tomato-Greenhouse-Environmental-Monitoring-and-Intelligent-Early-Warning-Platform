import json, threading
from datetime import datetime,timedelta
import numpy as np
import pandas as pd
import torch
from torch import nn
from . import db,data
from .config import DATA

torch.set_num_threads(4)
LOCK=threading.RLock()
class ClimateGRU(nn.Module):
    def __init__(self):
        super().__init__();self.gru=nn.GRU(6,32,batch_first=True);self.head=nn.Linear(32,12)
    def forward(self,x):
        h,_=self.gru(x);return self.head(h[:,-1]).reshape(-1,6,2)

def make_features(f,mean,std):
    values=f[['temperature','humidity']].to_numpy(dtype=np.float32)
    hours=f.index.hour.to_numpy()+f.index.minute.to_numpy()/60
    return np.column_stack(((values-mean)/std,np.sin(hours*2*np.pi/24),np.cos(hours*2*np.pi/24),f[['maskT','maskRH']].to_numpy())).astype(np.float32)

def training_frames(cutoff,selection_cutoff,greenhouse_id='GH1'):
    stats=db.rows("SELECT r.node_id,COUNT(*) n FROM readings r JOIN nodes n ON n.id=r.node_id WHERE n.greenhouse_id=? AND r.event_time<=? AND r.quality='valid' GROUP BY r.node_id ORDER BY COUNT(*) DESC LIMIT 10",(greenhouse_id,selection_cutoff))
    result={}
    for x in stats:
        rr=db.rows('SELECT event_time,temperature,humidity,quality FROM readings WHERE node_id=? AND event_time<=? ORDER BY event_time',(x['node_id'],cutoff))
        f=pd.DataFrame(rr);f.event_time=pd.to_datetime(f.event_time);f=f.set_index('event_time');f.loc[f.quality!='valid',['temperature','humidity']]=np.nan
        f=f[['temperature','humidity']].resample('5min',label='right',closed='right').last()
        f['maskT']=f.temperature.notna().astype(float);f['maskRH']=f.humidity.notna().astype(float)
        f['targetT']=f.temperature;f['targetRH']=f.humidity
        f[['temperature','humidity']]=f[['temperature','humidity']].ffill(limit=1)
        result[x['node_id']]=f
    return result

def windows(frames,start,end,mean,std,limit,seed):
    rng=np.random.default_rng(seed);xx=[];yy=[];mm=[]
    per=max(100,limit//max(1,len(frames)))
    for f in frames.values():
        f=f.loc[(f.index>=start)&(f.index<=end)]
        if len(f)<30:continue
        features=make_features(f,mean,std);targets=f[['targetT','targetRH']].to_numpy(dtype=np.float32)
        masks=f[['maskT','maskRH']].to_numpy()
        starts=rng.permutation(max(0,len(f)-29));added=0
        for k in starts:
            x=features[k:k+24];y=targets[k+24:k+30];m=np.isfinite(y)
            if not np.isfinite(x).all() or masks[k:k+24].mean()<.8 or m.mean()<.8:continue
            xx.append(x);yy.append(np.nan_to_num((y-mean)/std));mm.append(m.astype(np.float32));added+=1
            if added>=per:break
    if len(xx)<30:raise ValueError('有效窗口不足；请调整节点覆盖或训练时间范围')
    return tuple(torch.tensor(np.stack(v),dtype=torch.float32) for v in (xx,yy,mm))

def train(j,epochs=12,greenhouse_id='GH1'):
    try:
        torch.manual_seed(42);np.random.seed(42)
        bounds=data.source_bounds(greenhouse_id)
        if not bounds['start']:raise ValueError('请先导入真实数据')
        start=datetime.fromisoformat(bounds['start']);actual_end=datetime.fromisoformat(bounds['end'])
        if greenhouse_id!='GH1':
            # Some GH2 nodes contain sparse June records before the July rollout.
            # Keep them as observations, but start model scope at multi-node coverage.
            total=db.one('SELECT COUNT(*) n FROM nodes WHERE greenhouse_id=?',(greenhouse_id,))['n']
            covered=db.one("SELECT day,COUNT(*) coverage FROM (SELECT substr(r.event_time,1,10) day,r.node_id FROM readings r JOIN nodes n ON n.id=r.node_id WHERE n.greenhouse_id=? AND r.quality='valid' GROUP BY day,r.node_id HAVING COUNT(*)>=6) GROUP BY day HAVING COUNT(*)>=? ORDER BY day LIMIT 1",(greenhouse_id,max(1,(total+1)//2)))
            if not covered:raise ValueError('当前温室尚无足够多节点覆盖的训练时段')
            start=datetime.fromisoformat(covered['day'])
        # The initial model scope is the first 70 days; the default June 25 case is held out.
        end=min(actual_end,start+timedelta(days=70));duration=end-start
        train_end=start+duration*.6;val_end=start+duration*.8
        db.progress(j,3,'整理首70天、覆盖良好的真实节点窗口')
        frames=training_frames(end.isoformat(),train_end.isoformat(),greenhouse_id)
        base=np.concatenate([f.loc[f.index<=train_end,['targetT','targetRH']].to_numpy() for f in frames.values()])
        mean=np.nanmean(base,axis=0).astype(np.float32);std=np.nanstd(base,axis=0).astype(np.float32);std=np.maximum(std,.1)
        tr=windows(frames,start,train_end,mean,std,6000,42)
        va=windows(frames,train_end+timedelta(seconds=1),val_end,mean,std,1200,43)
        te=windows(frames,val_end+timedelta(seconds=1),end,mean,std,1200,44)
        net=ClimateGRU();opt=torch.optim.Adam(net.parameters(),lr=.003)
        best=float('inf');patience=0;best_state=None;history=[]
        for epoch in range(epochs):
            net.train();order=torch.randperm(len(tr[0]));losses=[]
            for ids in order.split(256):
                pred=net(tr[0][ids]);mask=tr[2][ids];loss=((pred-tr[1][ids]).square()*mask).sum()/mask.sum().clamp_min(1)
                opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(net.parameters(),2);opt.step();losses.append(float(loss.detach()))
            net.eval()
            with torch.no_grad():vp=net(va[0]);vl=float(((vp-va[1]).square()*va[2]).sum()/va[2].sum())
            history.append({'epoch':epoch+1,'train_loss':round(float(np.mean(losses)),5),'val_loss':round(vl,5)})
            if vl<best-1e-5:best=vl;best_state={k:v.detach().clone() for k,v in net.state_dict().items()};patience=0
            else:patience+=1
            db.progress(j,15+(epoch+1)/epochs*76,f'GRU训练 {epoch+1}/{epochs}，验证损失 {vl:.4f}')
            if patience>=4:break
        net.load_state_dict(best_state);net.eval()
        with torch.no_grad():pred=net(te[0]).numpy()*std+mean
        actual=te[1].numpy()*std+mean;mask=te[2].numpy()
        mae=(np.abs(pred-actual)*mask).sum(axis=(0,1))/mask.sum(axis=(0,1))
        m= {'greenhouse_id':greenhouse_id,'temperature_mae':round(float(mae[0]),3),'humidity_mae':round(float(mae[1]),3),'train_windows':len(tr[0]),'validation_windows':len(va[0]),'held_out_windows':len(te[0]),'nodes':list(frames),'history':history,'scope_start':start.isoformat(),'scope_end':end.isoformat(),'seed':42,'actual_epochs':len(history)}
        model_id='gru-'+db.uid();path=DATA/(model_id+'.pt')
        torch.save({'state':best_state,'mean':mean.tolist(),'std':std.tolist(),'train_end':train_end.isoformat(),'val_end':val_end.isoformat(),'metrics':m},path)
        with db.connect() as c:
            c.execute("UPDATE model_versions SET status='archived' WHERE status='active' AND greenhouse_id=?",(greenhouse_id,))
            c.execute('INSERT INTO model_versions(id,trained_at,train_end,val_end,feature_spec,metrics,path,status,greenhouse_id) VALUES(?,?,?,?,?,?,?,?,?)',(model_id,db.now(),train_end.isoformat(),val_end.isoformat(),db.dumps({'input':[24,6],'output':[6,2],'hidden':32,'features':['T','RH','sin_hour','cos_hour','maskT','maskRH']}),db.dumps(m),str(path),'active',greenhouse_id))
        SERVICE.reload(greenhouse_id);db.progress(j,100,'GRU训练完成，已激活真实权重','done',m)
    except Exception as e:db.progress(j,0,f'训练未完成：{e}','failed')

class ForecastService:
    def __init__(self):self.states={};self.cache={}
    def reload(self,greenhouse_id=None):
        with LOCK:
            gids=[greenhouse_id] if greenhouse_id else [r['id'] for r in db.rows('SELECT id FROM greenhouses')]
            for gid in gids:
                meta=db.one("SELECT * FROM model_versions WHERE status='active' AND greenhouse_id=? ORDER BY trained_at DESC LIMIT 1",(gid,))
                if not meta:self.states.pop(gid,None);continue
                weights=torch.load(meta['path'],map_location='cpu',weights_only=True)
                net=ClimateGRU();net.load_state_dict(weights['state']);net.eval()
                self.states[gid]=(net,meta,np.array(weights['mean'],dtype=np.float32),np.array(weights['std'],dtype=np.float32))
            self.cache={}
    def predict(self,node,cursor):
        with LOCK:
            gid=db.node_greenhouse(node)
            if gid not in self.states:self.reload(gid)
            if gid not in self.states:return {'status':'paused','reason':'尚未训练GRU，请在数据设置中启动训练','points':[]}
            net,meta,mean,std=self.states[gid]
            if cursor<=meta['val_end']:return {'status':'paused','reason':'该回放时间处于训练/验证期；请跳转到'+meta['val_end'][:10]+'之后','model_id':meta['id'],'points':[]}
            key=(node,cursor,meta['id'])
            if key in self.cache:return self.cache[key]
            f=data.frame(node,cursor,2)
            if len(f)!=24 or f[['temperature','humidity']].isna().any().any() or f[['maskT','maskRH']].to_numpy().mean()<.8:
                return {'status':'paused','reason':'过去2小时存在长缺口或原始缺失比例超过20%','model_id':meta['id'],'points':[]}
            x=make_features(f,mean,std)
            with torch.no_grad():pred=net(torch.tensor(x).unsqueeze(0)).numpy()[0]*std+mean
            points=[];issued=f.index[-1]
            for k,(t,rh) in enumerate(pred):
                t=float(t);rh=float(rh)
                points.append({'time':(issued+pd.Timedelta(minutes=5*(k+1))).isoformat(),'temperature':round(t,3),'humidity':round(rh,3),'vpd':data.vpd(t,rh)})
            with db.connect() as c:c.executemany('INSERT OR IGNORE INTO predictions(node_id,model_id,issued_at,target_time,temperature,humidity,vpd) VALUES(?,?,?,?,?,?,?)',[(node,meta['id'],issued.isoformat(),v['time'],v['temperature'],v['humidity'],v['vpd']) for v in points])
            result={'status':'ready','model_id':meta['id'],'issued_at':issued.isoformat(),'points':points,'reason':None};self.cache[key]=result
            if len(self.cache)>500:self.cache.pop(next(iter(self.cache)))
            return result
SERVICE=ForecastService()
