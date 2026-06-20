from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from image_translator.domain.export import (
    ApprovalStatus,
    ExportFormat,
    ExportMode,
    ExportRequest,
    FinalImageResult,
    FormatOptions,
)
from image_translator.domain.quality import QualityIssue, QualitySeverity
from image_translator.services.export_service import export_image


def test_confirmed_warning_result_can_be_saved_with_safe_audit_summary(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "result.png"
    Image.new("RGB", (12, 10), color=(255, 255, 255)).save(input_path, format="PNG")
    warning = QualityIssue(
        issue_code="low_contrast_warning",
        severity=QualitySeverity.warning,
        scope="render",
        region_ids=("region-1",),
        summary="contrast is close to the minimum",
        evidence_references=("deterministic-render-check",),
        resolved=False,
    )
    final_result = FinalImageResult(
        revision_id="revision-1",
        approval_status=ApprovalStatus.approved_user,
        unresolved_issues=(warning,),
        visual_quality_checked=True,
    )

    result = export_image(
        image=Image.new("RGB", (12, 10), color=(1, 2, 3)),
        request=ExportRequest(
            input_path=str(input_path),
            output_path=str(output_path),
            job_id="job-1",
            final_image_result=final_result,
            format=ExportFormat.png,
            format_options=FormatOptions(),
            confirmed_warning_issue_codes=("low_contrast_warning",),
        ),
        exported_at=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
    )

    assert output_path.exists()
    assert result.eligibility_decision.allowed is True
    assert result.eligibility_decision.mode is ExportMode.normal
    assert result.audit_summary.job_id == "job-1"
    assert result.audit_summary.revision_id == "revision-1"
    assert result.audit_summary.warning_issue_codes == ()
    assert result.audit_summary.format_options == ("strip_metadata=true",)
    audit_payload = result.audit_summary.model_dump(mode="json")
    assert "image" not in audit_payload
    assert "prompt" not in audit_payload
    assert "provider_raw_payload" not in audit_payload
