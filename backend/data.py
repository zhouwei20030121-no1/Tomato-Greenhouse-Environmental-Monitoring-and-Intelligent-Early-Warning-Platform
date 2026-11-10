import hashlib, math, json
from datetime import datetime,time,timedelta
from functools import lru_cache
import numpy as np
import pandas as pd
from .config import SOURCE
from . import db

DEPLOY=datetime(2020,4,17,6,38)
EXPECTED_MD5='4bf157516b3b576abe30550c65ce75d9'

def vpd(t,rh):
    if t is None or rh is None or not -20<=t<=70 or not 0<=rh<=100:return None
    return round(0.6108*math.exp(17.27*t/(t+237.3))*(1-rh/100),4)
def number(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None
def parse_time(d,t):
    if d is None or t is None:return None
    try:
        if isinstance(d,(float,int)):d=datetime(1899,12,30)+timedelta(days=float(d))
        if not isinstance(d,datetime):d=pd.Timestamp(d).to_pydatetime()
        if isinstance(t,time):dt=datetime.combine(d.date(),t)
        elif isinstance(t,datetime):dt=datetime.combine(d.date(),t.time())
        elif isinstance(t,(float,int)):dt=datetime.combine(d.date(),time())+timedelta(days=float(t)%1)
        else:dt=datetime.combine(d.date(),time.fromisoformat(str(t)))
        return dt.replace(microsecond=0)
    except (ValueError,TypeError,OverflowError):return None

def import_source(j):
    try:
        import openpyxl
        if not SOURCE.is_file():raise ValueError('找不到原始数据，请在.env中设置DATASET_PATH')
        db.progress(j,1,'校验原始文件')
        checksum=hashlib.md5(SOURCE.read_bytes()).hexdigest()
        if checksum!=EXPECTED_MD5:raise ValueError('源文件MD5与已核验的Greenhouse-1.xlsx不一致，停止导入')
        old=db.one("SELECT * FROM sources WHERE checksum=? AND status='ready'",(checksum,))
        if old:
            db.progress(j,100,'数据已经导入，无需重复写入','done',{'rows':old['rows']});return
        with db.connect() as c:
            c.execute('INSERT OR IGNORE INTO sources(path,checksum,license,status) VALUES(?,?,?,?)',(str(SOURCE),checksum,'CC BY 4.0','importing'))
            source_id=c.execute('SELECT id FROM sources WHERE path=?',(str(SOURCE),)).fetchone()[0]
        wb=openpyxl.load_workbook(SOURCE,read_only=True,data_only=True)
        raw=0;valid_time=0;quality_count=0
        try:
            for k,name in enumerate(wb.sheetnames):
                if name not in {f'AF{n}' for n in range(16,43)}:continue
                batch=[]
                for row in wb[name].iter_rows(min_row=2,values_only=True):
                    if not any(v is not None for v in row[:6]):continue
                    raw+=1
                    if len(row)<6:continue
                    ts=parse_time(row[0],row[1])
                    if ts is None or ts<DEPLOY:continue
                    valid_time+=1;t,rh,rssi,snr=map(number,row[2:6])
                    flags=[]
                    if t is None or not -20<=t<=70:flags.append('temperature_invalid')
                    if rh is None or not 0<=rh<=100:flags.append('humidity_invalid')
                    if flags:quality_count+=1
                    batch.append((source_id,name,ts.isoformat(),t,rh,rssi,snr,','.join(flags) or 'valid'))
                with db.connect() as c:c.executemany('INSERT OR IGNORE INTO readings(source_id,node_id,event_time,temperature,humidity,rssi,snr,quality) VALUES(?,?,?,?,?,?,?,?)',batch)
                db.progress(j,round((k+1)/27*95,1),f'已读取{name}，累计{valid_time:,}条温室记录')
        finally:wb.close()
        actual=db.one('SELECT COUNT(*) n FROM readings WHERE source_id=?',(source_id,))['n']
        db.execute('UPDATE sources SET status=?,rows=?,imported_at=? WHERE id=?',('ready',actual,db.now(),source_id))
        bounds=db.one('SELECT MIN(event_time) start,MAX(event_time) end FROM readings')
        db.progress(j,100,f'真实数据导入完成：{actual:,}条','done',{'rows':actual,'raw_rows':raw,'valid_time':valid_time,'quality_flagged':quality_count,'bounds':bounds,'md5':checksum})
        snapshot.cache_clear();frame.cache_clear()
    except Exception as e:db.progress(j,0,str(e),'failed')

def status():
    return {'sources':db.rows('SELECT id,path,checksum,license,status,rows,imported_at FROM sources'),
            'bounds':db.one('SELECT MIN(event_time) start,MAX(event_time) end,COUNT(*) count FROM readings'),
            'nodes':db.rows('SELECT n.id,COUNT(r.id) count,MIN(r.event_time) start,MAX(r.event_time) end FROM nodes n LEFT JOIN readings r ON n.id=r.node_id GROUP BY n.id'),
            'job':db.one("SELECT * FROM jobs WHERE kind='import' ORDER BY started_at DESC LIMIT 1"),'source_exists':SOURCE.is_file()}

def latest(node,cursor):
    return db.one('SELECT * FROM readings WHERE node_id=? AND event_time<=? ORDER BY event_time DESC LIMIT 1',(node,cursor))

@lru_cache(maxsize=250)
def snapshot(cursor):
    cfg=db.settings();out=[]
    for n in db.rows('SELECT * FROM nodes ORDER BY col_index,row_index'):
        r=latest(n['id'],cursor);item={**n,'temperature':None,'humidity':None,'vpd':None,'rssi':None,'snr':None,'age_seconds':None,'event_time':None,'quality':'no_data','state':'missing'}
        if r:
            item.update({k:v for k,v in r.items() if k!='id'});age=(datetime.fromisoformat(cursor)-datetime.fromisoformat(r['event_time'])).total_seconds();item['age_seconds']=max(0,age)
            item['vpd']=vpd(r['temperature'],r['humidity']) if r['quality']=='valid' else None
            item['state']='stale' if age>cfg['freshness_minutes']*60 else 'invalid' if r['quality']!='valid' else 'warning' if not cfg['temperature_min']<=r['temperature']<=cfg['temperature_max'] or not cfg['humidity_min']<=r['humidity']<=cfg['humidity_max'] else 'normal'
        out.append(item)
    return out

@lru_cache(maxsize=200)
def frame(node,end,hours=8):
    start=(datetime.fromisoformat(end)-timedelta(hours=hours,minutes=15)).isoformat()
    rr=db.rows('SELECT event_time,temperature,humidity,rssi,snr,quality FROM readings WHERE node_id=? AND event_time>? AND event_time<=? ORDER BY event_time',(node,start,end))
    if not rr:return pd.DataFrame()
    f=pd.DataFrame(rr);f['event_time']=pd.to_datetime(f['event_time']);f=f.set_index('event_time')
    # A right-closed bin at time t never includes a record later than t.
    f.loc[f.quality!='valid',['temperature','humidity']]=np.nan
    f=f.resample('5min',label='right',closed='right').last()
    last=pd.Timestamp(end).floor('5min');first=last-pd.Timedelta(hours=hours)+pd.Timedelta(minutes=5)
    f=f.reindex(pd.date_range(first,last,freq='5min'))
    f['maskT']=f.temperature.notna().astype(float);f['maskRH']=f.humidity.notna().astype(float)
    f[['temperature','humidity']]=f[['temperature','humidity']].ffill(limit=1)
    return f

def series(node,end,hours=8):
    f=frame(node,end,hours)
    if f.empty:return []
    out=[]
    for ts,r in f.iterrows():
        def clean(k):return float(r[k]) if k in r and pd.notna(r[k]) else None
        t,rh=clean('temperature'),clean('humidity')
        out.append({'time':ts.isoformat(),'temperature':t,'humidity':rh,'vpd':vpd(t,rh),'rssi':clean('rssi'),'snr':clean('snr'),'observed':bool(r.maskT and r.maskRH)})
    return out
