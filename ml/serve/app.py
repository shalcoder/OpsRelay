from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import joblib
import numpy as np

MODEL=joblib.load('/opt/ml/model/model.joblib')
REG=MODEL['model']


def predict(payload):
    machine_bad=1.0 if payload.get('machineStatus')=='STOPPED' else .5 if payload.get('machineStatus')=='DEGRADED' else 0.0
    values=[float(payload.get('downtimeMinutes',0)),float(payload.get('reworkRate',0)),float(payload.get('materialDelayHours',0)),float(payload.get('remainingRatio',0)),float(payload.get('dueHours',24)),machine_bad,float(payload.get('productionRate',20))]
    delay=float(np.clip(REG.predict(np.array([values]))[0],0.01,.99))
    failure=float(np.clip(.04+.62*machine_bad+.28*min(1,values[0]/180),.01,.99))
    anomaly=float(np.clip(.08+.58*min(1,values[0]/180)+.22*min(1,values[1]/.12),.01,.99))
    return {'delayProbability':round(delay,4),'failureProbability':round(failure,4),'anomalyScore':round(anomaly,4)}

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,data):
        raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.reply(200,{'status':'ok'} if self.path=='/ping' else {'service':'opsrelay-predictor'})
    def do_POST(self):
        if self.path!='/invocations': return self.reply(404,{'error':'not found'})
        n=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(n)); self.reply(200,predict(payload))

if __name__=='__main__': ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
