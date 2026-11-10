"""Verified real deployments. A deployment is never a renamed copy of another."""
from datetime import datetime
from .config import SOURCE

PUBLICATION = 'https://zenodo.org/records/5793685'
DEPLOYMENTS = {
    'GH1': {'id':'GH1','name':'比利时番茄温室','location':'比利时','filename':'Greenhouse-1.xlsx',
            'path':SOURCE,'md5':'4bf157516b3b576abe30550c65ce75d9','first_node':16,'last_node':42,
            'deployed_after':datetime(2020,4,17,6,38),'default_cursor':'2020-06-25T13:45:00',
            'layout':'论文相对部署布局'},
    'GH2': {'id':'GH2','name':'荷兰番茄温室','location':'荷兰','filename':'Greenhouse-2.xlsx',
            'path':SOURCE.parent/'Greenhouse-2.xlsx','md5':'08901111dce781dbe40904292eb847fd',
            'first_node':49,'last_node':67,'deployed_after':None,'default_cursor':'2020-09-24T13:45:00',
            'layout':'节点示意排列，非实测位置'},
}

def get(greenhouse_id='GH1'):
    if greenhouse_id not in DEPLOYMENTS:raise ValueError('温室不存在')
    return DEPLOYMENTS[greenhouse_id]

def public(greenhouse_id):
    d=get(greenhouse_id)
    return {k:d[k] for k in ['id','name','location','filename','layout']} | {
        'node_count':d['last_node']-d['first_node']+1,'license':'CC BY 4.0',
        'source_url':PUBLICATION,'download_url':PUBLICATION+'/files/'+d['filename']+'?download=1',
        'md5':d['md5']}
