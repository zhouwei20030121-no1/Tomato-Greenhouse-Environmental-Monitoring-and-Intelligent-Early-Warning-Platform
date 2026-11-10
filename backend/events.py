import json
from datetime import datetime,timedelta
from . import db,data,forecast

NAMES={'temperature_high':'持续偏热','temperature_low':'持续偏冷','humidity_high':'持续高湿','humidity_low':'空气偏干','vpd_high':'空气VPD偏高','vpd_low':'空气VPD偏低','forecast_temperature_high':'预测升温提示','forecast_humidity_high':'预测高湿提示','data_quality':'节点数据维护'}
ACTIONS={'ventilate':'模拟通风','open_window':'模拟开窗','shade':'模拟遮阳'}

def evaluate(cursor,session_id):
    cfg=db.settings();count=int(cfg['persistence']);created=0
    for node in data.snapshot(cursor):
        cases=[]
        if node['state'] in ('missing','invalid','stale'):
            cases.append(('data_quality','info',{'quality':node['quality'],'age_seconds':node['age_seconds'],'latest_time':node['event_time']}))
        else:
            f=data.frame(node['node_id'] if 'node_id' in node else node['id'],cursor,2)
            if len(f)>=count:
                z=f.iloc[-count:]
                valid=bool(z.maskT.eq(1).all() and z.maskRH.eq(1).all())
                if valid:
                    for metric in ('temperature','humidity'):
                        for side in ('high','low'):
                            threshold=cfg[metric+('_max' if side=='high' else '_min')];trigger=(z[metric]>threshold).all() if side=='high' else (z[metric]<threshold).all()
                            if trigger:cases.append((metric+'_'+side,'warning',{'metric':metric,'threshold':threshold,'values':z[metric].tolist(),'times':[t.isoformat() for t in z.index],'source':'actual_observation','rule':f'{count} consecutive valid 5min points'}))
                    vv=[data.vpd(float(t),float(h)) for t,h in zip(z.temperature,z.humidity)]
                    for side,threshold in [('high',cfg['vpd_max']),('low',cfg['vpd_min'])]:
                        if all(v is not None and (v>threshold if side=='high' else v<threshold) for v in vv):cases.append(('vpd_'+side,'warning',{'metric':'vpd','values':vv,'threshold':threshold,'source':'derived_from_actual_T_RH'}))
            pred=forecast.SERVICE.predict(node['node_id'] if 'node_id' in node else node['id'],cursor)
            if pred['status']=='ready':
                for metric in ('temperature','humidity'):
                    flags=[p[metric]>cfg[metric+'_max'] and (metric!='humidity' or 0<=p[metric]<=100) for p in pred['points']]
                    if any(flags[i] and flags[i+1] for i in range(len(flags)-1)):cases.append(('forecast_'+metric+'_high','notice',{'model_id':pred['model_id'],'issued_at':pred['issued_at'],'points':pred['points'],'threshold':cfg[metric+'_max'],'source':'gru_prediction'}))
        node_id=node.get('node_id') or node['id']
        for kind,severity,evidence in cases:
            evidence.update({'node_id':node_id,'cursor':cursor,'title':NAMES[kind]})
            old=db.one("SELECT * FROM alerts WHERE session_id=? AND node_id=? AND type=? ORDER BY opened_at DESC LIMIT 1",(session_id,node_id,kind))
            if old and old['status']!='closed':db.execute('UPDATE alerts SET last_seen=?,evidence_json=? WHERE id=?',(cursor,db.dumps(evidence),old['id']))
            elif not old or datetime.fromisoformat(cursor)-datetime.fromisoformat(old['last_seen'])>=timedelta(minutes=cfg['cooldown_minutes']):
                db.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?)',(db.uid(),session_id,node_id,kind,severity,'pending',cursor,cursor,db.dumps(evidence),''));created+=1
    return created

def list_alerts(session=None):
    rr=db.rows('SELECT * FROM alerts '+('WHERE session_id=? ' if session else '')+'ORDER BY CASE status WHEN \'pending\' THEN 0 WHEN \'closed\' THEN 2 ELSE 1 END,opened_at DESC LIMIT 200',(session,) if session else ())
    for r in rr:r['evidence']=json.loads(r.pop('evidence_json'));r['title']=NAMES.get(r['type'],r['type'])
    return rr

def confirm(event_id,note):
    with db.connect() as c:
        r=c.execute('SELECT * FROM alerts WHERE id=?',(event_id,)).fetchone()
        if not r:raise ValueError('事件不存在')
        if r['status']!='pending':raise ValueError('只有待确认事件可确认')
        c.execute("UPDATE alerts SET status='confirmed',note=? WHERE id=?",(note,event_id))
    return {'status':'confirmed'}

def execute_event(event_id,action,command_id,note):
    if action not in ACTIONS:raise ValueError('不支持的模拟动作')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM commands WHERE id=?',(command_id,)).fetchone()
        if old:
            if old['event_id']!=event_id or old['action']!=action:raise ValueError('指令ID已用于其他事件或动作')
            return dict(old)
        r=c.execute('SELECT * FROM alerts WHERE id=?',(event_id,)).fetchone()
        if not r or r['status']!='confirmed':raise ValueError('请先人工确认事件，已执行事件不可重复下发')
        ts=db.now();target='virtual-'+r['node_id']
        c.execute('INSERT INTO commands VALUES(?,?,?,?,?,?,?,?)',(command_id,event_id,target,action,'acknowledged',ts,ts,note))
        for state in ['requested','published','acknowledged']:c.execute('INSERT INTO command_logs(command_id,state,created_at,payload) VALUES(?,?,?,?)',(command_id,state,ts,db.dumps({'mode':'simulation','action':action,'environment_modified':False})))
        c.execute("UPDATE alerts SET status='observing',note=? WHERE id=?",(note or r['note'],event_id))
    return db.one('SELECT * FROM commands WHERE id=?',(command_id,))

def close(event_id,note):
    if not note.strip():raise ValueError('请填写复看或关闭说明')
    r=db.one('SELECT * FROM alerts WHERE id=?',(event_id,))
    if not r:raise ValueError('事件不存在')
    if r['status']=='pending':raise ValueError('请先核对并确认事件')
    db.execute("UPDATE alerts SET status='closed',note=? WHERE id=?",(note,event_id));return {'status':'closed'}
