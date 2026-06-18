# 아키텍처

## 1. 설계 목표

- 품질 판정과 수정 이력을 재현 가능하게 만든다.
- 결정론적 검증과 AI 판단을 분리한다.
- OCR, 번역, 검증, 인페인팅 provider를 교체 가능하게 유지한다.
- GUI thread를 모든 무거운 작업에서 격리한다.
- LangGraph는 상태가 있는 품질 workflow에만 사용한다.
- 원본 데이터와 승인 결과를 불변 snapshot으로 보존한다.

## 2. 기술 스택

- Python 3.11+
- PySide6
- LangGraph
- Pydantic 2
- NumPy, Pillow, OpenCV
- SQLite checkpointer
- uv
- pytest, pytest-asyncio, pytest-qt, pytest-cov
- ruff, mypy

LangChain은 사용하지 않는다. 외부 provider SDK는 typed adapter 내부에서만 사용한다.

## 3. 디렉토리 구조

```text
src/
  image_translator/
    app/             # bootstrap, dependency wiring, entrypoint
    domain/          # immutable DTO, enum, typed error
    config/          # typed settings, user config, resource paths
    providers/       # OCR, translator, reviewer, inpainting adapters
    services/        # image IO, normalization, layout, rendering, export
    workflows/       # LangGraph builders, nodes, routers, state mapping
    use_cases/       # graph 외부 application orchestration
    persistence/     # checkpoint, project context, revision repository
    gui/             # windows, controllers, widgets, workers
    observability/   # structured logging, progress mapping
tests/
  unit/
  integration/
  gui/
  provider_smoke/
docs/
config/
assets/
```

## 4. 의존성 규칙

```text
app -> config, providers, services, workflows, use_cases, persistence, gui
gui -> domain, config, use_cases
use_cases -> domain, config, services, workflows, persistence
workflows -> domain, providers, services, persistence
services -> domain, config
providers -> domain, config
persistence -> domain, config
config -> domain
domain -> standard library, Pydantic only
```

금지 사항:

- `domain`은 PySide6, LangGraph, provider SDK, OpenCV를 import하지 않는다.
- `gui`는 graph node나 provider adapter를 직접 호출하지 않는다.
- `services`는 외부 provider API를 호출하지 않는다.
- provider SDK 타입은 `providers` 밖으로 노출하지 않는다.
- graph state를 GUI runtime state로 직접 사용하지 않는다.
- 결정론적 정합성 검증을 LLM에 맡기지 않는다.

## 5. 처리 경계

### 결정론적 Pipeline

- 이미지 로드 및 파일 검증
- OCR normalization
- bbox, polygon, region ID 검증
- writing mode와 reading order 기본 분석
- inpainting 실행
- RenderPlan 실행
- export

### LangGraph Workflow

- OCR 위험 영역 교차 확인과 선택적 AI 교정
- 페이지 맥락 생성
- 번역, 품질 검증, 재번역
- 사용자 검토 interrupt와 resume
- 최종 이미지 품질 판단과 재처리 routing
- 자연어 수정 계획 생성, 승인, 적용, 재검증

LangGraph node는 domain DTO를 입력받고 domain DTO patch를 반환한다. node 내부에서 공유 객체를 mutation하지 않는다.

## 6. 상태 소유권

### JobDefinition

사용자가 선택한 실행 설정이다. 생성 후 변경하지 않는다.

- input path
- requested output path
- source/target language
- provider IDs와 fallback 순서
- visual mode 및 이미지 전송 동의
- 프로젝트 ID

### JobSnapshot

GUI에 전달하는 immutable 진행 이벤트다.

- job ID
- status
- progress
- stage
- message
- interrupt summary

### Workflow State

LangGraph checkpoint 대상이다. workflow 내부에서만 소유한다.

- `model_dump(mode="json")` 가능한 JSON-serializable domain DTO
- region별 attempt와 decision
- provider request fingerprint
- interrupt payload

`Path`, PIL image, NumPy array, 이미지 배열, image/crop bytes, secret, 전체 prompt, provider raw payload는 포함하지 않는다.

### ImageDocumentSession

GUI 편집 세션이 소유한다.

- 현재 승인 revision
- 선택 region
- 원본과 preview 이미지 reference
- 미해결 issue 요약

### RevisionRepository

승인된 수정 이력과 diff를 append-only로 저장한다. 기존 revision을 mutation하지 않는다.

## 7. Persistence

- 한 이미지 작업은 하나의 `job_id`를 가진다.
- TranslationQualityGraph, ResultQualityGraph, NaturalRevisionGraph는 별도 `thread_id`를 사용한다.
- 모든 graph는 `job_id`와 revision ID로 연결한다.
- SQLite checkpointer는 OS app data 경로에 저장한다.
- 완료·실패 checkpoint는 기본 30일 보존한다.
- 검토 대기 checkpoint는 사용자가 해결하거나 삭제할 때까지 보존한다.
- provider 호출 node는 request fingerprint를 사용해 resume 시 중복 호출을 피한다.
- resume 시 node가 다시 실행될 수 있으므로 외부 부작용은 idempotent하게 만든다.

## 8. GUI와 Worker

- worker thread가 asyncio event loop와 graph task를 소유한다.
- 취소는 `loop.call_soon_threadsafe(task.cancel)`로 전달한다.
- `CancelledError`는 `CANCELLED`로 변환한다.
- graph stream update는 progress mapper가 `JobSnapshot`으로 변환한다.
- GUI는 signal을 통해 snapshot, preview, interrupt payload를 받는다.
- preview와 자연어 수정 결과는 monotonically increasing request ID를 사용한다.
- 오래된 preview와 변경 계획은 폐기한다.

## 9. 오류 정책

주요 typed error:

- `ImageLoadError`
- `InvalidRegionError`
- `ReadingOrderUncertainError`
- `ProviderConfigError`
- `ProviderCallError`
- `TranslationResultMismatchError`
- `QualityGateRejected`
- `RevisionPlanRejected`
- `ExportBlockedError`
- `WorkflowCancelled`
- `CheckpointError`

사용자 메시지는 단계와 해결 가능한 원인을 설명한다. API key, raw provider payload, 전체 prompt, 전체 번역문은 로그나 오류 메시지에 기록하지 않는다.

## 10. 관측 가능성

구조화 로그 필드:

- job ID, thread ID, revision ID
- stage, node, provider ID
- attempt, elapsed time
- region count와 issue count
- result status

품질 판정에는 rubric 점수, issue code, evidence summary, prompt contract version, provider/model version을 기록한다.

## 11. 관련 문서

- 도메인 모델: [DOMAIN_MODEL.md](DOMAIN_MODEL.md)
- workflow: [WORKFLOWS.md](WORKFLOWS.md)
- provider 계약: [PROVIDERS.md](PROVIDERS.md)
- 보안과 개인정보: [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md)
