# Step 1: ocr-normalization

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/OCR_LAYOUT.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/QUALITY.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/1-image-layout-rendering/step0.md`
- `/src/image_translator/domain/ocr.py`
- `/src/image_translator/domain/geometry.py`
- `/src/image_translator/services/image_io.py`

## 작업

OCR raw output을 normalized text region으로 변환하는 deterministic service를 구현하라.

1. normalization service를 구현하라.
   - 권장 파일: `/src/image_translator/services/ocr_normalization.py`
   - `RawOCRRegion`은 후속 service에 직접 전달하지 않고 `NormalizedTextRegion`으로 변환하라.
   - polygon 또는 rotated bbox 중 하나 이상을 geometry로 보존하라.
   - normalization 이후 geometry는 반드시 non-null이어야 한다.
   - region ID는 page 내에서 고유해야 한다.
   - image boundary와 교차하지 않는 geometry는 invalid로 처리하라.
2. OCR risk score 계산 기반을 추가하라.
   - 권장 파일: `/src/image_translator/services/ocr_risk.py`
   - confidence, writing mode confidence, abnormal character, reading order ambiguity, ruby ambiguity 신호를 표현하라.
   - 정확한 가중치는 설정 가능한 policy 객체로 분리하라.
3. 테스트를 먼저 추가하라.
   - 권장 파일: `/tests/unit/services/test_ocr_normalization.py`
   - 권장 파일: `/tests/unit/services/test_ocr_risk.py`
   - duplicate region ID, invalid polygon, missing geometry, boundary miss, low-confidence risk를 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "OCR normalization과 risk scoring service 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 축 정렬 bbox만 저장해 회전 또는 세로 텍스트 정보를 잃지 마라. Reason: OCR layout 계약은 polygon 또는 rotated bbox 정보를 보존해야 한다.
- 잘못된 geometry를 AI 판단으로 우회하지 마라. Reason: Q0 입력 무결성 실패는 결정론적으로 중단되어야 한다.
- 원본 OCR snapshot을 수정하지 마라. Reason: 원본 provider 결과는 판단 근거로 보존해야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
