# Step 1: domain-core-models

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/QUALITY.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/WORKFLOWS.md`
- `/docs/OCR_LAYOUT.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/0-core-vertical-slice/step0.md`
- `/src/image_translator/domain/`
- `/tests/unit/test_architecture_boundaries.py`

## 작업

문서화된 domain model의 첫 구현 단위를 immutable Pydantic 2 모델로 추가하라.

1. 아래 stable boundary 타입을 구현하라.
   - ID value object 또는 constrained alias: `ProjectId`, `JobId`, `PageId`, `RegionId`, `RevisionId`, `WorkflowThreadId`, `ProviderRequestId`
   - geometry: `Point`, `Polygon`, `RotatedBoundingBox`
   - layout enum: `WritingMode`, `TextOrientation`, `TextRole`
   - reading order: `ReadingOrderCandidate`, `ReadingOrder`
   - OCR: `RawOCRRegion`, `OCRCandidate`, `NormalizedTextRegion`
   - quality: `QualitySeverity`, `QualityIssue`, `RubricScores`, `RegionReview`
   - translation: `TranslationRequest`, `TranslationCandidate`, `TranslationResult`
   - job/progress: `JobStatus`, `JobDefinition`, `JobSnapshot`
2. 권장 파일 구조는 다음과 같다.
   - `/src/image_translator/domain/ids.py`
   - `/src/image_translator/domain/geometry.py`
   - `/src/image_translator/domain/ocr.py`
   - `/src/image_translator/domain/translation.py`
   - `/src/image_translator/domain/quality.py`
   - `/src/image_translator/domain/job.py`
   - `/src/image_translator/domain/errors.py`
3. 모든 모델은 기본적으로 frozen/immutable이어야 하며 tuple 기반 collection을 사용하라.
4. validation invariant를 테스트하라.
   - polygon은 최소 3개 point와 양수 면적을 요구한다.
   - normalization 이후 `NormalizedTextRegion.geometry`는 non-null이어야 한다.
   - rubric 점수는 1.0 이상 5.0 이하이어야 한다.
   - `JobSnapshot.progress`는 0.0 이상 1.0 이하이어야 한다.
5. 권장 테스트 파일:
   - `/tests/unit/domain/test_geometry.py`
   - `/tests/unit/domain/test_ocr_models.py`
   - `/tests/unit/domain/test_quality_models.py`
   - `/tests/unit/domain/test_job_models.py`

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "immutable domain core models와 invariant tests 추가"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- provider SDK 타입이나 GUI 타입을 domain model에 넣지 마라. Reason: domain은 외부 SDK와 UI 런타임에서 독립적이어야 한다.
- 원본 OCR snapshot과 승인 결과를 mutation 가능한 구조로 만들지 마라. Reason: 판단 근거와 revision 추적성을 보존해야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
