from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from prompt_piper_api.config import get_settings
from prompt_piper_api.llm.factory import create_llm_client_from_env
from prompt_piper_api.schemas.inference import SendToInferenceRequest, SendToInferenceResponse
from prompt_piper_api.schemas.precision import (
    ApplyPrecisionReplacementRequest,
    PrecisionReviewResponse,
    PrecisionSuggestRequest,
    PrecisionSuggestResponse,
)
from prompt_piper_api.schemas.session import (
    AnswerClarificationRequest,
    AskTheLocalsResponse,
    ClarificationSuggestionsResponse,
    CreateSessionFromTemplateRequest,
    CreateSessionRequest,
    EditDraftRequest,
    FinalizeSessionRequest,
    GenerateArtifactsRequest,
    SessionDetailResponse,
    to_session_detail,
    to_session_response,
)
from prompt_piper_api.services.artifact_factory import create_artifact_export_service
from prompt_piper_api.services.audit_log_service import AuditLogService
from prompt_piper_api.services.external_inference_service import ExternalInferenceService
from prompt_piper_api.services.git_registry_service import GitRegistryService
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.session_service import SessionService
from prompt_piper_api.services.session_store import create_session_store
from prompt_piper_api.services.similarity_factory import create_similarity_check_service

router = APIRouter(prefix="/sessions", tags=["sessions"])

_session_service: SessionService | None = None


def get_session_service() -> SessionService:
    global _session_service
    if _session_service is None:
        settings = get_settings()
        audit = AuditLogService(settings.audit_log_path)
        artifact_export = create_artifact_export_service(settings)
        _session_service = SessionService(
            llm=create_llm_client_from_env(),
            registry=GitRegistryService(settings.registry_path),
            similarity=create_similarity_check_service(settings),
            optimizer=TokenOptimizationEngine(),
            artifact_export=artifact_export,
            external_inference=ExternalInferenceService(
                settings,
                audit,
                settings.artifacts_path,
            ),
            audit=audit,
            store=create_session_store(settings.sessions_path),
        )
    return _session_service


@router.post("", response_model=SessionDetailResponse, status_code=201)
def create_session(
    payload: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.create_session(
        initial_request=payload.initial_request,
        title=payload.title,
    )
    return to_session_response(result)


@router.post("/{session_id}/template", response_model=SessionDetailResponse, status_code=201)
def create_session_from_template(
    session_id: UUID,
    payload: CreateSessionFromTemplateRequest | None = None,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.create_session_from_template(
        session_id,
        title=None if payload is None else payload.title,
    )
    return to_session_response(result)


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    record = service.get_session(session_id)
    return to_session_detail(record)


@router.post("/{session_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_session_post(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> Response:
    service.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> Response:
    service.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/clarify/suggest", response_model=ClarificationSuggestionsResponse)
def suggest_clarification(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> ClarificationSuggestionsResponse:
    result = service.suggest_clarification(session_id)
    return ClarificationSuggestionsResponse.model_validate(result.model_dump())


@router.post("/{session_id}/clarify/locals", response_model=AskTheLocalsResponse)
def ask_the_locals(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> AskTheLocalsResponse:
    result = service.ask_the_locals(session_id)
    return AskTheLocalsResponse.model_validate(result.model_dump())


@router.post("/{session_id}/answer", response_model=SessionDetailResponse)
def answer_clarification(
    session_id: UUID,
    payload: AnswerClarificationRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.answer_clarification(session_id, payload.answer)
    return to_session_response(result)


@router.post("/{session_id}/clarify/complete", response_model=SessionDetailResponse)
def complete_clarification(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.complete_clarification(session_id)
    return to_session_response(result)


@router.post("/{session_id}/edit", response_model=SessionDetailResponse)
def edit_session_draft(
    session_id: UUID,
    payload: EditDraftRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.edit_draft(
        session_id, payload.instruction, body=payload.body
    )
    return to_session_response(result)


@router.post("/{session_id}/workflow/reopen/edit", response_model=SessionDetailResponse)
def reopen_session_for_edit(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.reopen_for_edit(session_id)
    return to_session_response(result)


@router.post("/{session_id}/workflow/rerun/similarity", response_model=SessionDetailResponse)
def rerun_session_similarity_check(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.rerun_similarity_check(session_id)
    return to_session_response(result)


@router.post("/{session_id}/workflow/rerun/optimize", response_model=SessionDetailResponse)
def rerun_session_optimization(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.rerun_optimization(session_id)
    return to_session_response(result)


@router.post("/{session_id}/finalize", response_model=SessionDetailResponse)
def finalize_session(
    session_id: UUID,
    payload: FinalizeSessionRequest | None = None,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    body = payload or FinalizeSessionRequest()
    result = service.finalize(
        session_id,
        acknowledge_first_shot_risk=body.acknowledge_first_shot_risk,
    )
    return to_session_response(result)


@router.post("/{session_id}/optimize", response_model=SessionDetailResponse)
def optimize_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.optimize(session_id)
    return to_session_response(result)


@router.post("/{session_id}/optimize/approve", response_model=SessionDetailResponse)
def approve_optimization(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.approve_optimization(session_id)
    return to_session_response(result)


@router.get("/{session_id}/precision", response_model=PrecisionReviewResponse)
def get_precision_review(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> PrecisionReviewResponse:
    return service.get_precision_review(session_id)


@router.post("/{session_id}/precision/suggest", response_model=PrecisionSuggestResponse)
def suggest_precision_replacement(
    session_id: UUID,
    payload: PrecisionSuggestRequest,
    service: SessionService = Depends(get_session_service),
) -> PrecisionSuggestResponse:
    result = service.suggest_precision_replacement(session_id, finding_id=payload.finding_id)
    return PrecisionSuggestResponse.from_service(result)


@router.post("/{session_id}/precision/apply", response_model=SessionDetailResponse)
def apply_precision_replacement(
    session_id: UUID,
    payload: ApplyPrecisionReplacementRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.apply_precision_replacement(
        session_id,
        finding_id=payload.finding_id,
        replacement=payload.replacement,
    )
    return to_session_response(result)


@router.post("/{session_id}/artifacts", response_model=SessionDetailResponse)
def generate_session_artifacts(
    session_id: UUID,
    payload: GenerateArtifactsRequest | None = None,
    service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    result = service.generate_artifacts(
        session_id,
        include_pdf=True if payload is None else payload.include_pdf,
        export_folder_label=None if payload is None else payload.export_folder_label,
    )
    return to_session_response(result)


@router.post("/{session_id}/send-to-inference", response_model=SendToInferenceResponse)
def send_session_to_inference(
    session_id: UUID,
    payload: SendToInferenceRequest,
    service: SessionService = Depends(get_session_service),
) -> SendToInferenceResponse:
    result = service.send_to_inference(
        session_id,
        explicit_approval=payload.explicit_approval,
        api_endpoint_id=payload.api_endpoint_id,
    )
    return SendToInferenceResponse(
        provider=result.provider,
        model=result.model,
        prompt_id=result.prompt_id,
        version=result.version,
        timestamp=result.timestamp,
        artifact_location=result.artifact_location,
        inference_response_artifact_path=result.inference_response_artifact_path,
        response_text=result.response_text,
    )
