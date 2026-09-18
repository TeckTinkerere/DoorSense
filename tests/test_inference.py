"""Regression boundaries that protect the frozen model and supplied format."""
import hashlib
import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from doorlens.inference import (COLUMNS, FEATURE_NAMES, I, P, PROBES, FrozenModel,
    InputError, apply_probe, parse_csv, parse_timestamp, trace_payload)

APP = Path(__file__).resolve().parents[1]
MODELS = APP/'backend/doorlens/models'
SOURCE_ROOT = Path(os.environ.get('DOORLENS_SOURCE_ROOT',
    APP.parent/'NebulaX-Hackathon-ProblemStatement'/'PS3'))
DATA = SOURCE_ROOT/'02_Datasets/Door'

@pytest.fixture
def demo():
    source = json.loads((MODELS/'demo.json').read_text(encoding='utf-8'))
    return parse_csv(pd.DataFrame(source['rows'],columns=source['columns']).to_csv(index=False).encode())[0]

def encode(frame):
    return frame[COLUMNS].to_csv(index=False).encode()

def test_native_millisecond_components_and_deterministic_axis():
    assert parse_timestamp('2023-7-5-0-0-0-8')-parse_timestamp('2023-7-5-0-0-0-0') == pytest.approx(.008,abs=1e-6)
    assert parse_timestamp('1970-1-1-0-0-0-0') == 0
    for bad in ['2023-2-29-0-0-0-0','2023-1-1-0-0-0-1000','2023-01-01T00:00:00Z','2023-1-1-25-0-0-0']:
        with pytest.raises(InputError,match='timestamp'):
            parse_timestamp(bad)

def test_real_train_boundaries_preserved_and_all_rows_classifiable():
    content=(DATA/'Train.csv').read_bytes()
    cycles=parse_csv(content)
    labels=pd.read_csv(DATA/'Train_Segments_Answer.csv')
    assert len(cycles)==110 and sum(map(len,cycles))==18036
    model=FrozenModel.load(MODELS/'final')
    for cycle,label in zip(cycles,labels.itertuples()):
        assert (cycle.Datetime.iloc[0],cycle.Datetime.iloc[-1],len(cycle))==(label.start_time,label.end_time,label.n_rows)
        assert model.predict(cycle)['prediction'] in ('Normal','Abnormal resistance')
    assert model.metadata['feature_names']==FEATURE_NAMES

def test_unlabelled_test_structure_is_supported_without_fitting():
    # Compatibility only. No test labels exist and this makes no accuracy claim.
    before=hashlib.sha256((MODELS/'final/model.json').read_bytes()).hexdigest()
    cycles=parse_csv((DATA/'Test.csv').read_bytes())
    assert len(cycles)==38 and sum(map(len,cycles))==6253
    model=FrozenModel.load(MODELS/'final')
    for cycle in cycles:
        result=model.predict(cycle)
        assert 0<=result['score']<=1
    assert before==hashlib.sha256((MODELS/'final/model.json').read_bytes()).hexdigest()

def test_frozen_demo_and_every_probe_match_saved_research(demo):
    recorded=json.loads((SOURCE_ROOT/'research/signature_results/sensitivity.json').read_text())
    expected=next(r for r in recorded['details'] if r['segment_id']=='train_seg_017' and r['model']=='phase')
    model=FrozenModel.load(MODELS/'demo-fold-0')
    before=demo.copy(deep=True)
    assert model.metadata['training_indices_zero_based']==list(range(24,88))
    assert model.predict(demo)['score']==pytest.approx(expected['original']['model_score'],abs=1e-9)
    for probe in PROBES:
        changed=apply_probe(demo,probe['id'])
        prediction=model.predict(changed)
        assert prediction['score']==pytest.approx(expected['probes'][probe['id']]['model_score'],abs=1e-9)
        assert (prediction['prediction']=='Abnormal resistance')==bool(expected['probes'][probe['id']]['label'])
        pd.testing.assert_frame_equal(demo,before)
        assert changed.Datetime.iloc[0]==demo.Datetime.iloc[0] and changed.Datetime.iloc[-1]==demo.Datetime.iloc[-1]
    assert len(model.features(demo))==21

def test_mutated_model_rejected_before_loading(tmp_path):
    for name in ('manifest.json','model.json'):
        (tmp_path/name).write_bytes((MODELS/'final'/name).read_bytes())
    (tmp_path/'model.json').write_bytes((tmp_path/'model.json').read_bytes()+b' ')
    with pytest.raises(ValueError,match='checksum'):
        FrozenModel.load(tmp_path)

def test_references_are_direction_matched_descriptive_bands(demo):
    model=FrozenModel.load(MODELS/'demo-fold-0')
    reference=model.reference(demo)
    assert reference['sample_count']>0
    assert 'not a confidence interval' in reference['provenance']
    assert len(reference['progress'])==10
    assert np.all(np.array(reference['current_lower_a'])<=reference['current_median_a'])
    assert np.all(np.array(reference['current_upper_a'])>=reference['current_median_a'])
    assert trace_payload(demo)['position']==demo[P].tolist()

@pytest.mark.parametrize('alteration,code',[
    ('duplicate_header','duplicate_columns'),('missing_numeric','non_finite'),
    ('infinite','non_finite'),('binary','binary_values'),('direction','cycle_direction'),
    ('truncated','incomplete_cycle'),('unknown_sampling','sampling_structure'),
    ('non_monotonic','timestamp_order'),('malformed_row','invalid_csv')])
def test_rejects_corrupted_recordings_without_silent_repair(demo,alteration,code):
    frame=demo.copy(deep=True)
    if alteration=='missing_numeric': frame[I]=frame[I].astype(object);frame.loc[2,I]=''
    elif alteration=='infinite': frame[I]=frame[I].astype(float);frame.loc[2,I]=np.inf
    elif alteration=='binary': frame.loc[2,'DCSR']=2
    elif alteration=='direction': frame.loc[2,'Door is opening']=0
    elif alteration=='truncated': frame=frame.iloc[:-40]
    elif alteration=='unknown_sampling': frame=frame.iloc[::2]
    elif alteration=='non_monotonic': frame.loc[2,'Datetime']=frame.loc[1,'Datetime']
    content=encode(frame)
    if alteration=='duplicate_header': content=content.replace(b'Motor current(mA)',b'Datetime',1)
    elif alteration=='malformed_row': content=content+b'1,2,3\n'
    with pytest.raises(InputError) as error:
        parse_csv(content)
    assert error.value.code==code

def test_extra_metadata_columns_cannot_become_features_and_bom_is_supported(demo):
    frame=demo[COLUMNS].copy()
    frame['status']='Normal'  # A stray label column must not become a model input.
    actual=parse_csv(b'\xef\xbb\xbf'+frame.to_csv(index=False).encode())[0]
    pd.testing.assert_frame_equal(actual,demo)

def test_no_movement_rejected_without_inventing_physical_position_limits(demo):
    moved=demo.copy(deep=True)
    moved[P]=42
    model=FrozenModel.load(MODELS/'final')
    with pytest.raises(InputError) as error:
        model.predict(moved)
    assert error.value.code=='incomplete_cycle'

def test_finite_extreme_values_cannot_overflow_into_imputed_predictions(demo):
    huge=demo.copy(deep=True)
    huge[I]=huge[I].astype(float)*1e300
    assert np.isfinite(huge[I]).all()
    model=FrozenModel.load(MODELS/'final')
    with pytest.raises(InputError) as error:
        model.predict(huge)
    assert error.value.code=='numerical_range'
