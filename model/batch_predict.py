"""Vectorized evaluation of portable artifacts; inference explanations stay unchanged."""
import numpy as np
from scipy.special import expit,logit


def base_logit(artifact,rows):
    names=artifact['features'];raw=np.array([[np.nan if r[f] is None else r[f] for f in names] for r in rows],dtype=float)
    if not len(rows):return np.array([],dtype=float)
    if any(set(r)!=set(names) for r in rows) or np.any(np.isinf(raw)):raise ValueError('Invalid feature matrix')
    missing=np.isnan(raw);x=np.where(missing,artifact['medians'],raw)
    if artifact['indicators']:x=np.c_[x,missing[:,artifact['indicators']].astype(float)]
    if 'mean' in artifact:x=(x-artifact['mean'])/artifact['scale']
    if not np.isfinite(x).all():raise ValueError('Invalid transformed features')
    if artifact['kind']=='logistic':raw_score=x@np.asarray(artifact['weights'])+artifact['intercept']
    else:
        x=x.astype(np.float32);trees=artifact['trees'];raw_score=np.full(len(rows),artifact.get('intercept',0.),dtype=float)
        for tree in trees:
            left=np.asarray(tree['left']);right=np.asarray(tree['right']);features=np.asarray(tree['feature']);threshold=np.asarray(tree['threshold']);values=np.asarray(tree['value']);nodes=np.zeros(len(rows),dtype=int)
            while True:
                active=np.flatnonzero(left[nodes]!=-1)
                if not len(active):break
                n=nodes[active];nodes[active]=np.where(x[active,features[n]]<=threshold[n],left[n],right[n])
            rate=artifact['learning_rate'] if artifact['kind']=='boosted' else 1/len(trees)
            raw_score+=rate*values[nodes]
    probabilities=raw_score if artifact['kind']=='forest' else expit(raw_score)
    return logit(np.clip(probabilities,1e-6,1-1e-6))


def predict(artifact,rows):
    a,b=artifact['calibration']
    return expit(a*base_logit(artifact,rows)+b)
