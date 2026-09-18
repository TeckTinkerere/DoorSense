"""Exercise the running production API and save its exact Test.csv downloads.

Start scripts/start.ps1 first. This is an integration check, not another exporter:
artifacts are the bytes returned by the application's download endpoints.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid
import zipfile

APP=Path(__file__).resolve().parents[1]
SOURCE_ROOT=Path(os.environ.get('DOORLENS_SOURCE_ROOT',
    APP.parent/'NebulaX-Hackathon-ProblemStatement'/'PS3'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    base=args.url.rstrip('/')
    def request(path,body=None,headers=None,method=None):
        req=urllib.request.Request(base+path,data=body,headers=headers or {},method=method)
        with urllib.request.urlopen(req,timeout=60) as response:
            return response.read(),{key.lower():value for key,value in response.headers.items()}
    def get_json(path,body=None):
        content,_=request(path,None if body is None else json.dumps(body).encode(),
                          {'Content-Type':'application/json'} if body is not None else {})
        return json.loads(content)
    html,headers=request('/')
    assert b'<html' in html and 'text/html' in headers.get('content-type','')
    health=get_json('/api/health')
    try:
        request('/api/this-endpoint-must-not-exist')
        raise AssertionError('Unknown API route must fail')
    except urllib.error.HTTPError as error:
        assert error.code==404 and json.loads(error.read())['detail']['code']=='api_not_found'
    runs=[]
    for name in ('Train.csv','Test.csv'):
        content=(SOURCE_ROOT/'02_Datasets/Door'/name).read_bytes()
        boundary='DoorLensVerification'+uuid.uuid4().hex
        multipart=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                   'Content-Type: text/csv\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        started=time.perf_counter()
        raw,_=request('/api/analyze',multipart,{'Content-Type':f'multipart/form-data; boundary={boundary}'})
        elapsed=(time.perf_counter()-started)*1000
        run=json.loads(raw)
        prefix=f'/api/analyses/{run["id"]}'
        csv_bytes,csv_headers=request(prefix+'/predictions.csv')
        zip_bytes,zip_headers=request(prefix+'/predictions.zip')
        assert hashlib.sha256(csv_bytes).hexdigest()==run['csv_sha256']
        rows=list(csv.DictReader(StringIO(csv_bytes.decode())))
        assert csv_bytes.splitlines()[0]==b'start_time,end_time,prediction'
        assert rows==[{key:cycle[key] for key in ('start_time','end_time','prediction')} for cycle in run['cycles']]
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            assert archive.namelist()==['door_predictions.csv']
            assert archive.read('door_predictions.csv')==csv_bytes
        assert 'filename="predictions.zip"' in zip_headers['content-disposition']
        selected=get_json(prefix+'/cycles/0')
        assert selected['model_id']==health['model_id']
        probe_results=[]
        for probe in run['probe_definitions']:
            result=get_json(prefix+'/cycles/0/challenge',{'probe_id':probe['id']})
            assert result['original_csv_sha256']==run['csv_sha256']
            assert result['original']['score']==run['cycles'][0]['score']
            assert request(prefix+'/predictions.csv')[0]==csv_bytes
            assert request(prefix+'/predictions.zip')[0]==zip_bytes
            probe_results.append({'probe':probe['id'],'label_changed':result['label_changed'],'score':result['altered']['score']})
        assert get_json(prefix+'/cycles/0')==selected
        runs.append({'file':name,'input_sha256':hashlib.sha256(content).hexdigest(),
            'model_id':run['model_id'],'summary':run['summary'],'api_inference_ms':run['elapsed_ms'],
            'http_upload_to_response_ms':round(elapsed,3),'csv_sha256':run['csv_sha256'],
            'probe_results_first_cycle':probe_results,'original_exports_unchanged':True})
        if name=='Test.csv':
            output=APP/'artifacts'
            output.mkdir(exist_ok=True)
            (output/'door_predictions.csv').write_bytes(csv_bytes)
            (output/'predictions.zip').write_bytes(zip_bytes)
    demo_raw,_=request('/api/demo',b'',method='POST')
    demo=json.loads(demo_raw)
    assert demo['context']=='development-demo' and demo['model_id']==health['demo_model_id']!=health['model_id']
    result=get_json(f'/api/analyses/{demo["id"]}/cycles/0/challenge',{'probe_id':'current_minus_5pct'})
    assert result['label_changed'] and result['original']['prediction']=='Abnormal resistance' and result['altered']['prediction']=='Normal'
    report={'verified_at':datetime.now(timezone.utc).isoformat(),'base_url':base,
        'source':'Actual running application HTTP responses; downloads saved unchanged.',
        'runs':runs,'demo_result':{key:result[key] for key in ('model_id','original','altered','label_changed')},
        'unknown_api_json_404':True,'test_ground_truth_available':False,
        'latency_note':'One measured run per supplied file on this laptop; not a throughput benchmark or real-world accuracy result.'}
    (APP/'artifacts/local-api-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
