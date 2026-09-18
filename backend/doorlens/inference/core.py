"""Recorded-cycle contract, exact research features, and trusted frozen models.

No runtime fitting, calibration, automatic repair, or reference updates.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

I, V, E, P = 'Motor current(mA)', 'Motor Voltage(10mV)', 'Motor electrodynamic force', 'Door leaf position'
COLUMNS = ['Datetime', I, V, E, 'Door opening time(.1s)', 'Door closing time(.1s)',
           'Close command', 'Open command', 'DCSR', 'DCSL', 'DLSR', 'DLSL',
           'Door Opened', 'Door Locked', 'Door is opening', 'Door is closing', P]
BASE_NAMES = ['current_mean_A', 'current_p90_A', 'current_sd_A', 'voltage_mean_V',
              'back_emf_mean_raw', 'duration_s', 'stroke_counts', 'start_counts',
              'end_counts', 'speed_p90_counts_s', 'stationary_fraction', 'integrated_abs_vi_proxy']
FEATURE_NAMES = BASE_NAMES + [f'{channel}_reference_{summary}' for channel in ['current','voltage','back_emf']
                              for summary in ['median','p90','positive_mean']]
PROBES = [
    {'id':'current_minus_5pct','label':'Current −5%','description':'Multiply recorded motor current by 0.95; all other channels stay unchanged.'},
    {'id':'current_plus_5pct','label':'Current +5%','description':'Multiply recorded motor current by 1.05; all other channels stay unchanged.'},
    {'id':'voltage_minus_5pct','label':'Voltage −5%','description':'Multiply recorded motor voltage by 0.95; all other channels stay unchanged.'},
    {'id':'voltage_plus_5pct','label':'Voltage +5%','description':'Multiply recorded motor voltage by 1.05; all other channels stay unchanged.'},
    {'id':'drop_each_20th_interior','label':'Sparse sample removal','description':'Remove indices 20, 40, 60… within this recorded cycle, keeping its first and last samples.'},
]

class InputError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

def parse_timestamp(value: str) -> float:
    """Native seven integer components; milliseconds are literal, not padded fractions.

    A UTC coordinate is used for timezone-independent plotting. The input contains
    no timezone, so it does not assert the original operator's timezone.
    """
    try:
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,3}',value):
            raise ValueError()
        pieces = [int(v) for v in value.split('-')]
        return datetime(*pieces[:6],microsecond=pieces[6]*1000,tzinfo=timezone.utc).timestamp()
    except (ValueError, OverflowError, OSError, TypeError):
        raise InputError('timestamp_format',f'Invalid timestamp {str(value)[:70]!r}. Use Year-Month-Day-Hour-Minute-Second-Millisecond, with milliseconds from 0 to 999.') from None

def parse_csv(content: bytes, max_rows: int = 300_000) -> tuple[pd.DataFrame,...]:
    if not content or not content.strip():
        raise InputError('empty_file','The CSV is empty. Upload a recorded Door telemetry file.')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise InputError('encoding','Use a UTF-8 CSV file with the original Door column headers.') from None
    if '\x00' in text:
        raise InputError('invalid_csv','The file contains binary data, not supported CSV text.')
    try:
        reader = csv.reader(io.StringIO(text),strict=True)
        header = next(reader)
    except (csv.Error,StopIteration):
        raise InputError('invalid_csv','The CSV header could not be read.') from None
    if len(header)!=len(set(header)):
        raise InputError('duplicate_columns','Duplicate column names are ambiguous. Restore the original Door headers.')
    missing = [name for name in COLUMNS if name not in header]
    if missing:
        raise InputError('missing_columns','Missing required columns: '+', '.join(missing))
    # Count and validate record widths before pandas allocation; accept extra columns
    # without allowing them to affect features or identity.
    count=0
    try:
        for row in reader:
            if not row: continue
            count+=1
            if count>max_rows:
                raise InputError('row_limit',f'This file exceeds the configured {max_rows:,}-row limit.')
            if len(row)!=len(header):
                raise InputError('invalid_csv',f'CSV row {count+1} has {len(row)} fields; expected {len(header)}.')
    except csv.Error:
        raise InputError('invalid_csv','The CSV contains malformed quoting or records.') from None
    if count==0:
        raise InputError('empty_file','The file has a header but no sensor readings.')
    try:
        frame = pd.read_csv(io.StringIO(text),usecols=COLUMNS,dtype=str,keep_default_na=False)
        frame=frame.loc[:,COLUMNS]
    except (ValueError,pd.errors.ParserError,pd.errors.EmptyDataError):
        raise InputError('invalid_csv','The CSV records could not be parsed. Keep the original comma-separated format.') from None
    for name in COLUMNS[1:]:
        try:
            values=pd.to_numeric(frame[name],errors='raise')
        except (ValueError,TypeError):
            raise InputError('numeric_values',f'{name} contains blank or non-numeric values.') from None
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise InputError('non_finite',f'{name} contains missing or non-finite values.')
        frame[name]=values
    for name in COLUMNS[6:16]:
        if not frame[name].isin([0,1]).all():
            raise InputError('binary_values',f'{name} must contain recorded binary values 0 or 1.')
    frame['_seconds']=frame.Datetime.map(parse_timestamp)
    delta=np.diff(frame._seconds.to_numpy())
    if np.any(delta<=0):
        raise InputError('timestamp_order','Timestamps must strictly increase. Duplicate or out-of-order readings are not silently repaired.')
    starts=np.r_[0,np.flatnonzero(delta>1.0)+1]
    ends=np.r_[starts[1:],len(frame)]
    cycles=[]
    for index,(start,end) in enumerate(zip(starts,ends)):
        cycle=frame.iloc[start:end].reset_index(drop=True).copy(deep=True)
        try: validate_cycle(cycle)
        except InputError as error:
            raise InputError(error.code,f'Cycle {index+1}: {error.message}') from None
        cycles.append(cycle)
    return tuple(cycles)

def validate_cycle(c: pd.DataFrame) -> None:
    if len(c)<20:
        raise InputError('incomplete_cycle','Too few readings for a complete supported cycle (minimum 20).')
    dt=np.diff(c._seconds.to_numpy())
    if np.any(dt<=0) or np.any(dt>.100001) or not np.isclose(np.median(dt),.02,atol=1e-6):
        raise InputError('sampling_structure','Expected 20 ms recorded sampling with no internal gap over 100 ms. This recording structure is unsupported.')
    if not np.all(np.isclose(dt/.02,np.rint(dt/.02),atol=1e-4)):
        raise InputError('sampling_structure','Samples must lie on the recorded 20 ms time grid.')
    p=c[P].to_numpy(dtype=float)
    stroke=float(p[-1]-p[0])
    if abs(stroke)<=1:
        raise InputError('incomplete_cycle','No complete position movement was found. Flat or truncated position traces are unsupported.')
    opening=stroke>0
    if not (c['Door is opening']==int(opening)).all() or not (c['Door is closing']==int(not opening)).all():
        raise InputError('cycle_direction','Direction flags conflict with position travel or change inside one detected interval. A gapless or mixed-cycle stream is unsupported.')
    if opening:
        complete=bool(c.DCSR.iloc[0]==1 and c.DCSL.iloc[0]==1 and c['Door Opened'].iloc[-1]==1)
    else:
        complete=bool(c.DCSR.iloc[0]==0 and c.DCSL.iloc[0]==0 and c.DCSR.iloc[-1]==1 and c.DCSL.iloc[-1]==1)
    if not complete:
        raise InputError('incomplete_cycle','Recorded endpoint states do not describe a complete supported cycle. Check whether the recording was cut short.')
    if np.any(np.diff(p)*np.sign(stroke)<-.25*abs(stroke)):
        raise InputError('cycle_structure','Position resets inside the interval suggest multiple movements without a recording gap.')

def direction(c: pd.DataFrame) -> int:
    return int(c[P].iloc[-1]>=c[P].iloc[0])

def summaries(c: pd.DataFrame) -> np.ndarray:
    i,v,e,p,t=(c[I].to_numpy()/1000,c[V].to_numpy()*.01,c[E].to_numpy(),c[P].to_numpy(),c._seconds.to_numpy())
    a=np.abs(i)
    speed=np.diff(p)/np.diff(t)
    return np.array([a.mean(),np.quantile(a,.9),a.std(),np.abs(v).mean(),np.abs(e).mean(),
        t[-1]-t[0],abs(p[-1]-p[0]),p[0],p[-1],np.quantile(abs(speed),.9),np.mean(speed==0),np.trapezoid(abs(i*v),t)])

def progress(c: pd.DataFrame) -> np.ndarray:
    p=c[P].to_numpy(dtype=float)
    span=p[-1]-p[0]
    return np.clip((p-p[0])/span,0,1) if abs(span)>1 else np.linspace(0,1,len(c))

def profile(c: pd.DataFrame) -> np.ndarray:
    bins=np.minimum((progress(c)*10).astype(int),9)
    channels=[np.abs(c[I].to_numpy()/1000),np.abs(c[V].to_numpy()*.01),np.abs(c[E].to_numpy())]
    result=np.full((3,10),np.nan)
    for j,values in enumerate(channels):
        for column in range(10):
            if np.any(bins==column): result[j,column]=np.median(values[bins==column])
    return result

class FrozenModel:
    def __init__(self,metadata: dict,parameters: dict):
        self.metadata=metadata
        self.model_id=metadata['model_id']
        self._parameters={}
        for d,values in parameters.items():
            arrays={key:np.asarray(value,dtype=float) for key,value in values.items() if key!='normal_count'}
            shapes={'reference_median':(3,10),'reference_scale':(3,10),'reference_lower':(3,10),'reference_upper':(3,10),
                    'fill':(21,),'center':(21,),'scale':(21,),'coefficients':(22,)}
            for key,shape in shapes.items():
                if key not in arrays or arrays[key].shape!=shape or not np.isfinite(arrays[key]).all():
                    raise ValueError(f'Invalid bundled model array: {d}/{key}')
            if np.any(arrays['scale']<=0) or np.any(arrays['reference_scale']<=0):
                raise ValueError('Model scales must be positive')
            for array in arrays.values(): array.flags.writeable=False
            self._parameters[int(d)]={**arrays,'normal_count':int(values['normal_count'])}
        if set(self._parameters)!={0,1}: raise ValueError('Both model directions are required')

    @classmethod
    def load(cls,directory: Path) -> 'FrozenModel':
        directory=Path(directory)
        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        raw=(directory/'model.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest['artifacts']['model.json']:
            raise ValueError('Bundled model checksum mismatch')
        payload=json.loads(raw)
        if payload['metadata']['feature_names']!=FEATURE_NAMES or payload['metadata']['decision_threshold']!=.5:
            raise ValueError('Bundled feature schema or threshold does not match the runtime')
        if payload['metadata']['model_id']!=manifest['model_id']:
            raise ValueError('Bundled model identities disagree')
        return cls(payload['metadata'],payload['parameters'])

    def features(self,c: pd.DataFrame) -> np.ndarray:
        params=self._parameters[direction(c)]
        z=(profile(c)-params['reference_median'])/params['reference_scale']
        if np.any(np.sum(np.isfinite(z),axis=1)<8):
            raise InputError('profile_coverage','Too few relative-travel bins contain measurements for this model.')
        residual=np.concatenate([[np.nanmedian(a),np.nanquantile(a,.9),np.nanmean(np.maximum(a,0))] for a in z])
        return np.r_[summaries(c),residual]

    def predict(self,c: pd.DataFrame) -> dict:
        validate_cycle(c)
        d=direction(c)
        params=self._parameters[d]
        try:
            with np.errstate(over='raise',invalid='raise',divide='raise'):
                x=self.features(c)
                if not np.isfinite(x).all():
                    raise FloatingPointError('Derived feature is non-finite')
                x=np.where(np.isfinite(x),x,params['fill'])
                logit=float(np.r_[1.,(x-params['center'])/params['scale']]@params['coefficients'])
                if not np.isfinite(logit):
                    raise FloatingPointError('Derived score is non-finite')
        except (FloatingPointError,OverflowError):
            raise InputError('numerical_range','These recorded values exceed the numerical range of the feature calculation. Check the units and corrupted readings; no prediction was produced.') from None
        score=float(1/(1+np.exp(-np.clip(logit,-35,35))))
        return {'prediction':'Abnormal resistance' if score>=.5 else 'Normal','score':score,'direction':'Open' if d else 'Close'}

    def reference(self,c: pd.DataFrame) -> dict:
        params=self._parameters[direction(c)]
        return {'progress':((np.arange(10)+.5)/10).tolist(),
                'current_median_a':params['reference_median'][0].tolist(),
                'current_lower_a':params['reference_lower'][0].tolist(),
                'current_upper_a':params['reference_upper'][0].tolist(),
                'sample_count':params['normal_count'],
                'provenance':f'{self.model_id}: direction-matched training-normal cycles; descriptive 10th–90th percentile band, not a confidence interval.'}

def trace_payload(c: pd.DataFrame) -> dict:
    return {'time_ms':np.rint(c._seconds.to_numpy()*1000).astype(np.int64).tolist(),
            'timestamps':c.Datetime.tolist(),'current_a':(c[I].to_numpy()/1000).tolist(),
            'voltage_v':(c[V].to_numpy()*.01).tolist(),'back_emf':c[E].tolist(),
            'position':c[P].tolist(),'progress':progress(c).tolist()}

def apply_probe(c: pd.DataFrame,probe_id: str) -> pd.DataFrame:
    if probe_id not in {p['id'] for p in PROBES}:
        raise InputError('unknown_probe','Choose one of the five documented synthetic sensitivity checks.')
    changed=c.copy(deep=True)
    if probe_id.startswith('current_'):
        changed[I]=changed[I]*(.95 if 'minus' in probe_id else 1.05)
    elif probe_id.startswith('voltage_'):
        changed[V]=changed[V]*(.95 if 'minus' in probe_id else 1.05)
    else:
        keep=np.ones(len(changed),dtype=bool)
        keep[np.arange(20,len(changed)-1,20)]=False
        changed=changed.loc[keep].reset_index(drop=True)
    return changed
