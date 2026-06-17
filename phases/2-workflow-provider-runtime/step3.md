# Step 3: natural-revision-graph

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/WORKFLOWS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/PROMPT_CONTRACTS.md`
- `/docs/PROJECT_CONTEXT.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/UI_GUIDE.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/2-workflow-provider-runtime/step2.md`
- `/src/image_translator/workflows/`
- `/src/image_translator/persistence/`

## 작업

NaturalRevisionGraph와 append-only revision application contract를 구현하라.

1. revision domain 타입을 구현 또는 보강하라.
   - 권장 파일: `/src/image_translator/domain/revision.py`
   - 허용 `RevisionAction` 목록은 `docs/WORKFLOWS.md`와 정확히 일치해야 한다.
   - `RevisionTarget`, `RevisionPlan`, `RevisionRecord`, `ApprovalRecord`를 immutable하게 정의하라.
2. NaturalRevisionGraph를 구현하라.
   - 권장 파일: `/src/image_translator/workflows/natural_revision.py`
   - `parse_revision_intent`
   - `resolve_target_regions`
   - `determine_rule_scope`
   - `create_revision_plan`
   - `interrupt_for_plan_approval`
   - `apply_revision`
   - `revalidate_revision`
   - `commit_revision`
3. revision repository contract를 구현하라.
   - 권장 파일: `/src/image_translator/persistence/revision_repository.py`
   - 완료된 revision은 변경하지 않고 append-only로 저장하라.
   - Undo/Redo는 활성 revision pointer 변경 또는 revert revision 생성으로 표현하라.
4. 테스트를 추가하라.
   - 권장 파일: `/tests/unit/workflows/test_natural_revision_graph.py`
   - 권장 파일: `/tests/unit/persistence/test_revision_repository.py`
   - 허용 action만 생성, prompt injection 거절, 모호한 target interrupt, 승인 전 미적용, 프로젝트 규칙 별도 승인, Undo/Redo를 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "NaturalRevisionGraph와 append-only revision repository 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 승인된 `RevisionPlan` 없이 자연어 수정을 적용하지 마라. Reason: 자연어 입력은 신뢰할 수 없는 입력이며 승인 흐름이 필수다.
- 허용 목록 밖 `RevisionAction`을 생성하지 마라. Reason: 자연어 수정은 제한된 계획으로만 실행되어야 한다.
- 사용자 승인 없는 프로젝트 컨텍스트 변경을 영속화하지 마라. Reason: 잘못된 AI 추론이 이후 페이지에 전파되면 안 된다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
