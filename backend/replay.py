import asyncio,threading,json
from datetime import datetime,timedelta
from . import db,data,events,catalog
from .config import MQTT_HOST

LOCK=threading.RLock()
class GatewayService:
    def __init__(self):self.sent=0;self.received=0;self.last_messages={};self.client=None;self.transport='local';self.error=None
    def start(self):
        if not MQTT_HOST:return
        try:
            import paho.mqtt.client as mqtt
            self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='greenhouse-'+db.uid())
            def connected(client,userdata,flags,rc,properties):
                if rc==0:client.subscribe('greenhouse/+/nodes/+/telemetry');self.transport='mqtt'
            def received(client,userdata,message):
                try:self.accept(json.loads(message.payload))
                except (ValueError,KeyError):pass
            self.client.on_connect=connected;self.client.on_message=received;self.client.connect(MQTT_HOST,1883,30);self.client.loop_start()
        except Exception:self.error='MQTT代理不可用，已使用本地消息总线';self.client=None
    def accept(self,payload):self.received+=1;self.last_messages[payload['node_id']]=payload
    def publish(self,node,cursor,session):
        if node.get('event_time') is None:return
        self.sent+=1;payload={k:node.get(k) for k in ['temperature','humidity','rssi','snr','quality','event_time','greenhouse_id']};payload.update(node_id=node['id'],replay_time=cursor,session_id=session,source='real_dataset_replay')
        if self.transport=='mqtt' and self.client:self.client.publish('greenhouse/'+node['greenhouse_id']+'/nodes/'+node['id']+'/telemetry',db.dumps(payload),qos=1)
        else:self.accept(payload)
    def info(self):return {'transport':self.transport,'label':'MQTT网关' if self.transport=='mqtt' else '本地发布订阅总线','sent':self.sent,'received':self.received,'error':self.error}
    def stop(self):
        if self.client:self.client.loop_stop();self.client.disconnect()
GATEWAY=GatewayService()
LAST={}

def state(greenhouse_id='GH1'):
    catalog.get(greenhouse_id)
    s=db.one('SELECT * FROM greenhouse_replay WHERE greenhouse_id=?',(greenhouse_id,));s['running']=bool(s['running']);s['gateway']=GATEWAY.info();return s

def process(force=False,greenhouse_id='GH1'):
    with LOCK:
        s=state(greenhouse_id);t=datetime.fromisoformat(s['cursor']);bucket=(s['session_id'],t.replace(minute=t.minute//5*5,second=0).isoformat())
        if bucket==LAST.get(greenhouse_id) and not force:return
        LAST[greenhouse_id]=bucket
        for n in data.snapshot(s['cursor'],greenhouse_id):GATEWAY.publish(n,s['cursor'],s['session_id'])
        events.evaluate(s['cursor'],s['session_id'],greenhouse_id)

def control(action,cursor=None,speed=None,greenhouse_id='GH1'):
    with LOCK:
        s=state(greenhouse_id);bounds=data.source_bounds(greenhouse_id)
        if not bounds['start']:raise ValueError('请先导入当前温室的真实数据')
        if action=='play':db.execute('UPDATE greenhouse_replay SET running=1 WHERE greenhouse_id=?',(greenhouse_id,))
        elif action=='pause':db.execute('UPDATE greenhouse_replay SET running=0 WHERE greenhouse_id=?',(greenhouse_id,))
        elif action in ('seek','step'):
            ts=datetime.fromisoformat(cursor) if action=='seek' and cursor else datetime.fromisoformat(s['cursor'])+timedelta(minutes=5)
            value=max(bounds['start'],min(bounds['end'],ts.replace(microsecond=0).isoformat()))
            session=db.uid() if value<s['cursor'] else s['session_id']
            db.execute('UPDATE greenhouse_replay SET cursor=?,session_id=?,running=0 WHERE greenhouse_id=?',(value,session,greenhouse_id))
        elif action=='speed':
            if speed is None or not 1<=speed<=3600:raise ValueError('倍速范围为1到3600')
            db.execute('UPDATE greenhouse_replay SET speed=? WHERE greenhouse_id=?',(speed,greenhouse_id))
        else:raise ValueError('未知回放操作')
        process(force=action in ('seek','step'),greenhouse_id=greenhouse_id);return state(greenhouse_id)

async def loop():
    while True:
        await asyncio.sleep(1)
        for s in db.rows('SELECT * FROM greenhouse_replay WHERE running=1'):
            bounds=data.source_bounds(s['greenhouse_id']);end=bounds['end']
            if not end:continue
            ts=(datetime.fromisoformat(s['cursor'])+timedelta(seconds=s['speed'])).isoformat(timespec='seconds')
            db.execute('UPDATE greenhouse_replay SET cursor=?,running=? WHERE greenhouse_id=?',(min(ts,end),int(ts<end),s['greenhouse_id']))
            await asyncio.to_thread(process,False,s['greenhouse_id'])
