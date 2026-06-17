# Architecture Decision Records

## 철학

Image Translator는 속도보다 결과 품질과 판단 추적성을 우선한다. 외부 AI의 출력을 신뢰 경계 밖 입력으로 취급하며, 결정론적 검증과 사용자 승인을 통해 자동화의 위험을 제한한다.

---

### ADR-001: LangGraph를 품질 workflow에 사용

**결정**: TranslationQualityGraph, ResultQualityGraph, NaturalRevisionGraph에 LangGraph를 사용한다. 이미지 IO, normalization, 인페인팅 실행, 렌더링, export는 일반 application service로 유지한다.

**이유**: 재번역, 재처리, 사용자 interrupt, 앱 재시작 후 resume, revision 재검증은 상태와 분기가 많은 장기 workflow다.

**트레이드오프**: dependency와 checkpoint 운영 복잡성이 증가한다. 모든 graph node는 idempotency와 직렬화 가능 상태를 고려해야 한다.

### ADR-002: LangChain을 사용하지 않고 자체 adapter를 사용

**결정**: provider SDK는 자체 typed adapter로 감싼다.

**이유**: DeepL과 LLM provider를 동일한 LangChain abstraction에 억지로 맞추지 않고, capability와 오류 정책을 프로젝트 요구에 맞게 통제한다.

**트레이드오프**: provider별 adapter와 structured output 처리를 직접 유지해야 한다.

### ADR-003: 모든 번역은 AI 품질 검증을 거침

**결정**: balanced 프로파일에서도 모든 번역 영역을 text 기반 AI reviewer가 검증한다. visual mode가 활성화되면 모든 영역을 멀티모달로 추가 검증한다.

**이유**: 번역 품질이 제품의 최우선 가치이며, 짧은 만화 대사는 규칙 기반 검사만으로 의미·화자·말투 오류를 발견하기 어렵다.

**트레이드오프**: 비용과 처리 시간이 증가한다. AI reviewer의 오판 가능성 때문에 critical issue taxonomy와 사용자 검토 경로가 필요하다.

### ADR-004: Reviewer는 번역문을 직접 생성하지 않음

**결정**: reviewer는 판정, 점수, 근거, 개선 지시만 반환한다. 수정 번역은 translator가 생성한다.

**이유**: 생성과 평가 책임을 분리하고, 수정 과정과 provider 역할을 추적 가능하게 유지한다.

**트레이드오프**: 재번역 호출이 추가되어 비용과 지연이 증가한다.

### ADR-005: SQLite checkpoint와 human interrupt 사용

**결정**: OS app data 위치의 SQLite checkpointer를 사용하며 사용자 검토는 LangGraph interrupt/resume으로 처리한다.

**이유**: 앱 종료, provider 오류, 긴 검토 대기 후에도 작업을 안전하게 재개해야 한다.

**트레이드오프**: checkpoint schema와 보존 정책을 관리해야 하며, node 재실행을 고려한 idempotent 설계가 필요하다.

### ADR-006: 목표 언어 표준 쓰기 방향 우선

**결정**: OCR과 문맥 해석에서는 원문의 writing mode를 정확히 보존한다. 결과 렌더링은 목표 언어의 표준 가독성을 우선한다.

**이유**: 일본어 세로쓰기 원문을 한국어·영어로 번역할 때 세로 배치를 강제하면 가독성과 공간 활용이 악화될 수 있다.

**트레이드오프**: 원본과 결과의 방향이 달라질 수 있으며, RenderPlan이 영역 재배치를 수행해야 한다.

### ADR-007: 자연어 수정은 제한된 계획으로 변환

**결정**: 자연어 수정 지시는 허용된 `RevisionAction`으로 변환하고, 구조화된 계획을 사용자가 승인한 후 적용한다.

**이유**: 사용 편의성을 제공하면서도 모호한 지시와 임의 도구 실행으로 인한 변경을 방지한다.

**트레이드오프**: 즉시 적용보다 단계가 늘어나며 intent parser와 plan preview가 필요하다.

### ADR-008: 프로젝트 컨텍스트는 사용자 승인 후 영속화

**결정**: AI는 캐릭터, 호칭, 말투, 용어 변경을 제안할 수 있지만 사용자 승인 전에는 프로젝트 규칙으로 저장하지 않는다.

**이유**: 잘못된 자동 추론이 이후 모든 페이지에 전파되는 것을 방지한다.

**트레이드오프**: 사용자의 검토 부담이 증가한다.

### ADR-009: 사용자 지정 fallback만 허용

**결정**: provider fallback은 사용자가 순서를 설정한 경우에만 실행한다.

**이유**: provider 변경은 비용, 개인정보, 결과 일관성에 영향을 준다.

**트레이드오프**: fallback 미설정 시 일부 작업은 자동 완료되지 않는다.

### ADR-010: 미해결 blocking 품질 이슈가 있으면 일반 export 차단

**결정**: 미해결 `error`/`critical` issue 또는 필수 사용자 확인 대기가 남으면 일반 export를 차단한다. `warning`은 사용자가 확인하면 일반 export할 수 있다. blocking issue가 남아 있어도 사용자는 경고를 확인하고 강제 export할 수 있다.

**이유**: 품질 실패가 정상 결과처럼 저장되는 것을 막는다.

**트레이드오프**: 빠른 임시 결과가 필요한 사용자는 추가 확인 절차를 거쳐야 한다.

### ADR-011: Python bootstrap과 첫 구현 slice

**결정**: import package 이름은 `image_translator`로 확정한다. 프로젝트는 `uv`와 `pyproject.toml`을 기준으로 관리하며 Python `>=3.11`을 지원한다. bootstrap 직후부터 `pytest`, coverage 80%, `ruff`, `mypy src`를 Harness validation gate로 사용한다. 첫 구현 slice는 domain model, mock provider, 품질 workflow skeleton, export gate를 잇는 코어 경로로 한다.

**이유**: 구현 phase가 시작되기 전에 package, dependency, validation, 첫 수직 slice 기준을 고정해 worker가 임의 결정을 내리지 않게 한다.

**트레이드오프**: strict gate를 초기부터 유지하기 위해 작은 변경도 테스트와 타입 검증을 함께 갱신해야 한다.
