# Step 2: review-revision-ui

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/UI_GUIDE.md`
- `/docs/WORKFLOWS.md`
- `/docs/QUALITY.md`
- `/docs/PROJECT_CONTEXT.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/3-gui-export-release/step1.md`
- `/src/image_translator/gui/`
- `/src/image_translator/workflows/natural_revision.py`
- `/src/image_translator/persistence/revision_repository.py`

## 작업

Review Queue, Region Inspector, Natural Revision plan UI를 구현하라.

1. image comparison viewer overlay 기반을 구현하라.
   - 권장 파일: `/src/image_translator/gui/viewer.py`
   - OCR polygon, writing mode, reading order, text role, issue severity, selected region highlight를 표시하라.
   - 이 step에서는 기능 완성보다 domain state를 정확히 표시하는 deterministic widget state를 우선한다.
2. Region Inspector와 Review Queue를 구현하라.
   - 권장 파일: `/src/image_translator/gui/review_panel.py`
   - 주 OCR, 보조 OCR, 승인 OCR, 번역 후보, reviewer 점수, issue, RenderPlan 요약을 표시하라.
   - review queue는 자동 승인 실패 항목만 보여야 한다.
3. Natural Revision plan preview를 구현하라.
   - 권장 파일: `/src/image_translator/gui/revision_panel.py`
   - 자연어 입력 후 즉시 적용하지 말고 `RevisionPlan` preview를 표시하라.
   - 모호한 target은 후보 선택 상태로 표시하고 승인 action을 막아라.
   - 프로젝트 규칙 변경은 별도 확인 상태를 요구하라.
4. GUI test를 추가하라.
   - 권장 파일: `/tests/gui/test_review_revision_ui.py`
   - review queue filtering, selected region inspector update, plan preview, ambiguous target blocking, stale plan discard를 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
QT_QPA_PLATFORM=offscreen uv run pytest -m gui
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "review queue, region inspector, revision plan preview UI 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 자연어 수정 지시를 preview와 사용자 승인 없이 적용하지 마라. Reason: 자연어 수정은 승인된 `RevisionPlan`이 필요하다.
- 자동 승인 통과 항목을 review queue에 섞지 마라. Reason: review queue는 사용자가 봐야 할 실패/대기 항목에 집중해야 한다.
- 색상만으로 severity 의미를 전달하지 마라. Reason: UI guide는 텍스트/아이콘 병행 표시를 요구한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
