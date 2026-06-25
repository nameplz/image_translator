# 프로젝트: Image Translator

## 현재 상태

이 저장소는 Image Translator의 Python 0.1.0 부트스트랩 상태다.

- 실제 package 이름은 `image_translator`다.
- 현재 source tree는 core/workflow layer와 최소 GUI foundation 골격을 포함한다.
- 현재 `pyproject.toml`의 runtime dependency는 `pydantic>=2`, `langgraph`,
  `pillow`, `numpy`, `opencv-python-headless`, `PySide6`다.
- 현재 dev dependency는 `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`,
  `pytest-qt`다.
- `uv.lock`과 `.harness/validation.json`이 validation 기준이다.
- `phases/`는 0-2단계가 완료되었고 3단계 GUI/export release 구현을 진행 중이다.

아래 MVP 기술과 제품 계약은 구현 목표다. PySide6, NumPy, Pillow, OpenCV,
SQLite checkpointer, pytest-qt 같은 계획된 dependency를 사용하는 변경은 같은 변경에서
`pyproject.toml`, `uv.lock`, 테스트, 관련 문서를 함께 갱신해야 한다.

## 프로젝트 목표

만화와 웹툰 이미지의 한국어, 영어, 일본어 텍스트를 정확한 reading order로 인식하고,
의미, 말투, 작품 맥락을 보존해 번역한 뒤 품질 검증을 통과한 결과 이미지를 생성한다.

처리 속도보다 번역과 최종 이미지의 품질, 판단 근거의 추적성, 사용자 검토 가능성을 우선한다.

## MVP 기술 목표

문서 계약상 최종 MVP는 다음 스택을 목표로 한다.

- Python 3.11+
- PySide6 데스크톱 GUI
- LangGraph workflow orchestration
- Pydantic 2 typed domain model
- NumPy, Pillow, OpenCV
- SQLite checkpointer
- uv package manager
- pytest, pytest-asyncio, pytest-qt, pytest-cov
- ruff, mypy

현재 구현에서 사용할 수 있는 dependency는 `pyproject.toml`을 기준으로 판단한다. 문서에만 있는
dependency를 코드에서 먼저 import하지 않는다.

## Source Of Truth

문서가 충돌하면 다음 우선순위를 따른다.

1. `docs/QUALITY.md`: 품질 gate와 승인 기준
2. `docs/DOMAIN_MODEL.md`: 타입과 불변 조건
3. `docs/WORKFLOWS.md`: graph node, routing, retry, interrupt 계약
4. `docs/ARCHITECTURE.md`: 레이어와 의존성 규칙
5. `docs/PRD.md`: 제품 범위와 사용자 시나리오
6. 나머지 상세 문서

문서 계약을 변경하는 구현은 관련 문서를 먼저 갱신한다.

## CRITICAL 아키텍처 규칙

- LangChain을 사용하지 않는다. 외부 SDK는 자체 typed provider adapter 내부에 격리한다.
- LangGraph는 번역 품질, 결과 품질, 자연어 수정 workflow에만 사용한다.
- OCR normalization 이후 region geometry는 non-null이어야 한다.
- 일본어 `vertical_rl`은 열 내부 상에서 하, 열 사이 우에서 좌 순서를 보존한다.
- 결정론적 cardinality, region ID, geometry, schema 검증을 LLM에 맡기지 않는다.
- reviewer는 최종 번역문을 직접 생성하지 않고 판정, 근거, 개선 지시만 반환한다.
- 승인된 번역과 원본 OCR snapshot을 mutation하지 않는다.
- 자연어 수정은 승인된 `RevisionPlan` 없이 적용하지 않는다.
- 사용자 승인 없는 프로젝트 컨텍스트 변경을 영속화하지 않는다.
- 사용자 설정 없는 provider fallback을 실행하지 않는다.
- visual mode와 이미지 전송 동의 없이 이미지 또는 crop을 외부 provider에 전달하지 않는다.
- checkpoint에 API key, 이미지 배열, 전체 prompt, provider raw payload를 저장하지 않는다.
- 미해결 `error`/`critical` issue 또는 필수 사용자 확인 대기가 있는 결과의 일반 export를 허용하지 않는다.
- GUI thread에서 OCR, graph, provider 호출, 인페인팅, 렌더링, 저장을 실행하지 않는다.

## 현재 구현 순서

Harness phase는 `phases/index.json`을 따른다.

1. `0-core-vertical-slice`: package boundary, domain model, 품질과 export policy, mock provider, mock workflow use case
2. `1-image-layout-rendering`: image IO, OCR normalization, reading order, inpainting, rendering, export service
3. `2-workflow-provider-runtime`: provider runtime, LangGraph workflow, revision graph, checkpoint와 resume
4. `3-gui-export-release`: GUI, worker, review UI, settings, privacy, export, mock MVP integration gate
5. `4-real-provider-adapters`: DeepL, OpenAI, Gemini, Grok 실제 adapter와 provider smoke release gate

새 구현은 가능한 한 현재 phase와 step의 범위 안에서 진행한다. phase 계약과 다른 순서로 구현해야 하면
관련 phase 문서와 acceptance criteria를 먼저 갱신한다.

## 디렉토리와 경계

목표 구조는 `docs/ARCHITECTURE.md`의 디렉토리 구조와 의존성 규칙을 따른다. 현재 저장소에는 아직
전체 구조가 생성되어 있지 않으므로, 새 모듈을 추가할 때 아래 경계를 보존한다.

- `domain`: standard library와 Pydantic만 의존한다.
- `providers`: 외부 SDK 타입을 adapter 내부에 격리한다.
- `services`: deterministic image, layout, render, export 로직을 둔다.
- `workflows`: LangGraph builder, node, router, state mapping을 둔다.
- `use_cases`: graph 밖 application orchestration을 둔다.
- `gui`: PySide6 UI와 worker 경계를 둔다. provider와 graph node를 직접 호출하지 않는다.
- `persistence`: checkpoint, project context, revision repository를 둔다.

## 코딩 규칙

- Python 코드는 PEP 8과 type annotation을 따른다.
- 안정적인 domain model은 frozen dataclass 또는 immutable Pydantic model을 사용한다.
- 함수는 작고 명확하게 유지하고, mutation은 소유자가 명확한 경계에서만 허용한다.
- 외부 입력은 schema validation을 통과시킨다.
- 오류를 조용히 삼키지 않는다.
- 사용자 오류 메시지와 개발자 로그를 분리한다.
- secret, 이미지 내용, 전체 원문, 전체 번역문을 로그에 기록하지 않는다.
- 파일은 고응집, 저결합을 유지하고 800줄을 넘기지 않는다.
- 코드가 계획 문서의 계약을 구현하기 시작하면 해당 계약의 테스트를 같은 변경에 포함한다.

## TDD와 검증

- 모든 기능과 버그 수정은 테스트를 먼저 작성한다.
- 변경된 behavior에 unit 또는 integration test를 추가한다.
- GUI 주요 흐름은 GUI dependency가 도입된 뒤 pytest-qt로 검증한다.
- 외부 provider 호출은 기본 테스트에서 mock한다.
- 최소 coverage는 80%다.

현재 `.harness/validation.json`의 기본 gate:

```bash
uv run pytest -q
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
uv run ruff check .
uv run mypy src
python3 scripts/run_gui_tests.py
```

`scripts/run_gui_tests.py`는 `QT_QPA_PLATFORM=offscreen`을 설정한다. PySide6/pytest-qt 또는
`tests/gui`가 아직 도입되지 않은 bootstrap 상태에서는 명시적으로 skip하지만, GUI dependency나
GUI test directory가 생긴 뒤에는 실패를 전체 validation 실패로 처리한다. coverage 기준은 낮추지
않으며, 큰 구현 step은 테스트를 먼저 추가한 뒤 구현한다.

Harness 전체 검증은 다음 명령을 우선 사용한다.

```bash
python3 scripts/validate_project.py
```

## Harness와 로컬 스킬

프로젝트 로컬 스킬:

- `.agents/skills/harness-workflow`: phase와 step 설계, 메인 세션 기반 phase 실행
- `.agents/skills/harness-review`: 변경사항과 프로젝트 규칙 검증
- `.agents/skills/harness-validation`: `.harness/validation.json` 생성과 갱신

현재 커밋된 validation은 `.harness/validation.json`이 권위다. 자동 감지 결과를 확인할 때만 다음 명령을
사용한다.

```bash
python3 scripts/configure_harness.py --dry-run
```

`python3 scripts/configure_harness.py --force`는 validation 계약을 의도적으로 재생성할 때만 사용한다.
사용하는 경우 `.harness/validation.json`, `tests/unit/test_bootstrap_contract.py`, 관련 문서를 함께 갱신한다.

phase 실행을 요청받으면 별도 `scripts/execute.py`를 찾지 않는다. 현재 Harness 계약은 메인 세션이
오케스트레이터가 되어 `harness-workflow`의 subagent execution 프로토콜을 따르는 방식이다.

## Codex 설정과 Hooks

프로젝트 로컬 `.codex/config.toml`은 현재 다음을 활성화한다.

- `multi_agent = true`
- `hooks = true`
- Bash command policy, pre-commit validation, stop validation hooks

hook과 validation script를 변경할 때는 `scripts/test_codex_hooks.py`와
`python3 scripts/validate_project.py` 기준을 함께 확인한다.

## Git과 개발 프로세스

- conventional commits를 사용한다: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`
- commit 전 secret, 개인 경로, validation 결과를 확인한다.
- 관련 품질 또는 workflow 계약 변경 시 docs를 함께 갱신한다.
- phase metadata와 step 상태는 실제 실행 상태와 일치해야 한다.
