# DoorLens API contract

All API errors return JSON {detail:{code,message}} with suitable HTTP status. GET /api/health returns {status,model_id,demo_model_id}; GET /api/methodology returns bundled evidence/provenance JSON.

POST /api/analyze multipart file => Analysis; POST /api/demo => Analysis using frozen development fold-zero model and train_seg_017. DELETE /api/analyses/{id} clears a run.

Analysis: {id,filename,context:'upload'|'development-demo',model_id,model_label,created_at,expires_at,input_sha256,csv_sha256,elapsed_ms,summary:{cycle_count,normal_count,abnormal_count},warnings:string[],cycles:Cycle[],overview:Trace,probe_definitions:Probe[]}

Cycle: {index,cycle_id,start_time,end_time,prediction:'Normal'|'Abnormal resistance',score,direction:'Open'|'Close',sample_count,duration_s}.

Trace: {time_ms:(number|null)[],timestamps:(string|null)[],current_a:(number|null)[],voltage_v:(number|null)[],back_emf:(number|null)[],position:(number|null)[],progress:(number|null)[]}. Full-resolution selected cycle; overview may be boundary-aware downsampled for display only, with explicit null breaks.

GET /api/analyses/{id}/cycles/{index} => {analysis_id,index,context,model_id,cycle:Cycle,trace:Trace,reference:{progress:number[],current_median_a:number[],current_lower_a:number[],current_upper_a:number[],sample_count,provenance}}.

Probe: {id,label,description}. IDs: current_minus_5pct,current_plus_5pct,voltage_minus_5pct,voltage_plus_5pct,drop_each_20th_interior.

POST /api/analyses/{id}/cycles/{index}/challenge JSON {probe_id} => {analysis_id,index,model_id,probe_id,probe_label,description,original:{prediction,score},altered:{prediction,score},label_changed,trace:Trace,sample_count,original_csv_sha256,synthetic:true,caveat}.

GET /api/analyses/{id}/predictions.csv => original bytes download filename door_predictions.csv; GET .../predictions.zip => archive containing only door_predictions.csv at root, download filename predictions.zip. Never regenerate inference at download. Challenge never mutates original analysis or export bytes. IDs expire with 410 and unknown IDs return404.

Frontend uses relative /api URLs in production; optional NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 for development. API namespace misses always return JSON404, never HTML.
