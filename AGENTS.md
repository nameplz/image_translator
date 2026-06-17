# 프로젝트: Image Translator

## 프로젝트 목표

만화·웹툰 이미지의 한국어·영어·일본어 텍스트를 정확한 reading order로 인식하고, 의미·말투·작품 맥락을 보존해 번역한 뒤 품질 검증을 통과한 결과 이미지를 생성한다.

처리 속도보다 번역과 최종 이미지의 품질, 판단 근거의 추적성, 사용자 검토 가능성을 우선한다.

## 기술 스택

- Python 3.11+
- PySide6 데스크톱 GUI
- LangGraph workflow orchestration
- Pydantic 2 typed domain model
- NumPy, Pillow, OpenCV
- SQLite checkpointer
- uv package manager
- pytest, pytest-asyncio, pytest-qt, pytest-cov
- ruff, mypy

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
- 일본어 `vertical_rl`은 열 내부 상→하, 열 사이 우→좌 순서를 보존한다.
- 결정론적 cardinality, region ID, geometry, schema 검증을 LLM에 맡기지 않는다.
- reviewer는 최종 번역문을 직접 생성하지 않고 판정·근거·개선 지시만 반환한다.
- 승인된 번역과 원본 OCR snapshot을 mutation하지 않는다.
- 자연어 수정은 승인된 `RevisionPlan` 없이 적용하지 않는다.
- 사용자 승인 없는 프로젝트 컨텍스트 변경을 영속화하지 않는다.
- 사용자 설정 없는 provider fallback을 실행하지 않는다.
- visual mode와 이미지 전송 동의 없이 이미지 또는 crop을 외부 provider에 전달하지 않는다.
- checkpoint에 API key, 이미지 배열, 전체 prompt, provider raw payload를 저장하지 않는다.
- 미해결 `error`/`critical` issue 또는 필수 사용자 확인 대기가 있는 결과의 일반 export를 허용하지 않는다.
- GUI thread에서 OCR, graph, provider 호출, 인페인팅, 렌더링, 저장을 실행하지 않는다.

## 코딩 규칙

- Python 코드는 PEP 8과 타입 annotation을 따른다.
- 안정적인 domain model은 frozen dataclass 또는 immutable Pydantic model을 사용한다.
- 함수는 작고 명확하게 유지하고, mutation은 소유자가 명확한 경계에서만 허용한다.
- 외부 입력은 schema validation을 통과시킨다.
- 오류를 조용히 삼키지 않는다.
- 사용자 오류 메시지와 개발자 로그를 분리한다.
- secret, 이미지 내용, 전체 원문·번역문을 로그에 기록하지 않는다.
- 파일은 고응집·저결합을 유지하고 800줄을 넘기지 않는다.

## TDD와 검증

- CRITICAL: 모든 기능과 버그 수정은 테스트를 먼저 작성한다.
- 변경된 behavior에 unit 또는 integration test를 추가한다.
- GUI 주요 흐름은 pytest-qt로 검증한다.
- 외부 provider 호출은 기본 테스트에서 mock한다.
- 최소 coverage는 80%다.

계획된 기본 검증:

```bash
uv run pytest -q
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
uv run ruff check .
uv run mypy src
```

## Git과 개발 프로세스

- conventional commits를 사용한다: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- commit 전 secret, 개인 경로, validation 결과를 확인한다.
- 관련 품질 또는 workflow 계약 변경 시 docs를 함께 갱신한다.
- Codex headless 호출은 `codex exec -c approval_policy=never -s workspace-write --json "작업 내용"` 형식을 사용한다.

## 프로젝트 로컬 스킬

- `.agents/skills/harness`: phase/step 설계와 `scripts/execute.py` 실행
- `.agents/skills/harness-review`: 변경사항과 프로젝트 규칙 검증
- `.agents/skills/harness-validation`: `.harness/validation.json` 생성

## Harness

```bash
python3 scripts/configure_harness.py
python3 scripts/validate_project.py
python3 scripts/execute.py <phase-dir>
```

스펙 문서 작성 완료 후 validation 설정을 생성한다. 구현 phase는 문서 계약을 읽고 acceptance criteria를 포함해야 한다.
