import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from doorlens.inference import PROBES
from doorlens.services.analysis import AnalysisService
from doorlens.services.store import AnalysisMissing


router = APIRouter(prefix="/api")


def error(status: int, code: str, message: str):
    return HTTPException(status, detail={"code": code, "message": message})


def get_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


def find_analysis(service: AnalysisService, identifier: str):
    try:
        return service.store.get(identifier)
    except AnalysisMissing as exc:
        if exc.expired:
            raise error(410, "analysis_expired", "This analysis expired or was cleared to release memory. Upload the recording again.") from None
        raise error(404, "analysis_not_found", "This analysis does not exist in the current application session.") from None


def find_cycle(service: AnalysisService, identifier: str, index: int):
    analysis = find_analysis(service, identifier)
    if index < 0 or index >= len(analysis.cycles):
        raise error(404, "cycle_not_found", "This cycle does not exist in the selected analysis.")
    return analysis


@router.get("/health")
def health(service: AnalysisService = Depends(get_service)):
    return {"status": "ok", "model_id": service.model("upload").model_id,
            "demo_model_id": service.model("development-demo").model_id}


@router.get("/methodology")
def methodology(service: AnalysisService = Depends(get_service)):
    path = Path(service.settings.model_directory) / "evidence.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/analyze")
async def analyze(file: UploadFile = File(...), service: AnalysisService = Depends(get_service)):
    content = bytearray()
    try:
        # Count actual file bytes; UploadFile's spooling is not an upload cap.
        while True:
            chunk = await file.read(min(64 * 1024, service.settings.max_upload_bytes - len(content) + 1))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > service.settings.max_upload_bytes:
                raise error(413, "upload_too_large", f"The recording exceeds the {service.settings.max_upload_bytes:,}-byte upload limit.")
        filename = (file.filename or "recording.csv").replace("\\", "/").rsplit("/", 1)[-1]
        analysis = await run_in_threadpool(service.analyze, bytes(content), filename)
        return Response(analysis.response_json, media_type="application/json")
    finally:
        await file.close()


@router.post("/demo")
def demo(service: AnalysisService = Depends(get_service)):
    analysis = service.demo()
    return Response(analysis.response_json, media_type="application/json")


@router.delete("/analyses/{identifier}", status_code=204)
def delete_analysis(identifier: str, service: AnalysisService = Depends(get_service)):
    find_analysis(service, identifier)
    try:
        service.store.delete(identifier)
    except AnalysisMissing:
        raise error(410, "analysis_expired", "This analysis expired. Upload the recording again.") from None
    return Response(status_code=204)


@router.get("/analyses/{identifier}/cycles/{index}")
def cycle(identifier: str, index: int, service: AnalysisService = Depends(get_service)):
    analysis = find_cycle(service, identifier, index)
    return service.cycle_result(analysis, index)


class ChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    probe_id: str = Field(min_length=1, max_length=80)


@router.post("/analyses/{identifier}/cycles/{index}/challenge")
def challenge(identifier: str, index: int, body: ChallengeRequest, service: AnalysisService = Depends(get_service)):
    analysis = find_cycle(service, identifier, index)
    if body.probe_id not in {probe["id"] for probe in PROBES}:
        raise error(422, "unsupported_probe", "Choose one of the five listed synthetic sensitivity checks.")
    return service.challenge(analysis, index, body.probe_id)


@router.get("/analyses/{identifier}/predictions.csv")
def csv_download(identifier: str, service: AnalysisService = Depends(get_service)):
    analysis = find_analysis(service, identifier)
    return Response(analysis.csv_bytes, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="door_predictions.csv"'})


@router.get("/analyses/{identifier}/predictions.zip")
def zip_download(identifier: str, service: AnalysisService = Depends(get_service)):
    analysis = find_analysis(service, identifier)
    return Response(analysis.zip_bytes, media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="predictions.zip"'})
