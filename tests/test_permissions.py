import tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import db,auth,data,forecast
from backend.app import app

class RolePermissions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=db.DB_PATH;db.DB_PATH=Path(self.tmp.name)/'isolated.sqlite3';self.env=patch.dict(os.environ,{'GROWER_PASSWORD':'unit-grower-password','OPERATOR_PASSWORD':'unit-operator-password'});self.env.start();self.folder=patch.object(auth,'DATA',Path(self.tmp.name));self.folder.start();data.snapshot.cache_clear();data.frame.cache_clear();forecast.SERVICE=forecast.ForecastService();self.client=TestClient(app);self.client.__enter__()
 def tearDown(self):
  self.client.__exit__(None,None,None);self.folder.stop();self.env.stop();db.DB_PATH=self.old;data.snapshot.cache_clear();data.frame.cache_clear();self.tmp.cleanup()
 def test_anonymous_and_role_restrictions(self):
  self.assertEqual(self.client.get('/api/overview').status_code,401)
  login=self.client.post('/api/auth/login',json={'username':'grower','password':'unit-grower-password'});self.assertEqual(login.status_code,200);self.assertIn('HttpOnly',login.headers['set-cookie'])
  self.assertEqual(self.client.get('/api/data/status').status_code,403)
  self.assertEqual(self.client.post('/api/models/train',json={'epochs':2}).status_code,403)
  self.client.post('/api/auth/logout')
  self.client.post('/api/auth/login',json={'username':'operator','password':'unit-operator-password'})
  self.assertEqual(self.client.get('/api/data/status').status_code,200)
  self.assertEqual(self.client.put('/api/settings',json={}).status_code,403)
  self.assertEqual(self.client.post('/api/alerts/fake/confirm',json={'note':'test'}).status_code,403)
 def test_bad_password_is_rejected(self):
  self.assertEqual(self.client.post('/api/auth/login',json={'username':'grower','password':'wrong'}).status_code,401)
  self.assertIsNone(self.client.get('/api/auth/me').json()['user'])

if __name__=='__main__':unittest.main()
