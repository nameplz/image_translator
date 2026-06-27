# 테스트 전략

## 1. 원칙

- TDD를 적용한다.
- unit, integration, GUI, provider smoke, packaging smoke를 분리한다.
- 외부 provider 없이 mock adapter로 핵심 workflow를 항상 재현할 수 있어야 한다.
- 최소 line coverage는 80%다.
- 번역 품질의 절대 우수성을 fixture로 주장하지 않는다. 테스트는 품질 gate 계약과 routing을 검증한다.

## 2. Test Marker

```text
unit
integration
gui
provider_smoke
packaging_smoke
```

provider smoke는 credential이 없으면 skip한다. 기본 CI는 외부 유료 provider를 호출하지 않는다.
GUI test는 `tests/gui` 경로 기준으로 수집하며, `@pytest.mark.gui` marker는 선택적으로 사용할 수 있다.

## 3. Domain Unit Test

- geometry와 polygon validation
- normalization 이후 non-null geometry
- page 내 region ID uniqueness
- writing mode와 reading order model
- immutable revision과 snapshot
- export eligibility
- rubric total 계산과 critical override

## 4. OCR과 Layout Test

- 일본어 `vertical_rl`: 열 내부 상→하, 열 사이 우→좌
- 가로·세로 혼합 page
- 회전 효과음
- 세로 대사 안의 가로 숫자
- panel과 말풍선 order
- 루비와 본문 연결
- 불확실한 reading order의 interrupt routing
- 주·보조 OCR 불일치
- 원본 OCR snapshot 보존

## 5. TranslationQualityGraph Test

- 모든 region이 review 대상이 됨
- visual mode off에서 이미지 reference 미전달
- visual mode on에서 page와 모든 crop 전달
- missing, duplicate, unknown region ID가 AI review 전에 실패
- critical issue가 점수와 관계없이 승인 차단
- 자동 승인 threshold
- 승인된 region은 다른 region 재번역에서 변경되지 않음
- 최대 2회 재번역 후 문제 region만 interrupt
- provider retry와 품질 retry 카운트 분리
- 사용자 fallback 순서만 사용
- resume 시 완료 provider 호출 미반복

## 6. ResultQualityGraph Test

- clipping, overlap, 최소 폰트, glyph 검사
- 목표 언어 표준 writing mode RenderPlan
- 인페인팅 mask 재처리
- backend escalation
- 최대 2회 자동 수정
- visual mode off의 사용자 확인 상태
- unresolved `error`/`critical` 및 필수 사용자 확인 대기의 export 차단

## 7. NaturalRevisionGraph Test

- 허용 action만 생성
- prompt injection과 임의 도구 요청 거절
- 현재 선택 region 우선
- 자연어 위치 참조 해석
- 모호한 target의 사용자 선택 interrupt
- 적용 범위 후보와 프로젝트 규칙 별도 승인
- 사용자 승인 전 미적용
- 변경 후 관련 graph 재검증
- revision diff, Undo, Redo, 복원

## 8. GUI Test

- 진행 단계와 progress 표시
- progress 비감소
- interrupt의 검토 대기 표시
- thread-safe cancel
- 취소가 실패로 집계되지 않음
- output 경로 실행 전 선택
- 품질 gate 전 파일 미생성
- Save As와 overwrite 확인
- 미해결 issue의 일반 Save 차단
- 자연어 변경 계획 preview
- 오래된 preview와 plan 결과 폐기

## 9. Persistence Test

- SQLite checkpoint 생성과 resume
- Translation/Result/Revision graph thread 연결
- checkpoint에 secret, 이미지 배열, raw payload 없음
- interrupt 작업 보존
- 완료 checkpoint 정리 정책
- 손상 checkpoint의 사용자 친화적 오류

## 10. Provider Contract Test

모든 adapter에 공통 contract suite를 적용한다.

- config validation
- capability 일관성
- language pair
- batch cardinality
- structured output 변환
- timeout과 retryable error 분류
- secret redaction
- visual consent enforcement

## 11. Integration Test

Mock provider 기반 전체 경로:

```text
image fixture
 -> OCR
 -> vertical/mixed layout
 -> TranslationQualityGraph
 -> inpainting
 -> rendering
 -> ResultQualityGraph
 -> natural revision
 -> export
```

성공, 사용자 interrupt, provider retry, fallback, cancel, resume 경로를 각각 검증한다.

## 12. Validation Commands

계획된 기본 gate:

```bash
uv run pytest -q
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
uv run ruff check .
uv run mypy src
python3 scripts/run_gui_tests.py
```

GUI:

```bash
python3 scripts/run_gui_tests.py
```

기본 `uv run pytest -q`와 coverage gate는 `pyproject.toml`의 `testpaths`에 따라
`scripts`, `tests/unit`, `tests/integration`만 수집한다. GUI test는 기본 pytest
collection에서 제외하며 `python3 scripts/run_gui_tests.py`로만 실행한다.
기본 coverage gate도 GUI package와 GUI entrypoint를 제외한다. GUI coverage는 별도
wrapper test 통과 여부로 검증한다.

GUI wrapper는 `QT_QPA_PLATFORM=offscreen`을 설정한다. PySide6/pytest-qt 또는
`tests/gui`가 없으면 bootstrap 상태로 간주해 skip하고, GUI dependency 또는 GUI test가
도입된 뒤에는 `uv run pytest tests/gui` 실패를 전체 validation 실패로 반환한다.
`@pytest.mark.gui`는 선택 사항이며 gate 통과 조건으로 요구하지 않는다.

Provider:

```bash
uv run pytest -m provider_smoke
```

provider smoke는 credential이 있는 release validation에서 별도로 실행한다. credential이 없으면
skip하며, 기본 validation은 외부 유료 provider를 호출하지 않는다.
