import asyncio,threading,json
from datetime import datetime,timedelta
from . import db,data,events
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
                if rc==0:client.subscribe('greenhouse/GH1/nodes/+/telemetry');self.transport='mqtt'
            def received(client,userdata,message):
                try:self.accept(json.loads(message.payload))
                except (ValueError,KeyError):pass
            self.client.on_connect=connected;self.client.on_message=received;self.client.connect(MQTT_HOST,1883,30);self.client.loop_start()
        except Exception:self.error='MQTT代理不可用，已使用本地消息总线';self.client=None
    def accept(self,payload):self.received+=1;self.last_messages[payload['node_id']]=payload
    def publish(self,node,cursor,session):
        if node.get('event_time') is None:return
        self.sent+=1;payload={k:node.get(k) for k in ['temperature','humidity','rssi','snr','quality','event_time']};payload.update(node_id=node['id'],replay_time=cursor,session_id=session,source='real_dataset_replay')
        if self.transport=='mqtt' and self.client:self.client.publish('greenhouse/GH1/nodes/'+node['id']+'/telemetry',db.dumps(payload),qos=1)
        else:self.accept(payload)
    def info(self):return {'transport':self.transport,'label':'MQTT网关' if self.transport=='mqtt' else '本地发布订阅总线','sent':self.sent,'received':self.received,'error':self.error}
    def stop(self):
        if self.client:self.client.loop_stop();self.client.disconnect()
GATEWAY=GatewayService()
LAST=None
def state():
    s=db.one('SELECT * FROM replay_state WHERE id=1');s['running']=bool(s['running']);s['gateway']=GATEWAY.info();return s
def process(force=False):
    global LAST
    with LOCK:
        s=state();bucket=s['cursor'][:15] # bucket is refined below to exactly 5 minutes
        t=datetime.fromisoformat(s['cursor']);bucket=(s['session_id'],t.replace(minute=t.minute//5*5,second=0).isoformat())
        if bucket==LAST and not force:return
        LAST=bucket
        for n in data.snapshot(s['cursor']):GATEWAY.publish(n,s['cursor'],s['session_id'])
        events.evaluate(s['cursor'],s['session_id'])
def control(action,cursor=None,speed=None):
    with LOCK:
        s=state();bounds=db.one('SELECT MIN(event_time) start,MAX(event_time) end FROM readings')
        if not bounds['start']:raise ValueError('请先导入真实数据')
        if action=='play':db.execute('UPDATE replay_state SET running=1 WHERE id=1')
        elif action=='pause':db.execute('UPDATE replay_state SET running=0 WHERE id=1')
        elif action in ('seek','step'):
            ts=datetime.fromisoformat(cursor) if action=='seek' and cursor else datetime.fromisoformat(s['cursor'])+timedelta(minutes=5)
            value=max(bounds['start'],min(bounds['end'],ts.replace(microsecond=0).isoformat()))
            session=db.uid() if value<s['cursor'] else s['session_id']
            db.execute('UPDATE replay_state SET cursor=?,session_id=?,running=0 WHERE id=1',(value,session))
        elif action=='speed':
            if speed is None or not 1<=speed<=3600:raise ValueError('倍速范围为1到3600')
            db.execute('UPDATE replay_state SET speed=? WHERE id=1',(speed,))
        else:raise ValueError('未知回放操作')
        process(force=action in ('seek','step'));return state()
async def loop():
    while True:
        await asyncio.sleep(1)
        s=state()
        if s['running']:
            end=db.one('SELECT MAX(event_time) end FROM readings')['end']
            if not end:continue
            ts=(datetime.fromisoformat(s['cursor'])+timedelta(seconds=s['speed'])).isoformat(timespec='seconds')
            db.execute('UPDATE replay_state SET cursor=?,running=? WHERE id=1',(min(ts,end),int(ts<end)))
            await asyncio.to_thread(process)

