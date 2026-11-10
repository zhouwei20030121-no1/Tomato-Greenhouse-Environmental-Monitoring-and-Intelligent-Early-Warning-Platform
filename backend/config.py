from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
env_file=ROOT/'.env'
if env_file.is_file():
    for line in env_file.read_text('utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key,value=line.split('=',1);os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / 'greenhouse.sqlite3'
SOURCE = Path(os.getenv('DATASET_PATH', str(ROOT.parent / '公开数据' / 'Greenhouse-1.xlsx')))
API_BASE = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')
API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
API_MODEL = os.getenv('DEEPSEEK_MODEL', 'auto')
MQTT_HOST = os.getenv('MQTT_HOST', '')
DEFAULTS = {'temperature_min': 16.0, 'temperature_max': 30.0,
            'humidity_min': 45.0, 'humidity_max': 85.0,
            'vpd_min': 0.4, 'vpd_max': 1.8, 'persistence': 3,
            'cooldown_minutes': 10, 'freshness_minutes': 15}
