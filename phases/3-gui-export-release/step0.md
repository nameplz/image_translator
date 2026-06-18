# Step 0: gui-foundation

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/UI_GUIDE.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/WORKFLOWS.md`
- `/docs/TESTING.md`
- `/docs/ADR.md`
- `/phases/2-workflow-provider-runtime/index.json`
- `/src/image_translator/gui/`
- `/src/image_translator/use_cases/`
- `/pyproject.toml`

## 작업

PySide6 기반 Main Window skeleton과 GUI test 기반을 구현하라.

1. `pyproject.toml`에 GUI dependency를 추가하라.
   - `PySide6`
   - dev dependency에 `pytest-qt`
   - runtime dependency는 `uv add PySide6`로 추가하라.
   - dev dependency는 `uv add --dev pytest-qt`로 추가하라.
   - dependency 도입과 같은 변경에서 `uv.lock`, `AGENTS.md`의 현재 상태, `tests/unit/test_bootstrap_contract.py`, 관련 문서를 함께 갱신하라.
2. GUI application entrypoint와 main window를 구현하라.
   - 권장 파일: `/src/image_translator/app/main.py`
   - 권장 파일: `/src/image_translator/gui/main_window.py`
   - 권장 파일: `/src/image_translator/gui/controllers.py`
   - Toolbar: Open, Run, Cancel, Output Path, Save As, Settings.
   - Center viewer: Original, OCR Overlay, Inpainted, Result 탭 또는 mode selector.
   - Right panel: Region Inspector, Review Queue, Revision Plan placeholder.
   - Bottom bar: stage, progress, status message.
3. GUI는 domain DTO와 use case interface에만 의존하게 하라.
4. pytest-qt test를 추가하라.
   - 권장 파일: `/tests/gui/test_main_window.py`
   - Run button enable/disable, output path placeholder, progress/status display, save disabled initial state를 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
python3 scripts/run_gui_tests.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "PySide6 main window skeleton과 GUI test 기반 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- GUI에서 provider adapter나 graph node를 직접 호출하지 마라. Reason: GUI는 use case boundary를 통해서만 application logic에 접근해야 한다.
- GUI thread에서 OCR, graph, provider 호출, 인페인팅, 렌더링, 저장을 실행하지 마라. Reason: 데스크톱 UI 응답성을 보존해야 한다.
- UI에 raw provider error나 secret을 표시하지 마라. Reason: 사용자 메시지와 개발자 로그는 분리되어야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
