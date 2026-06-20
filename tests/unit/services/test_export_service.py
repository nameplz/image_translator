from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from image_translator.domain.errors import ExportBlockedError
from image_translator.domain.export import (
    ApprovalStatus,
    ExportFormat,
    ExportRequest,
    FinalImageResult,
    ForceApprovalRecord,
    FormatOptions,
)
from image_translator.domain.quality import QualityIssue, QualitySeverity
from image_translator.services.export_service import export_image


def _write_input(path: Path) -> None:
    Image.new("RGB", (8, 6), color=(255, 255, 255)).save(path, format="PNG")


def _approved_result() -> FinalImageResult:
    return FinalImageResult(
        revision_id="revision-1",
        approval_status=ApprovalStatus.approved_automatic,
        visual_quality_checked=True,
    )


def _request(
    *,
    input_path: Path,
    output_path: Path,
    final_image_result: FinalImageResult | None = None,
    export_format: ExportFormat = ExportFormat.png,
    options: FormatOptions | None = None,
    overwrite_confirmed: bool = False,
    force_approval_record: ForceApprovalRecord | None = None,
) -> ExportRequest:
    return ExportRequest(
        input_path=str(input_path),
        output_path=str(output_path),
        final_image_result=final_image_result or _approved_result(),
        format=export_format,
        format_options=options or FormatOptions(),
        overwrite_confirmed=overwrite_confirmed,
        force_approval_record=force_approval_record,
    )


def _critical_issue() -> QualityIssue:
    return QualityIssue(
        issue_code="source_remnant",
        severity=QualitySeverity.critical,
        scope="render",
        summary="source text remains visible",
        resolved=False,
    )


def test_export_blocks_before_creating_requested_output_path(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "result.png"
    _write_input(input_path)
    blocked_result = FinalImageResult(
        revision_id="revision-1",
        approval_status=ApprovalStatus.needs_review,
        visual_quality_checked=True,
    )

    with pytest.raises(ExportBlockedError) as exc_info:
        export_image(
            image=Image.new("RGB", (8, 6), color=(1, 2, 3)),
            request=_request(
                input_path=input_path,
                output_path=output_path,
                final_image_result=blocked_result,
            ),
        )

    assert output_path.exists() is False
    assert "export gate blocked" in exc_info.value.diagnostic


def test_export_rejects_overwrite_without_confirmation(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "result.png"
    _write_input(input_path)
    output_path.write_bytes(b"existing")

    with pytest.raises(ExportBlockedError) as exc_info:
        export_image(
            image=Image.new("RGB", (8, 6), color=(1, 2, 3)),
            request=_request(input_path=input_path, output_path=output_path),
        )

    assert output_path.read_bytes() == b"existing"
    assert "overwrite confirmation" in exc_info.value.diagnostic


def test_export_rejects_input_path_collision(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    _write_input(input_path)

    with pytest.raises(ExportBlockedError) as exc_info:
        export_image(
            image=Image.new("RGB", (8, 6), color=(1, 2, 3)),
            request=_request(input_path=input_path, output_path=input_path),
        )

    assert "matches input path" in exc_info.value.diagnostic


def test_export_requires_force_record_for_blocking_issues(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "forced.webp"
    _write_input(input_path)
    blocked_result = FinalImageResult(
        revision_id="revision-1",
        approval_status=ApprovalStatus.approved_automatic,
        unresolved_issues=(_critical_issue(),),
        visual_quality_checked=True,
    )

    with pytest.raises(ExportBlockedError):
        export_image(
            image=Image.new("RGB", (8, 6), color=(1, 2, 3)),
            request=_request(
                input_path=input_path,
                output_path=output_path,
                final_image_result=blocked_result,
                export_format=ExportFormat.webp,
            ),
        )

    force_record = ForceApprovalRecord(
        affected_revision="revision-1",
        reason="user accepts visible source remnants for a draft export",
        created_at=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
        unresolved_issue_codes=("source_remnant",),
    )
    result = export_image(
        image=Image.new("RGB", (8, 6), color=(1, 2, 3)),
        request=_request(
            input_path=input_path,
            output_path=output_path,
            final_image_result=blocked_result,
            export_format=ExportFormat.webp,
            force_approval_record=force_record,
        ),
        exported_at=datetime(2026, 6, 20, 12, 30, tzinfo=UTC),
    )

    assert output_path.exists()
    assert result.audit_summary.forced_reason_recorded is True
    assert result.audit_summary.blocking_issue_codes == ("source_remnant",)


def test_export_strips_metadata_by_default(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "result.png"
    _write_input(input_path)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("prompt", "do not persist this")
    image_path = tmp_path / "with-metadata.png"
    Image.new("RGB", (8, 6), color=(1, 2, 3)).save(
        image_path,
        format="PNG",
        pnginfo=metadata,
    )

    with Image.open(image_path) as source_image:
        export_image(
            image=source_image,
            request=_request(input_path=input_path, output_path=output_path),
        )

    with Image.open(output_path) as exported_image:
        assert "prompt" not in exported_image.info


def test_export_cleans_up_temp_file_when_save_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "result.png"
    _write_input(input_path)

    def fail_save(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated save failure")

    monkeypatch.setattr(Image.Image, "save", fail_save)

    with pytest.raises(ExportBlockedError):
        export_image(
            image=Image.new("RGB", (8, 6), color=(1, 2, 3)),
            request=_request(input_path=input_path, output_path=output_path),
        )

    assert output_path.exists() is False
    assert tuple(tmp_path.glob(".result.png.*.tmp.png")) == ()


def test_export_rejects_format_extension_mismatch(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "result.jpg"
    _write_input(input_path)

    with pytest.raises(ExportBlockedError) as exc_info:
        export_image(
            image=Image.new("RGB", (8, 6), color=(1, 2, 3)),
            request=_request(input_path=input_path, output_path=output_path),
        )

    assert "extension=.jpg format=png" in exc_info.value.diagnostic


def test_jpeg_export_converts_alpha_image_and_uses_quality_option(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "result.jpeg"
    _write_input(input_path)

    result = export_image(
        image=Image.new("RGBA", (8, 6), color=(1, 2, 3, 128)),
        request=_request(
            input_path=input_path,
            output_path=output_path,
            export_format=ExportFormat.jpeg,
            options=FormatOptions(quality=80),
        ),
    )

    with Image.open(output_path) as exported_image:
        assert exported_image.format == "JPEG"
        assert exported_image.mode == "RGB"
    assert result.audit_summary.format_options == ("strip_metadata=true", "quality=80")
