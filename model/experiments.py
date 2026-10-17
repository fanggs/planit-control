"""Small fixed experiment, with model selection restricted to validation sets.

Run from the repo root: python -m model.experiments
No cloud writes, wildlife outcome fabrication, 8/2 weighting or forecast-pilot reads.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import warnings

import numpy as np
import scipy
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             log_loss, precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

from model.data import FEATURES, ROOT, SEED, load_study, make_splits, sha256

CANDIDATES = ('constant_prior', 'month_only', 'shallow_tree', 'logistic', 'random_forest')
SELECTION_POLICY = (
    'Require AP above both constant and month-only baselines, and Brier below the constant '
    'baseline on EACH validation set. Of qualifying weather models, maximize mean '
    'validation AP; break ties by mean Brier then candidate name. If none qualify, '
    'report no supported winner. No tuning or refit using test or forecast-pilot data.'
)


def write_json(path, value, compact=False):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False,
                               indent=None if compact else 2) + '\n')


def matrix(rows):
    return np.array([[np.nan if r['features'][f] is None else r['features'][f]
                      for f in FEATURES] for r in rows], dtype=float)


def build_candidate(name):
    # No class reweighting or synthetic oversampling: probabilities are compared
    # against observed report frequencies, not an artificially balanced sample.
    if name == 'constant_prior':
        classifier = DummyClassifier(strategy='prior')
    elif name in ('month_only', 'logistic'):
        classifier = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED)
    elif name == 'shallow_tree':
        classifier = DecisionTreeClassifier(max_depth=4, min_samples_leaf=40, random_state=SEED)
    elif name == 'random_forest':
        classifier = RandomForestClassifier(n_estimators=128, max_depth=8,
                                            min_samples_leaf=30, max_features=0.8,
                                            random_state=SEED, n_jobs=1)
    else:
        raise ValueError('Unknown candidate')
    steps = [('impute', SimpleImputer(strategy='median', add_indicator=True))]
    if name in ('month_only', 'logistic'):
        steps.append(('scale', StandardScaler()))
    steps.append(('classifier', classifier))
    return Pipeline(steps)


def indices(name):
    return [FEATURES.index('month_sin'), FEATURES.index('month_cos')] if name == 'month_only' else list(range(len(FEATURES)))


def probability(model, x):
    p = model.predict_proba(x)[:, list(model.classes_).index(1)]
    if not np.all(np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError('Invalid predicted probability')
    return p


def measures(y, p):
    y = np.asarray(y); p = np.asarray(p)
    if len(y) != len(p) or not len(y) or not np.all(np.isin(y, [0, 1])):
        raise ValueError('Invalid evaluation labels or lengths')
    if not np.all(np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError('Invalid probabilities')
    positive = int(y.sum()); both = 0 < positive < len(y)
    calibration = []
    for low, high in zip((0, .1, .2, .4, .6, .8), (.1, .2, .4, .6, .8, 1.000001)):
        mask = (p >= low) & (p < high)
        if mask.any():
            calibration.append({'lower': low, 'upper': min(high, 1), 'count': int(mask.sum()),
                                'mean_prediction': float(p[mask].mean()), 'reported_fraction': float(y[mask].mean())})
    return {'rows': len(y), 'positives': positive, 'prevalence': float(y.mean()),
            'average_precision': float(average_precision_score(y, p)) if positive else None,
            'roc_auc': float(roc_auc_score(y, p)) if both else None,
            'brier': float(brier_score_loss(y, p)),
            'log_loss': float(log_loss(y, p, labels=[0, 1])),
            'precision_at_0_5': float(precision_score(y, p >= .5, zero_division=0)),
            'recall_at_0_5': float(recall_score(y, p >= .5, zero_division=0)) if positive else None,
            'confusion_at_0_5_tn_fp_fn_tp': confusion_matrix(y, p >= .5, labels=[0, 1]).ravel().tolist(),
            'calibration_bins': calibration}


def daily_ranking(rows, p):
    """A hypothetical review budget, not a safety-alert threshold."""
    days = defaultdict(list)
    for i, row in enumerate(rows):
        days[row['cutoff_at']].append(i)
    selected = []
    for positions in days.values():
        # Deterministic label-independent tie breaking (especially for the prior).
        ordered = sorted(positions, key=lambda i: (-p[i], hashlib.sha256(
            f'{SEED}:{rows[i]["cutoff_at"]}:{rows[i]["county_fips"]}'.encode()).hexdigest()))
        selected.extend(ordered[:max(1, math.ceil(len(positions) * .1))])
    captured = sum(rows[i]['reported_event'] for i in selected)
    positives = sum(r['reported_event'] for r in rows)
    return {'budget': 'ceil(10% of evaluated sites per UTC day)', 'selected': len(selected),
            'selected_fraction': len(selected) / len(rows),
            'precision': captured / len(selected), 'recall': captured / positives if positives else None}


def evaluate(model, x, rows):
    p = probability(model, x)
    result = measures([r['reported_event'] for r in rows], p)
    result['daily_review'] = daily_ranking(rows, p)
    result['regions'] = {}
    for region in sorted({r['hazard_region'] for r in rows}):
        positions = [i for i, r in enumerate(rows) if r['hazard_region'] == region]
        result['regions'][region] = measures([rows[i]['reported_event'] for i in positions], p[positions])
    return result, p


def choose_candidate(validation):
    eligible = []
    for name in ('shallow_tree', 'logistic', 'random_forest'):
        sets = validation[name]
        if all(sets[part]['average_precision'] > max(validation[b][part]['average_precision']
                                                   for b in ('constant_prior', 'month_only'))
               and sets[part]['brier'] < validation['constant_prior'][part]['brier']
               for part in ('temporal_validation', 'geographic_validation')):
            ap = np.mean([v['average_precision'] for v in sets.values()])
            brier = np.mean([v['brier'] for v in sets.values()])
            eligible.append((-float(ap), float(brier), name))
    return min(eligible)[2] if eligible else None


def tree_payload(classifier):
    tree = classifier.tree_
    values = tree.value[:, 0, :]
    # sklearn versions may store counts or proportions; normalize explicitly.
    p = values[:, 1] / values.sum(axis=1)
    return {'left': tree.children_left.tolist(), 'right': tree.children_right.tolist(),
            'feature': tree.feature.tolist(), 'threshold': tree.threshold.tolist(),
            'probability': p.tolist(), 'samples': tree.n_node_samples.tolist()}


def export_model(name, pipeline):
    imputer = pipeline.named_steps['impute']; classifier = pipeline.named_steps['classifier']
    data = {'format_version': 1, 'candidate': name, 'feature_columns': list(FEATURES),
            'feature_indices': indices(name), 'imputer_medians': imputer.statistics_.tolist(),
            'missing_indicator_indices': imputer.indicator_.features_.tolist(),
            'model_promotion_eligible': False}
    if 'scale' in pipeline.named_steps:
        scale = pipeline.named_steps['scale']
        data.update(scaler_mean=scale.mean_.tolist(), scaler_scale=scale.scale_.tolist())
    if isinstance(classifier, LogisticRegression):
        data.update(kind='logistic', coefficients=classifier.coef_[0].tolist(), intercept=float(classifier.intercept_[0]))
    elif isinstance(classifier, DecisionTreeClassifier):
        data.update(kind='tree', trees=[tree_payload(classifier)])
    elif isinstance(classifier, RandomForestClassifier):
        data.update(kind='forest', trees=[tree_payload(tree) for tree in classifier.estimators_])
    else:
        data.update(kind='constant', probability=float(classifier.class_prior_[1]))
    return data


def portable_predict(artifact, x):
    """Round-trip verification for JSON export; production adapter is interval 6."""
    z = np.asarray(x, dtype=float)[:, artifact['feature_indices']].copy()
    missing = np.isnan(z)
    z = np.where(missing, np.asarray(artifact['imputer_medians']), z)
    columns = artifact['missing_indicator_indices']
    if columns:
        z = np.column_stack([z, missing[:, columns].astype(float)])
    if 'scaler_mean' in artifact:
        z = (z - artifact['scaler_mean']) / artifact['scaler_scale']
    if artifact['kind'] == 'logistic':
        from scipy.special import expit
        return expit(z @ np.asarray(artifact['coefficients']) + artifact['intercept'])
    if artifact['kind'] == 'constant':
        return np.full(len(z), artifact['probability'])
    result = np.zeros(len(z))
    # sklearn trees compare float32 inputs; preserve the same boundary behavior.
    z = z.astype(np.float32)
    for tree in artifact['trees']:
        for i, row in enumerate(z):
            node = 0
            while tree['left'][node] != -1:
                node = tree['left'][node] if float(row[tree['feature'][node]]) <= tree['threshold'][node] else tree['right'][node]
            result[i] += tree['probability'][node]
    return result / len(artifact['trees'])


def run(manifest_path, output_root):
    rows, provenance = load_study(manifest_path)
    splits, split_audit = make_splits(rows)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = Path(output_root) / stamp; output.mkdir(parents=True, exist_ok=False)
    x_train = matrix(splits['train']); y_train = np.array([r['reported_event'] for r in splits['train']])
    models = {}; validation = {}; configurations = {}; exported = {}
    with warnings.catch_warnings(), threadpool_limits(limits=1):
        warnings.simplefilter('error', ConvergenceWarning)
        for name in CANDIDATES:
            model = build_candidate(name)
            model.fit(x_train[:, indices(name)], y_train)
            models[name] = model
            configurations[name] = model.named_steps['classifier'].get_params()
            validation[name] = {}
            for part in ('temporal_validation', 'geographic_validation'):
                validation[name][part], _ = evaluate(model, matrix(splits[part])[:, indices(name)], splits[part])
            artifact = export_model(name, model)
            # Check all training and validation windows, including optional missingness.
            check_rows = splits['train'] + splits['temporal_validation'] + splits['geographic_validation']
            check_x = matrix(check_rows)
            delta = float(np.max(np.abs(portable_predict(artifact, check_x) - probability(model, check_x[:, indices(name)]))))
            if delta > 1e-12:
                raise ValueError(f'JSON export round trip failed for {name}: {delta}')
            artifact['export_max_absolute_error'] = delta
            write_json(output / f'{name}.json', artifact, compact=True)
            exported[name] = sha256(output / f'{name}.json')
        selected = choose_candidate(validation)
        # Freeze the decision on disk BEFORE evaluating any final-test predictions.
        write_json(output / 'selection.json', {'policy': SELECTION_POLICY, 'selected': selected,
                                              'validation': validation, 'candidate_hashes': exported})
        importance = {}
        # Diagnostic feature evidence for each weather candidate, on validation
        # only. These results do not trigger feature removal or another search.
        for candidate in ('shallow_tree', 'logistic', 'random_forest'):
            importance[candidate] = {}
            for part in ('temporal_validation', 'geographic_validation'):
                study = splits[part]
                result = permutation_importance(models[candidate], matrix(study), [r['reported_event'] for r in study],
                                                scoring='average_precision', n_repeats=5, random_state=SEED, n_jobs=1)
                importance[candidate][part] = sorted([{'feature': f, 'mean_ap_drop': float(mean), 'repeat_std': float(std)}
                                           for f, mean, std in zip(FEATURES, result.importances_mean, result.importances_std)],
                                          key=lambda item: -item['mean_ap_drop'])
        # No refit on validation: the tested/exported model is exactly the one selected.
        final_test = {}
        tested = list(dict.fromkeys(['constant_prior', 'month_only'] + ([selected] if selected else [])))
        for name in tested:
            final_test[name] = {}
            for part in ('temporal_test', 'geographic_test'):
                final_test[name][part], p = evaluate(models[name], matrix(splits[part])[:, indices(name)], splits[part])
                write_json(output / f'{name}-{part}-predictions.json',
                           [{'site_id': r['site_id'], 'cutoff_at': r['cutoff_at'], 'reported_event': r['reported_event'],
                             'probability': float(pred)} for r, pred in zip(splits[part], p)], compact=True)
    report = {'experiment_version': 'weather-association-v1', 'created_at': stamp,
              'provenance': provenance, 'split_audit': split_audit,
              'selection_policy': SELECTION_POLICY, 'selected_candidate': selected,
              'configurations': configurations, 'validation': validation, 'final_test': final_test,
              'validation_permutation_importance': importance, 'candidate_hashes': exported,
              'selection_record_sha256': sha256(output / 'selection.json'),
              'code_hashes': {f'model/{name}': sha256(ROOT / 'model' / name) for name in ('data.py', 'experiments.py')},
              'environment': {'python': platform.python_version(), 'sklearn': sklearn.__version__,
                              'numpy': np.__version__, 'scipy': scipy.__version__},
              'local_output_directory': str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
              'model_promotion_eligible': False,
              'limitations': [
                  'Target is a documented county/zone event report, not plant injury or confirmed safe/unsafe conditions.',
                  'Inputs are realized reanalysis during the outcome window; this tests associations, not forecast skill.',
                  'One partial year, 60 selected sites, correlated weather episodes and reporting bias limit generalization.',
                  'Final tests share seasons and may share storms; they are not independent replications.',
                  'Zero means no applicable published report, not absence of hazard.',
                  'No wildlife absence labels, combined hazard score, 8/2 weights or direct soil-saturation outcome.',
                  'Forecast pilot remains sealed; publication latency and input-distribution shift remain unresolved.',
                  'Permutation importance is validation association, not causal or per-hazard attribution.',
                  'Threshold 0.5 and 10% review budget are diagnostics, not approved safety or alert policies.',
                  'Do not tune on the final tests after reading this report; a new claim needs fresh held-out evidence.'
              ]}
    write_json(output / 'results.json', report)
    # Publish small audit/results locally only after the entire experiment succeeds.
    write_json(ROOT / 'model/generated/experiment-results.json', report)
    for name in CANDIDATES:
        artifact = json.loads((output / f'{name}.json').read_text())
        write_json(ROOT / f'model/generated/candidates/{name}.json', artifact, compact=True)
    if selected:
        selected_artifact = json.loads((output / f'{selected}.json').read_text())
        selected_artifact.update(experiment_version=report['experiment_version'],
                                 training_data_sha256=provenance['data_sha256'],
                                 target_definition=provenance['target_definition'])
        write_json(ROOT / 'model/generated/selected-candidate.json', selected_artifact, compact=True)
    elif (ROOT / 'model/generated/selected-candidate.json').exists():
        (ROOT / 'model/generated/selected-candidate.json').unlink()
    print(f'Experiment complete. Validation-selected candidate: {selected or "none qualified"}.')
    print(f'Results: {output / "results.json"}. Forecast pilot unopened; production promotion disabled.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/raw/history/latest.json')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'data/raw/model/runs')
    args = parser.parse_args()
    try:
        run(args.manifest, args.output_root.resolve())
    except (ValueError, KeyError, OSError, ConvergenceWarning) as exc:
        parser.exit(1, f'Experiment failed: {exc}\n')


if __name__ == '__main__':
    main()
