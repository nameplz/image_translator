# Step 4: mock-workflow-use-case

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/WORKFLOWS.md`
- `/docs/QUALITY.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/EXPORT.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/0-core-vertical-slice/step3.md`
- `/src/image_translator/domain/`
- `/src/image_translator/providers/`
- `/src/image_translator/services/quality_policy.py`
- `/src/image_translator/services/export_gate.py`

## 작업

mock provider 기반의 첫 end-to-end core use case를 구현하라.

1. workflow skeleton을 구현하라.
   - 권장 파일: `/src/image_translator/workflows/translation_quality.py`
   - 권장 파일: `/src/image_translator/workflows/result_quality.py`
   - 이 step에서는 LangGraph node skeleton과 deterministic routing을 최소 구현한다.
   - graph state는 serializable domain DTO만 포함해야 한다.
   - node는 입력 state를 mutation하지 않고 patch/new state를 반환해야 한다.
2. application use case를 구현하라.
   - 권장 파일: `/src/image_translator/use_cases/run_image_translation.py`
   - `RunImageTranslationUseCase`는 `JobDefinition`을 검증하고 mock OCR -> mock translation/review -> export gate 결과까지 연결한다.
   - GUI thread 관련 코드는 작성하지 말고 domain `JobSnapshot` progress event만 반환하거나 yield하라.
   - provider request fingerprint를 사용해 후보와 review를 연결하라.
3. integration test를 추가하라.
   - 권장 파일: `/tests/integration/test_mock_core_workflow.py`
   - 성공 경로: 모든 region 승인, export eligible.
   - critical issue 경로: 해당 region만 needs_review/unresolved로 남고 일반 export 차단.
   - visual mode off 경로: 이미지/crop reference가 외부 provider request에 포함되지 않음.
4. 이 phase의 범위는 mock core vertical slice다. 실제 이미지 IO, 실제 rendering, GUI, SQLite checkpoint는 이후 phase로 남겨라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "mock provider 기반 core workflow use case 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- GUI thread 또는 PySide6 코드를 이 step에 추가하지 마라. Reason: core workflow는 GUI 런타임과 분리되어야 한다.
- 실제 provider API를 호출하지 마라. Reason: 기본 테스트는 외부 provider 없이 deterministic하게 통과해야 한다.
- checkpoint에 이미지 배열, API key, 전체 prompt, raw provider payload를 저장하지 마라. Reason: 보안과 개인정보 계약 위반이다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
