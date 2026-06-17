# Step 4: checkpoint-resume-runtime

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/WORKFLOWS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/RELEASE.md`
- `/docs/ADR.md`
- `/phases/2-workflow-provider-runtime/step3.md`
- `/src/image_translator/workflows/`
- `/src/image_translator/persistence/`
- `/src/image_translator/config/resources.py`

## 작업

SQLite checkpoint, resume, progress mapping, checkpoint redaction을 구현하라.

1. checkpoint store abstraction을 구현하라.
   - 권장 파일: `/src/image_translator/persistence/checkpoints.py`
   - OS app data 경로를 config/resource abstraction으로 찾는다.
   - TranslationQualityGraph, ResultQualityGraph, NaturalRevisionGraph는 별도 `thread_id`를 사용하고 `job_id`, revision ID로 연결하라.
   - checkpoint schema version을 저장하라.
2. resume orchestration을 구현하라.
   - 권장 파일: `/src/image_translator/use_cases/resume_job.py`
   - provider request fingerprint를 사용해 완료된 provider 호출을 불필요하게 반복하지 않게 하라.
   - `CancelledError`는 `WorkflowCancelled` 또는 `CANCELLED` 상태로 변환하라.
3. progress mapper를 구현하라.
   - 권장 파일: `/src/image_translator/observability/progress.py`
   - `docs/WORKFLOWS.md`의 단계 가중치를 사용하고 progress는 감소하지 않게 하라.
   - graph stream update를 `JobSnapshot`으로 변환하라.
4. redaction test를 추가하라.
   - 권장 파일: `/tests/unit/persistence/test_checkpoints.py`
   - 권장 파일: `/tests/unit/observability/test_progress.py`
   - 권장 파일: `/tests/integration/test_resume_mock_workflow.py`
   - checkpoint에 API key, 이미지 배열, provider raw payload, 전체 prompt가 없는지 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "checkpoint/resume runtime과 progress mapper 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- checkpoint에 API key, 이미지 배열, 전체 prompt, provider raw payload를 저장하지 마라. Reason: 보안과 개인정보 정책 위반이다.
- provider 호출 node의 부작용을 non-idempotent하게 만들지 마라. Reason: resume 시 node가 다시 실행될 수 있다.
- 취소를 실패 상태로 집계하지 마라. Reason: 사용자 취소는 `CANCELLED` 상태로 별도 처리해야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
