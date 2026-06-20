from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from image_translator.domain.errors import ExportBlockedError
from image_translator.domain.export import (
    ExportAuditSummary,
    ExportFormat,
    ExportRequest,
    ExportResult,
    FormatOptions,
)
from image_translator.services.export_gate import evaluate_export_eligibility

_EXTENSION_FORMATS = {
    ".png": ExportFormat.png,
    ".jpg": ExportFormat.jpeg,
    ".jpeg": ExportFormat.jpeg,
    ".webp": ExportFormat.webp,
}
_PIL_FORMATS = {
    ExportFormat.png: "PNG",
    ExportFormat.jpeg: "JPEG",
    ExportFormat.webp: "WEBP",
}


def export_image(
    *,
    image: Image.Image,
    request: ExportRequest,
    exported_at: datetime | None = None,
) -> ExportResult:
    decision = evaluate_export_eligibility(
        request.final_image_result,
        confirmed_warning_issue_codes=request.confirmed_warning_issue_codes,
        confirmed_user_confirmation_reasons=request.confirmed_user_confirmation_reasons,
        force_approval_record=request.force_approval_record,
    )
    if not decision.allowed:
        raise _export_error(
            "Resolve blocking export issues or use forced export with a reason.",
            f"export gate blocked: reason_codes={decision.reason_codes}",
        )

    output_path = _validate_export_path(request)
    temp_path: Path | None = None
    try:
        temp_path = _write_temp_image(
            image=image,
            output_path=output_path,
            export_format=request.format,
            options=request.format_options,
        )
        os.replace(temp_path, output_path)
        temp_path = None
    except OSError as exc:
        raise _export_error(
            "The image could not be saved. Check the output folder and try Save As.",
            f"export write failed: {exc.__class__.__name__}",
        ) from exc
    finally:
        if temp_path is not None:
            _unlink_if_exists(temp_path)

    file_size = output_path.stat().st_size
    audit_summary = ExportAuditSummary(
        job_id=request.job_id,
        revision_id=request.final_image_result.revision_id,
        output_path=str(output_path),
        format=request.format,
        format_options=_format_options_summary(request.format_options),
        exported_at=exported_at or datetime.now(UTC),
        mode=decision.mode,
        blocking_issue_codes=decision.blocking_issue_codes,
        warning_issue_codes=decision.warning_issue_codes,
        requires_user_confirmation=decision.requires_user_confirmation,
        forced_reason_recorded=request.force_approval_record is not None,
    )
    return ExportResult(
        output_path=str(output_path),
        format=request.format,
        file_size_bytes=file_size,
        audit_summary=audit_summary,
        eligibility_decision=decision,
    )


def _validate_export_path(request: ExportRequest) -> Path:
    input_path = _resolve_existing_input(request.input_path)
    output_path = Path(request.output_path).expanduser()
    output_format = _format_from_extension(output_path)
    if output_format is not request.format:
        raise _export_error(
            "Choose an output extension that matches the selected export format.",
            f"extension={output_path.suffix.lower()} format={request.format.value}",
        )

    parent = output_path.parent if output_path.parent != Path("") else Path.cwd()
    if not parent.exists() or not parent.is_dir():
        raise _export_error(
            "Choose an output folder that exists.",
            f"output parent does not exist or is not a directory: {parent}",
        )
    if not os.access(parent, os.W_OK):
        raise _export_error(
            "Choose an output folder that can be written.",
            f"output parent is not writable: {parent}",
        )

    resolved_output = output_path.resolve(strict=False)
    if resolved_output == input_path:
        raise _export_error(
            "Choose an output path that does not overwrite the input image.",
            f"output path matches input path: {resolved_output}",
        )
    if resolved_output.exists() and not request.overwrite_confirmed:
        raise _export_error(
            "Confirm overwrite before replacing the existing output file.",
            f"output file exists without overwrite confirmation: {resolved_output}",
        )
    return resolved_output


def _resolve_existing_input(input_path: str) -> Path:
    try:
        resolved_input = Path(input_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise _export_error(
            "The input image path is no longer available.",
            f"input path resolution failed: {exc.__class__.__name__}",
        ) from exc
    if not resolved_input.is_file():
        raise _export_error(
            "Choose a regular input image file.",
            f"input path is not a file: {resolved_input}",
        )
    return resolved_input


def _format_from_extension(path: Path) -> ExportFormat:
    export_format = _EXTENSION_FORMATS.get(path.suffix.lower())
    if export_format is None:
        raise _export_error(
            "Choose a PNG, JPEG, or WebP output file.",
            f"unsupported export extension: {path.suffix}",
        )
    return export_format


def _write_temp_image(
    *,
    image: Image.Image,
    output_path: Path,
    export_format: ExportFormat,
    options: FormatOptions,
) -> Path:
    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=f".tmp{output_path.suffix.lower()}",
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    try:
        save_image = _prepare_image(image, export_format, strip_metadata=options.strip_metadata)
        save_kwargs = _save_kwargs(export_format, options)
        save_image.save(temp_path, format=_PIL_FORMATS[export_format], **save_kwargs)
        return temp_path
    except OSError:
        _unlink_if_exists(temp_path)
        raise


def _prepare_image(
    image: Image.Image,
    export_format: ExportFormat,
    *,
    strip_metadata: bool,
) -> Image.Image:
    working_image = image
    if strip_metadata:
        working_image = Image.new(image.mode, image.size)
        working_image.paste(image)
    else:
        working_image = image.copy()

    if export_format is ExportFormat.jpeg and working_image.mode not in {"RGB", "L"}:
        return working_image.convert("RGB")
    return working_image


def _save_kwargs(export_format: ExportFormat, options: FormatOptions) -> dict[str, Any]:
    if export_format is ExportFormat.png:
        return {}
    if export_format is ExportFormat.jpeg:
        return {"quality": options.quality or 95}
    if options.lossless:
        return {"lossless": True}
    return {"quality": options.quality or 95}


def _format_options_summary(options: FormatOptions) -> tuple[str, ...]:
    values = [f"strip_metadata={str(options.strip_metadata).lower()}"]
    if options.quality is not None:
        values.append(f"quality={options.quality}")
    if options.lossless:
        values.append("lossless=true")
    return tuple(values)


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _export_error(user_message: str, diagnostic: str) -> ExportBlockedError:
    return ExportBlockedError(user_message=user_message, diagnostic=diagnostic)


__all__ = ["export_image"]
