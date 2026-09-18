"""Package the already selected research model; never invoked by uploaded data.

No arguments rebuild the bundled artifacts from the read-only research inputs.
--verify rebuilds in temporary storage and checks the existing package without
overwriting it. Neither mode selects a model, threshold, or probe.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import os
import sys
import tempfile

APP = Path(__file__).resolve().parents[1]
def locate_source_root() -> Path:
    """Find the optional original Nebula source bundle used for reproduction."""
    configured = os.environ.get('DOORLENS_SOURCE_ROOT')
    candidates = ([Path(configured)] if configured else []) + [
        APP.parent / 'NebulaX-Hackathon-ProblemStatement' / 'PS3',
        APP.parent,
    ]
    for candidate in candidates:
        if (candidate/'02_Datasets/Door/Train.csv').is_file() and (candidate/'research/offline_benchmark.py').is_file():
            return candidate.resolve()
    raise RuntimeError(
        'Original Nebula PS3 sources were not found. Set DOORLENS_SOURCE_ROOT to the '
        'directory containing 02_Datasets and research. Runtime inference does not need them.'
    )

PS3 = locate_source_root()
sys.path[:0] = [str(APP / 'backend'), str(PS3 / 'research')]
import numpy as np
import pandas as pd
import offline_benchmark as research
import signature_probe as signature
from doorlens.inference import COLUMNS, FEATURE_NAMES, PROBES, FrozenModel, apply_probe, parse_csv

DESTINATION = APP / 'backend/doorlens/models'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False, ensure_ascii=False)+'\n', encoding='utf-8')

def make_payload(cycles, y, training, model_id, label, source_hashes):
    frozen = signature.FrozenFold(cycles, y, training)
    parameters, support = {}, {}
    for d in (0, 1):
        members = [k for k in training if research.direction(cycles[k]) == d]
        normals = [research.profile(cycles[k]) for k in members if y[k] == 0]
        reference_median, reference_scale = frozen.refs[d]
        fill, center, scale, coefficients = frozen.models[d]
        parameters[str(d)] = {name: value.tolist() for name, value in {
            'reference_median': reference_median, 'reference_scale': reference_scale,
            'reference_lower': np.nanquantile(normals, .1, axis=0),
            'reference_upper': np.nanquantile(normals, .9, axis=0),
            'fill': fill, 'center': center, 'scale': scale, 'coefficients': coefficients}.items()}
        parameters[str(d)]['normal_count'] = len(normals)
        support[str(d)] = {}
        for index, name in ((0, 'start'), (-1, 'end')):
            endpoints = [float(cycles[k][research.P].iloc[index]) for k in members]
            support[str(d)][name] = [min(endpoints), max(endpoints)]
    metadata = {
        'model_id': model_id, 'model_label': label, 'version': '1.0.0',
        'feature_names': FEATURE_NAMES, 'input_columns': COLUMNS,
        'decision_threshold': .5, 'selected_kind': 'phase', 'l2_lambda': 1,
        'training_indices_zero_based': list(map(int, training)),
        'training_cycle_count': len(training), 'source_sha256': source_hashes,
        'training_dependencies': {'numpy': np.__version__, 'pandas': pd.__version__},
        'training_python': platform.python_version(),
        'endpoint_training_range': support,
        'endpoint_range_note': 'Observed training range only; not a physical limit or rejection threshold. Completeness is checked against recorded endpoint states and movement structure.',
        'score_note': 'Uncalibrated model score, not confidence or safety probability.',
        'segmentation': 'Split strictly increasing native timestamps at gaps greater than 1 second.',
        'selection': 'Previously frozen development selection; no additional model or threshold tuning.',
    }
    return {'metadata': metadata, 'parameters': parameters}

def write_model(folder, payload):
    save(folder/'model.json', payload)
    save(folder/'manifest.json', {'model_id': payload['metadata']['model_id'],
        'version': '1.0.0', 'format': 'JSON arrays; no executable serialization',
        'artifacts': {'model.json': digest(folder/'model.json')}})
    return FrozenModel.load(folder)

def reproduce(destination):
    selection = json.loads((PS3/'research/offline_results/frozen_selection.json').read_text())
    assert selection['kind'] == 'phase' and selection['lambda'] == 1, 'Selected model changed; review packaging explicitly.'
    source_paths = ['02_Datasets/Door/Train.csv', '02_Datasets/Door/Train_Segments_Answer.csv',
        'research/offline_benchmark.py', 'research/signature_probe.py',
        'research/offline_results/frozen_selection.json',
        'research/offline_results/dev_current_0.csv', 'research/offline_results/dev_phase_1.csv',
        'research/offline_results/reserve_current_0.csv', 'research/offline_results/reserve_phase_1.csv',
        'research/signature_results/sensitivity.json', 'research/OFFLINE_EXPERIMENT_PLAN.md',
        'research/SIGNATURE_EXPERIMENT_PLAN.md']
    source_hashes = {path: digest(PS3/path) for path in source_paths}
    source_hashes['backend/doorlens/inference/core.py'] = digest(APP/'backend/doorlens/inference/core.py')
    data, labels, research_cycles, y = research.load()
    cycles = parse_csv((PS3/source_paths[0]).read_bytes())
    assert len(cycles) == len(research_cycles) == len(labels)
    # The original script uses naive timestamps. Only relative timing is used by
    # its features; retain the new parser's explicit timezone-independent axis.
    for a, b in zip(cycles, research_cycles):
        assert a.Datetime.tolist() == b.Datetime.tolist()
        np.testing.assert_allclose(a._seconds-a._seconds.iloc[0], b._seconds-b._seconds.iloc[0], atol=1e-9)
    all_training = np.arange(len(cycles))
    final = write_model(destination/'final', make_payload(research_cycles, y, all_training,
        'doorlens-phase-final-v1', 'Final submission model · all 110 training cycles', source_hashes))
    demo = write_model(destination/'demo-fold-0', make_payload(research_cycles, y, np.arange(24,88),
        'doorlens-phase-dev-fold-0-v1', 'Development demonstration · fold 0 model', source_hashes))
    max_error, comparisons = 0., 0
    def compare(actual, expected):
        nonlocal max_error, comparisons
        actual, expected = np.atleast_1d(actual), np.atleast_1d(expected)
        error = float(np.max(np.abs(actual-expected)))
        max_error = max(max_error, error)
        comparisons += len(actual)
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-9)
        np.testing.assert_array_equal(actual >= .5, expected >= .5)

    compare([final.predict(c)['score'] for c in cycles],
        research.predict('phase', all_training, all_training, research_cycles, y, 1))
    expected_sensitivity = json.loads((PS3/'research/signature_results/sensitivity.json').read_text())
    saved_detail = {(r['segment_id'], r['model']): r for r in expected_sensitivity['details']}
    saved = {kind: pd.read_csv(PS3/f'research/offline_results/dev_{kind}_{lam}.csv')
             for kind, lam in (('current',0), ('phase',1))}
    changes = {kind: {p['id']: 0 for p in PROBES} for kind in saved}
    affected = {kind: 0 for kind in saved}
    reproduced_scores = {kind: [] for kind in saved}
    for fold in range(4):
        validation = np.arange(22*fold,22*(fold+1))
        training = [k for k in range(88) if k < validation[0]-2 or k > validation[-1]+2]
        payload = make_payload(research_cycles, y, training, f'verification-fold-{fold}', 'Verification only', source_hashes)
        model = FrozenModel(payload['metadata'], payload['parameters'])
        original_research = signature.FrozenFold(research_cycles, y, training)
        for k in validation:
            cycle = cycles[k]
            for kind in saved:
                original = model.predict(cycle)['score'] if kind == 'phase' else original_research.predict(cycle,kind)['model_score']
                reproduced_scores[kind].append(original)
                compare(original, saved[kind].iloc[k].score)
                detail = saved_detail[(str(labels.iloc[k].segment_id), kind)]
                changed = False
                for probe in PROBES:
                    name = probe['id']
                    altered = apply_probe(cycle,name)
                    # Independent research probe implementation, including exact
                    # dropped-sample indices, must produce identical inputs.
                    pd.testing.assert_frame_equal(altered,signature.probe(cycle,name))
                    score = model.predict(altered)['score'] if kind == 'phase' else original_research.predict(altered,kind)['model_score']
                    compare(score,detail['probes'][name]['model_score'])
                    compare(score,original_research.predict(altered,kind)['model_score'])
                    flip = bool((score>=.5)!=(original>=.5))
                    changes[kind][name] += int(flip)
                    changed |= flip
                affected[kind] += int(changed)
    for kind in saved:
        assert affected[kind] == expected_sensitivity['summary'][kind]['cycles_with_any_label_change']
        assert changes[kind] == expected_sensitivity['summary'][kind]['label_changes_by_probe']

    # Reproduce the old reserve result solely as a packaging regression check.
    # It was already examined and is NOT a new or independent holdout.
    reserve = {}
    for kind, lam in (('current',0), ('phase',1)):
        scores = research.predict(kind,np.arange(86),np.arange(88,110),research_cycles,y,lam)
        old = pd.read_csv(PS3/f'research/offline_results/reserve_{kind}_{lam}.csv')
        compare(scores,old.score.to_numpy())
        reserve[kind] = research.metrics(y[88:],(scores>=.5).astype(int))
    demo_original = demo.predict(cycles[16])
    demo_probes = {p['id']: demo.predict(apply_probe(cycles[16],p['id'])) for p in PROBES}
    compare(demo_original['score'],saved_detail[('train_seg_017','phase')]['original']['model_score'])
    demo_frame = cycles[16][COLUMNS]
    save(destination/'demo.json', {'columns': COLUMNS, 'rows': demo_frame.values.tolist(),
        'cycle_id': 'train_seg_017', 'source': 'Recorded Train.csv cycle 17; development fold 0 validation example.',
        'source_sha256': source_hashes['02_Datasets/Door/Train.csv']})
    development = {kind: research.metrics(y[:88],(np.array(scores)>=.5).astype(int))
                   for kind,scores in reproduced_scores.items()}
    evidence = {
        'title': 'Saved experiment, reproduced during model packaging',
        'model_description': 'Direction-specific logistic models, 12 cycle summaries and 9 relative-travel reference residuals; L2 = 1, decision threshold = 0.5.',
        'metric': 'Exact supplied interval boundaries were reproduced; same-label IoU-weighted F1 therefore equals cycle accuracy here. Abnormal-class recall is a separate metric.',
        'scope': expected_sensitivity['scope'],
        'development': {'n':88,'current_correct':development['current']['tp']+development['current']['tn'],
            'phase_correct':development['phase']['tp']+development['phase']['tn'], 'abnormal':int(y[:88].sum()),'normal':int((y[:88]==0).sum()),
            'current_metrics':development['current'],'phase_metrics':development['phase']},
        'reserve': {'n':22,'current_correct':reserve['current']['tp']+reserve['current']['tn'],
            'phase_correct':reserve['phase']['tp']+reserve['phase']['tn'],'abnormal':int(y[88:].sum()),'normal':int((y[88:]==0).sum()),
            'current_metrics':reserve['current'],'phase_metrics':reserve['phase']},
        'sensitivity': {'n':88,'current_affected':affected['current'],'phase_affected':affected['phase'],
            'probes':[{'id':p['id'],'label':p['label'],'current_changes':changes['current'][p['id']],
                       'phase_changes':changes['phase'][p['id']]} for p in PROBES]},
        'limitations': [
            'The 22-cycle reserve was previously examined; reproducing it does not make it a fresh holdout.',
            'No original asset or collection-run identities are available; independence and fleet generalisation cannot be established.',
            'Both models achieved 22/22 on that small reserve. No demonstrated reserve accuracy advantage justifies additional complexity.',
            'Sensitivity probes are assumed recording changes, not calibrated sensor tolerances or new labelled fault examples.',
            'Stability does not establish correctness; no safe-to-depart, component diagnosis, or remaining-life claim is made.',
            'Recorded Test.csv has no available ground truth. Its predictions are not accuracy evidence.'],
        'sources': [{'label': name, 'path': '../research/'+name} for name in
            ['OFFLINE_EXPERIMENT_PLAN.md','SIGNATURE_EXPERIMENT_PLAN.md','offline_results/benchmark.json','signature_results/sensitivity.json']],
        'verification': {'verified_at': 'Reproduced by scripts/package_models.py; see artifacts/parity-report.json for run time.',
            'parity_max_abs_error': max_error, 'signature_reproduced': True},
    }
    save(destination/'evidence.json',evidence)
    current_hashes = {path: digest(PS3 / path) for path in source_paths}
    current_hashes['backend/doorlens/inference/core.py'] = digest(
        APP / 'backend' / 'doorlens' / 'inference' / 'core.py'
    )
    assert source_hashes == current_hashes, 'Packaging inputs changed during reproduction'
    return {'verified_at': datetime.now(timezone.utc).isoformat(), 'comparisons': comparisons,
        'parity_max_abs_error':max_error,'tolerance':1e-9,'predicted_labels_identical':True,
        'train_cycles':len(cycles),'train_rows':len(data),'signature_reproduced':True,
        'development':development,'previously_examined_reserve':reserve,
        'sensitivity':evidence['sensitivity'],'demo_original':demo_original,'demo_probes':demo_probes,
        'source_sha256':source_hashes,'test_used_for_packaging':False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args = parser.parse_args()
    if args.verify:
        with tempfile.TemporaryDirectory(prefix='doorlens-parity-') as folder:
            temporary = Path(folder)
            report = reproduce(temporary)
            max_parameter_error = 0.
            for path in temporary.rglob('*.json'):
                existing = DESTINATION/path.relative_to(temporary)
                assert existing.exists(), f'Missing bundled artifact: {existing}'
                a,b = json.loads(existing.read_text(encoding='utf-8')),json.loads(path.read_text(encoding='utf-8'))
                if path.name == 'manifest.json':
                    FrozenModel.load(existing.parent)  # Validate existing bytes against their own hash.
                    assert a['model_id'] == b['model_id'] and a['version'] == b['version']
                    continue
                if path.name == 'model.json':
                    for direction in a['parameters']:
                        for key,actual in a['parameters'][direction].items():
                            expected=b['parameters'][direction][key]
                            np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-9,
                                err_msg=f'Bundled parameter differs: {direction}/{key}')
                            max_parameter_error=max(max_parameter_error,float(np.max(np.abs(np.asarray(actual)-expected))))
                    assert set(a['parameters'])==set(b['parameters'])
                    assert all(set(a['parameters'][d])==set(b['parameters'][d]) for d in a['parameters'])
                    # Python patch provenance is preserved in the original
                    # package, but a compatible 3.12 patch is allowed to verify it.
                    a['metadata'].pop('training_python',None)
                    b['metadata'].pop('training_python',None)
                    a.pop('parameters'); b.pop('parameters')
                elif path.name == 'evidence.json':
                    assert a['verification']['parity_max_abs_error']<=1e-9
                    assert b['verification']['parity_max_abs_error']<=1e-9
                    a['verification'].pop('parity_max_abs_error')
                    b['verification'].pop('parity_max_abs_error')
                assert a == b, f'Artifact differs from reproducible package: {existing}'
            report['existing_package_max_parameter_error']=max_parameter_error
            report['existing_package_hashes_verified']=True
            report['verification_python']=platform.python_version()
    else:
        report = reproduce(DESTINATION)
    save(APP/'artifacts/parity-report.json',report)
    print(json.dumps({key:report[key] for key in ['comparisons','parity_max_abs_error','signature_reproduced','test_used_for_packaging']},indent=2))

if __name__ == '__main__':
    main()
