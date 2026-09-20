from __future__ import annotations

import argparse
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES=["downtimeMinutes","reworkRate","materialDelayHours","remainingRatio","dueHours","machineBad","productionRate"]


def generate(n=2400, seed=7):
    rng=np.random.default_rng(seed)
    downtime=rng.uniform(0,240,n)
    rework=rng.uniform(0,0.18,n)
    material=rng.uniform(0,18,n)
    remaining=rng.uniform(0.05,1,n)
    due=rng.uniform(-8,72,n)
    machine_bad=rng.choice([0,0.5,1],n,p=[.68,.2,.12])
    production=rng.uniform(12,42,n)
    z=(-2.7 + .008*downtime + 2.1*rework + .12*material + 1.1*remaining + .045*np.maximum(0,24-due) + 1.9*machine_bad - .02*production)
    p=1/(1+np.exp(-z))
    y=np.clip(p+rng.normal(0,.03,n),0,1)
    X=np.column_stack([downtime,rework,material,remaining,due,machine_bad,production])
    return X,y


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default='ml/artifacts/model.joblib'); args=ap.parse_args()
    X,y=generate(); model=HistGradientBoostingRegressor(max_depth=5,learning_rate=.06,max_iter=220,random_state=7).fit(X,y)
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({'model':model,'features':FEATURES},path)
    print(f"saved {path}")

if __name__=='__main__': main()
