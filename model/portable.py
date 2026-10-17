"""Non-executable model artifacts and exact path-based feature explanations."""
import math
import numpy as np
from scipy.special import expit, logit
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier


def pack_tree(model, classification):
    t=model.tree_;v=t.value[:,0,:]
    values=v[:,1]/v.sum(axis=1) if classification else v[:,0]
    return {'left':t.children_left.tolist(),'right':t.children_right.tolist(),'feature':t.feature.tolist(),
            'threshold':t.threshold.tolist(),'value':values.tolist()}


def export(pipeline, names, schema):
    impute=pipeline.named_steps['impute'];model=pipeline.named_steps['model']
    a={'format':2,'schema':schema,'features':list(names),'medians':impute.statistics_.tolist(),
       'indicators':impute.indicator_.features_.tolist(),'calibration':[1.0,0.0]}
    if 'scale' in pipeline.named_steps:
        s=pipeline.named_steps['scale'];a.update(mean=s.mean_.tolist(),scale=s.scale_.tolist())
    if isinstance(model,LogisticRegression):
        a.update(kind='logistic',weights=model.coef_[0].tolist(),intercept=float(model.intercept_[0]))
    elif isinstance(model,GradientBoostingClassifier):
        a.update(kind='boosted',intercept=float(logit(model.init_.class_prior_[1])),learning_rate=model.learning_rate,
                 trees=[pack_tree(t[0],False) for t in model.estimators_])
    elif isinstance(model,(DecisionTreeClassifier,RandomForestClassifier)):
        trees=model.estimators_ if isinstance(model,RandomForestClassifier) else [model]
        a.update(kind='forest',trees=[pack_tree(t,True) for t in trees])
    else:raise ValueError('Unsupported portable model')
    return a


def transformed(artifact,features):
    if set(features)!=set(artifact['features']):raise ValueError('Feature schema mismatch')
    raw=np.array([np.nan if features[k] is None else features[k] for k in artifact['features']],dtype=float)
    if np.any(np.isinf(raw)):raise ValueError('Nonfinite input')
    missing=np.isnan(raw);z=np.where(missing,artifact['medians'],raw)
    if artifact['indicators']:z=np.r_[z,missing[artifact['indicators']].astype(float)]
    if 'mean' in artifact:z=(z-artifact['mean'])/artifact['scale']
    if not np.all(np.isfinite(z)):raise ValueError('Invalid transformed input')
    names=list(artifact['features'])+[artifact['features'][i]+'_missing' for i in artifact['indicators']]
    return z,names


def explain(artifact,features):
    z,names=transformed(artifact,features);delta=np.zeros(len(z));a,b=artifact['calibration']
    if artifact['kind']=='logistic':
        baseline=artifact['intercept'];delta=np.asarray(artifact['weights'])*z
        transform=lambda x:float(expit(a*logit(np.clip(expit(x),1e-6,1-1e-6))+b))
    else:
        trees=artifact['trees'];boosted=artifact['kind']=='boosted';baseline=artifact.get('intercept',0.0)
        for tree in trees:
            rate=artifact['learning_rate'] if boosted else 1/len(trees)
            baseline+=rate*tree['value'][0];node=0
            while tree['left'][node]!=-1:
                f=tree['feature'][node]
                child=tree['left'][node] if float(np.float32(z[f]))<=tree['threshold'][node] else tree['right'][node]
                delta[f]+=rate*(tree['value'][child]-tree['value'][node]);node=child
        transform=(lambda x:float(expit(a*logit(np.clip(expit(x),1e-6,1-1e-6))+b))) if boosted else (lambda x:float(expit(a*logit(np.clip(x,1e-6,1-1e-6))+b)))
    total=math.fsum(float(v) for v in delta);basep=transform(baseline);p=transform(baseline+total)
    if abs(total)>1e-12:multiplier=(p-basep)/total
    else:
        step=1e-6;multiplier=(transform(baseline+step)-transform(baseline-step))/(2*step)
    contributions=delta*multiplier*10
    residual=10*p-(10*basep+math.fsum(float(v) for v in contributions))
    # Only numerical roundoff is assigned; never repair a substantive mismatch.
    if abs(residual)>1e-8:raise ValueError('Explanation reconciliation failed')
    if len(contributions):contributions[int(np.argmax(np.abs(contributions)))]+=residual
    return {'score':10*p,'baseline':10*basep,
            'factors':[{'feature':name,'contribution':float(v)} for name,v in zip(names,contributions)],
            'explanation_method':'path-deltas-with-output-link-v1; associative, reference/path-dependent, not causal SHAP'}
