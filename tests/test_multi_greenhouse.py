import json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch,Mock
from fastapi.testclient import TestClient
from backend import db,data,events,forecast,rag,replay,auth
from backend.app import app

class MultiGreenhouseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=db.DB_PATH;db.DB_PATH=Path(self.tmp.name)/'isolated.sqlite3'
  self.env=patch.dict(os.environ,{'GROWER_PASSWORD':'test-grower','OPERATOR_PASSWORD':'test-operator'});self.env.start()
  self.folder=patch.object(auth,'DATA',Path(self.tmp.name));self.folder.start()
  data.frame.cache_clear();data.snapshot.cache_clear();forecast.SERVICE=forecast.ForecastService();rag.RETRIEVER=rag.HybridRetriever();replay.LAST={}
  self.client=TestClient(app);self.client.__enter__()
  db.execute("UPDATE greenhouse_replay SET cursor='2020-09-20T13:45:00' WHERE greenhouse_id='GH2'")
  with db.connect() as c:
   for gid,node,day,t in [('GH1','AF16','2020-06-25',34),('GH2','AF49','2020-09-20',22)]:
    c.execute('INSERT INTO sources(path,checksum,license,status,greenhouse_id) VALUES(?,?,?,?,?)',(gid,gid,'test','ready',gid));sid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
    start=datetime.fromisoformat(day+'T10:00:00')
    c.executemany('INSERT INTO readings(source_id,node_id,event_time,temperature,humidity,rssi,snr,quality) VALUES(?,?,?,?,?,?,?,?)',[(sid,node,(start+timedelta(minutes=5*k)).isoformat(),t,70,-90,7,'valid') for k in range(60)])
 def tearDown(self):
  self.client.__exit__(None,None,None);self.folder.stop();self.env.stop();db.DB_PATH=self.old;data.frame.cache_clear();data.snapshot.cache_clear();self.tmp.cleanup()
 def login(self,role='grower'):
  self.client.post('/api/auth/login',json={'username':role,'password':'test-'+role})
 def test_scope_rejects_cross_site_nodes_and_unknown_sites(self):
  self.login();a=self.client.get('/api/overview?greenhouse_id=GH1').json();b=self.client.get('/api/overview?greenhouse_id=GH2').json()
  self.assertEqual(a['metrics']['total_nodes'],27);self.assertEqual(b['metrics']['total_nodes'],19)
  self.assertEqual(a['metrics']['temperature'],34);self.assertEqual(b['metrics']['temperature'],22)
  self.assertEqual(self.client.get('/api/nodes/AF16/series?greenhouse_id=GH2').status_code,404)
  self.assertEqual(self.client.get('/api/overview?greenhouse_id=unknown').status_code,404)
 def test_settings_and_replay_are_independent(self):
  self.login();cfg=db.settings('GH2');cfg['temperature_max']=33
  self.assertEqual(self.client.put('/api/settings?greenhouse_id=GH2',json=cfg).status_code,200)
  self.assertEqual(db.settings('GH1')['temperature_max'],30);self.assertEqual(db.settings('GH2')['temperature_max'],33)
  self.client.post('/api/auth/logout');self.login('operator');before=replay.state('GH1')['cursor']
  self.client.post('/api/replay/control?greenhouse_id=GH2',json={'action':'step'})
  self.assertEqual(replay.state('GH1')['cursor'],before);self.assertEqual(replay.state('GH2')['cursor'],'2020-09-20T13:50:00')
 def test_events_and_rag_stay_in_current_greenhouse(self):
  events.evaluate('2020-06-25T12:00:00','s1','GH1');events.evaluate('2020-09-20T12:00:00','s2','GH2')
  self.assertTrue(all(int(a['node_id'][2:])>=49 for a in events.list_alerts(None,'GH2')))
  a=db.one("SELECT * FROM alerts WHERE node_id='AF16' AND type='temperature_high'");self.login()
  self.assertEqual(self.client.post('/api/alerts/'+a['id']+'/confirm?greenhouse_id=GH2',json={'note':'wrong scope'}).status_code,404)
  with patch.object(rag,'API_KEY',''):
   response=rag.ask('当前节点情况','AF49','2020-09-20T12:00:00',greenhouse_id='GH2')
   self.assertEqual(json.loads(next(e for e in response['evidence'] if e['id']=='E1')['content'])['node'],'AF49')
   with self.assertRaises(ValueError):rag.ask('AF16为何高温','AF49','2020-09-20T12:00:00',greenhouse_id='GH2')
 def test_untrained_site_never_reuses_other_site_model(self):
  self.assertEqual(forecast.SERVICE.predict('AF49','2020-09-20T12:00:00')['status'],'paused')
 def test_ai_advice_rejects_unknown_action_and_never_executes(self):
  events.evaluate('2020-06-25T12:00:00','s','GH1');event=db.one("SELECT * FROM alerts WHERE node_id='AF16' AND type='temperature_high'")
  response=Mock();response.json.return_value={'choices':[{'message':{'content':json.dumps({'answer':'建议检查 [E2]','citations':['E2'],'suggestions':[],'recommendations':[{'action':'unsafe_unknown_action','reason':'错误动作','citations':['E2']}]})}}]}
  with patch.object(rag,'API_KEY','test'),patch.object(rag,'configured_model',return_value='test-model'),patch.object(rag.httpx,'post',return_value=response):
   advice=rag.recommend(event,'2020-06-25T12:00:00','GH1')
  self.assertEqual(advice['provider'],'local_evidence_template')
  self.assertTrue(all(r['action'] in ['none','ventilate','shade'] for r in advice['recommendations']))
  self.assertIn('湿度70.0%（在参考范围内）',advice['summary'])
  self.assertEqual(db.one('SELECT COUNT(*) n FROM commands')['n'],0)
  self.assertEqual(db.one('SELECT status FROM alerts WHERE id=?',(event['id'],))['status'],'pending')

if __name__=='__main__':unittest.main()
