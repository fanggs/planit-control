import unittest
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier,GradientBoostingClassifier
from model.portable import export,explain
from model.batch_predict import predict

class BatchPredictTests(unittest.TestCase):
    def test_matches_explanations_for_all_families_and_missing_indicators(self):
        rng=np.random.default_rng(42);x=rng.normal(size=(120,2));y=(x[:,0]+x[:,1]>0).astype(int);x[::4,1]=np.nan
        rows=[dict(a=float(a),b=None if np.isnan(b) else float(b)) for a,b in x[:30]]
        for estimator in (LogisticRegression(),DecisionTreeClassifier(max_depth=3),RandomForestClassifier(n_estimators=8,max_depth=3,random_state=1),GradientBoostingClassifier(n_estimators=8,max_depth=2,random_state=1)):
            model=Pipeline([('impute',SimpleImputer(add_indicator=True)),('scale',StandardScaler()),('model',estimator)]).fit(x,y)
            artifact=export(model,['a','b'],'test');artifact['calibration']=[1.2,-.3]
            expected=[explain(artifact,row)['score']/10 for row in rows]
            np.testing.assert_allclose(predict(artifact,rows),expected,atol=1e-12,rtol=1e-12)
