# Step 4: export-service

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/EXPORT.md`
- `/docs/QUALITY.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/1-image-layout-rendering/step3.md`
- `/src/image_translator/services/export_gate.py`
- `/src/image_translator/services/image_io.py`
- `/src/image_translator/services/rendering.py`

## 작업

품질 gate와 파일 안전 정책을 통과한 결과 이미지만 저장하는 export service를 구현하라.

1. export request/result 모델을 보강하라.
   - 권장 파일: `/src/image_translator/domain/export.py`
   - `ExportRequest`, `ExportFormat`, `FormatOptions`, `ForceApprovalRecord`, `ExportResult`를 정의하라.
2. export service를 구현하라.
   - 권장 파일: `/src/image_translator/services/export_service.py`
   - PNG를 기본 format으로 하고 JPEG/WebP options를 지원하라.
   - output path parent, extension, format 일치, overwrite confirmation, input path collision을 검증하라.
   - temporary file에 먼저 쓰고 성공 후 atomic replace를 사용하라.
   - 기본 metadata policy는 개인정보 가능 metadata 제거로 둔다.
3. export audit summary를 안전하게 기록할 수 있는 타입을 추가하라.
   - 전체 이미지 내용, secret, 전체 prompt, provider raw payload를 포함하지 마라.
4. 테스트를 추가하라.
   - 권장 파일: `/tests/unit/services/test_export_service.py`
   - 권장 파일: `/tests/integration/test_export_gate_and_save.py`
   - quality gate 전 파일 미생성, overwrite 확인, input path collision, forced export record required, temp cleanup을 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "safe export service와 format/path validation 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 품질 gate 통과 전에 requested output path에 파일을 만들지 마라. Reason: 실패 결과가 정상 output처럼 남으면 안 된다.
- 기존 파일을 직접 덮어쓰지 마라. Reason: 저장 실패 시 기존 결과를 손상시키지 않아야 한다.
- export audit에 이미지 내용이나 secret을 기록하지 마라. Reason: 보안 및 개인정보 정책 위반이다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
