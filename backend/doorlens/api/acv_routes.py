from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from doorlens import acv
from doorlens.services.store import AnalysisMissing

router = APIRouter(prefix="/api")


def _err(status: int, code: str, message: str):
    return HTTPException(status, detail={"code": code, "message": message})


@router.post("/acv/analyze")
async def acv_analyze(request: Request, file: UploadFile = File(...)):
    settings = request.app.state.settings
    limit = settings.max_acv_upload_bytes
    content = bytearray()
    try:
        while True:
            chunk = await file.read(min(64 * 1024, limit - len(content) + 1))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > limit:
                raise _err(413, "upload_too_large", f"The file exceeds the {limit:,}-byte upload limit.")
        name = (file.filename or "acv_case.xlsx").replace("\\", "/").rsplit("/", 1)[-1]
        result = await run_in_threadpool(acv.analyse, bytes(content), name, request.app.state.acv_store, settings.max_rows)
    finally:
        await file.close()
    import json
    return Response(json.dumps(result), media_type="application/json")


@router.get("/acv/{identifier}/predictions.csv")
def acv_csv(identifier: str, request: Request):
    data = request.app.state.acv_store.get(identifier)
    if data is None:
        raise _err(404, "analysis_not_found", "This ACV analysis does not exist or has expired. Upload the file again.")
    return Response(data, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="acv_predictions.csv"'})


@router.get("/submission.zip")
def submission_zip(request: Request, door: str | None = None, acv_id: str | None = None):
    """predictions.zip with door_predictions.csv and/or acv_predictions.csv at the root."""
    files: dict[str, bytes] = {}
    if door:
        try:
            files["door_predictions.csv"] = request.app.state.analysis_store.get(door).csv_bytes
        except AnalysisMissing:
            raise _err(404, "analysis_not_found", "The door analysis does not exist or has expired.") from None
    if acv_id:
        data = request.app.state.acv_store.get(acv_id)
        if data is None:
            raise _err(404, "analysis_not_found", "The ACV analysis does not exist or has expired.")
        files["acv_predictions.csv"] = data
    if not files:
        raise _err(422, "nothing_to_export", "Run at least one subsystem before exporting.")
    return Response(acv.zip_of(files), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="predictions.zip"'})
