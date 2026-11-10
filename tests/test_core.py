import tempfile, unittest, json
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
import numpy as np
from backend import db,data,events,forecast,rag

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=db.DB_PATH;db.DB_PATH=Path(self.tmp.name)/'test.sqlite3';db.init_db();data.frame.cache_clear();data.snapshot.cache_clear();forecast.SERVICE=forecast.ForecastService()
        db.execute('INSERT INTO sources(path,checksum,license,status) VALUES(?,?,?,?)',('fixture','test','test','ready'))
        start=datetime(2020,6,25,10)
        with db.connect() as c:c.executemany('INSERT INTO readings(source_id,node_id,event_time,temperature,humidity,rssi,snr,quality) VALUES(1,?,?,?,?,?,?,?)',[('AF16',(start+timedelta(minutes=5*k)).isoformat(),34.0,70.0,-90,7,'valid') for k in range(60)])
    def tearDown(self):db.DB_PATH=self.old;data.frame.cache_clear();data.snapshot.cache_clear();self.tmp.cleanup()
    def test_vpd_and_invalid_inputs(self):
        self.assertAlmostEqual(data.vpd(25,50),1.5839,places=3);self.assertIsNone(data.vpd(25,101));self.assertIsNone(data.vpd(None,50))
    def test_no_future_observations_in_window(self):
        end='2020-06-25T12:00:00';before=data.frame('AF16',end,2).copy()
        db.execute("UPDATE readings SET temperature=99 WHERE event_time>?",(end,));data.frame.cache_clear()
        np.testing.assert_equal(before.temperature.to_numpy(),data.frame('AF16',end,2).temperature.to_numpy())
    def test_original_missing_mask_survives_one_step_fill(self):
        db.execute("DELETE FROM readings WHERE node_id='AF16' AND event_time='2020-06-25T11:00:00'");data.frame.cache_clear();f=data.frame('AF16','2020-06-25T12:00:00',2)
        self.assertEqual(f.loc['2020-06-25T11:00:00','maskT'],0);self.assertEqual(f.loc['2020-06-25T11:00:00','temperature'],34)
    def test_long_gap_pauses_features(self):
        db.execute("DELETE FROM readings WHERE event_time>='2020-06-25T11:00:00' AND event_time<='2020-06-25T11:20:00'");data.frame.cache_clear();f=data.frame('AF16','2020-06-25T12:00:00',2)
        self.assertTrue(f.temperature.isna().any())
    def test_rule_event_is_idempotent(self):
        events.evaluate('2020-06-25T12:00:00','session');n=db.one('SELECT COUNT(*) n FROM alerts')['n'];events.evaluate('2020-06-25T12:00:00','session');self.assertEqual(db.one('SELECT COUNT(*) n FROM alerts')['n'],n)
        self.assertTrue(db.one("SELECT id FROM alerts WHERE node_id='AF16' AND type='temperature_high'"))
    def test_confirm_required_and_command_idempotent(self):
        events.evaluate('2020-06-25T12:00:00','s');a=db.one("SELECT * FROM alerts WHERE node_id='AF16' AND type='temperature_high'")
        with self.assertRaises(ValueError):events.execute_event(a['id'],'ventilate','command-unique','test')
        count=db.one('SELECT COUNT(*) n FROM readings')['n'];events.confirm(a['id'],'核对');r=events.execute_event(a['id'],'ventilate','command-unique','模拟');r2=events.execute_event(a['id'],'ventilate','command-unique','模拟')
        self.assertEqual(r['id'],r2['id']);self.assertEqual(db.one('SELECT COUNT(*) n FROM commands')['n'],1);self.assertEqual(db.one('SELECT COUNT(*) n FROM readings')['n'],count)
        self.assertEqual(db.one('SELECT COUNT(*) n FROM command_logs')['n'],3)
        with self.assertRaises(ValueError):events.close(a['id'],'')
        events.close(a['id'],'复看并关闭');self.assertEqual(db.one('SELECT status FROM alerts WHERE id=?',(a['id'],))['status'],'closed')
    def test_hybrid_retrieval_has_real_scores(self):
        rag.init_knowledge();r=rag.HybridRetriever();ev,trace=r.retrieve('空气VPD怎么由温湿度计算？')
        self.assertTrue(ev);self.assertFalse(trace['neural_embedding']);self.assertTrue(any('VPD' in x['content'] for x in ev));self.assertTrue(any(t['bm25']>0 and t['tfidf_cosine']>0 for t in trace['selected']))
    def test_rag_network_fallback_is_truthful(self):
        rag.init_knowledge();rag.RETRIEVER=rag.HybridRetriever()
        with patch.object(rag,'API_KEY',''):
            a=rag.ask('为什么这个节点持续偏热？','AF16','2020-06-25T12:00:00')
        self.assertEqual(a['provider'],'local_evidence_template');self.assertTrue(a['fallback_reason']);self.assertIn('E1',a['citations'])
        allowed={x['id'] for x in a['evidence']};self.assertTrue(set(a['citations'])<=allowed)
    def test_real_model_shape(self):
        import torch
        self.assertEqual(tuple(forecast.ClimateGRU()(torch.zeros(2,24,6)).shape),(2,6,2))
    def test_snapshot_preserves_node_id(self):
        n=next(x for x in data.snapshot('2020-06-25T12:00:00') if x['id']=='AF16');self.assertIsInstance(n['id'],str);self.assertEqual(n['state'],'warning')

if __name__=='__main__':unittest.main()
