# 릴리스 및 운영 스펙

## 1. Release Gate

모든 릴리스는 다음을 통과해야 한다.

- lockfile 기반 dependency 설치 가능
- unit, integration, GUI test 통과
- coverage 80% 이상
- ruff clean
- mypy 합의 범위 clean
- mock 전체 workflow 통과
- source tree 밖 resource loading
- secret 및 개인 경로 검사
- dependency audit

실제 provider smoke는 credential과 provider 가용 환경이 있는 release validation에서
`uv run pytest -m provider_smoke`로 별도 수행한다. credential이 없으면 skip한다.

## 2. CI 단계

### 기본 PR Gate

```text
uv sync --locked --group dev
pytest
coverage
ruff
mypy
offscreen GUI tests
```

### Release Gate

- provider smoke (`uv run pytest -m provider_smoke`, credential 없으면 skip)
- installed wheel smoke
- source tree 밖 실행
- PyInstaller artifact smoke
- resource loading
- checkpoint migration test

## 3. Resource

config, provider registry, fonts, styles, icons은 동일한 resource path abstraction으로 찾는다.

- source checkout
- installed wheel
- PyInstaller artifact

임의 module에서 source-tree-relative 경로를 계산하지 않는다.

## 4. User Data

OS app data:

- user config
- project context
- revision repository
- SQLite checkpoint
- logs
- cache

committed config:

- secret 없음
- 개인 경로 없음
- recent files 없음
- provider 기본 capability와 안전한 기본값만 포함

## 5. Checkpoint Migration

- checkpoint schema version을 저장한다.
- 호환 변경은 migration을 제공한다.
- 호환 불가능한 변경은 재개 불가 이유와 안전한 삭제 옵션을 표시한다.
- migration 실패 시 원본 checkpoint를 보존한다.

## 6. Provider 변경

provider SDK 또는 model 기본값 변경 시:

- capability와 schema contract 확인
- `provider_smoke` marker smoke test 실행
- prompt contract compatibility 확인
- release note에 변경 기록

모델 ID는 명시적으로 설정하고 provider의 “latest” alias에 의존하지 않는다.

## 7. Packaging

초기 개발은 wheel 실행을 기준으로 한다. PyInstaller는 MVP 이후지만 resource abstraction과 OS app data 정책은 처음부터 적용한다.

Windows artifact 수용 기준:

- repo 밖에서 실행
- font와 style 로드
- SQLite checkpoint 생성
- GUI 시작
- mock workflow 실행

## 8. Release Checklist

- [ ] 모든 validation gate 통과
- [ ] provider smoke 결과 기록
- [ ] dependency audit 결과 기록
- [ ] 새 secret 또는 개인 경로 없음
- [ ] migration과 rollback 검토
- [ ] docs와 changelog 갱신
- [ ] known issue와 미지원 기능 명시
