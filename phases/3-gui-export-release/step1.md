# Step 1: worker-progress-cancel

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/UI_GUIDE.md`
- `/docs/WORKFLOWS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/TESTING.md`
- `/docs/ADR.md`
- `/phases/3-gui-export-release/step0.md`
- `/src/image_translator/gui/main_window.py`
- `/src/image_translator/use_cases/run_image_translation.py`
- `/src/image_translator/observability/progress.py`

## 작업

GUI worker, progress signal, cancellation flow를 구현하라.

1. worker thread를 구현하라.
   - 권장 파일: `/src/image_translator/gui/workers.py`
   - worker thread가 asyncio event loop와 graph task를 소유하게 하라.
   - progress update는 immutable `JobSnapshot` signal로 전달하라.
   - cancel은 `loop.call_soon_threadsafe(task.cancel)` 또는 동등한 thread-safe 방식으로 전달하라.
2. controller integration을 구현하라.
   - Run 클릭은 validated `JobDefinition`을 생성하고 worker를 시작한다.
   - Cancel 클릭은 취소 요청 상태를 표시하고 중복 취소를 방지한다.
   - `WorkflowCancelled` 또는 `cancelled` status는 실패가 아니라 취소로 표시한다.
3. progress UI test를 추가하라.
   - 권장 파일: `/tests/gui/test_worker_progress.py`
   - progress 비감소, stage/status update, cancel status, stale update 폐기를 검증하라.
4. GUI와 use case 사이에 테스트용 fake use case를 주입할 수 있게 하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
python3 scripts/run_gui_tests.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "GUI worker thread, progress signal, cancellation flow 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- GUI thread에서 장시간 작업을 실행하지 마라. Reason: OCR, graph, provider, rendering, save는 worker가 담당해야 한다.
- progress 값을 감소시키지 마라. Reason: workflow progress contract는 monotonic progress를 요구한다.
- 취소를 실패로 표시하지 마라. Reason: 사용자가 의도한 취소는 별도 상태로 처리해야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
