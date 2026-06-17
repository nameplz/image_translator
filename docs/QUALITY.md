# 품질 기준

## 1. 목적

이 문서는 번역문과 최종 이미지가 자동 승인되기 위한 기준을 정의한다. AI 판정은 보조 신호가 아니라 runtime 품질 gate의 일부지만, 결정론적 검증과 사용자 승인보다 높은 권한을 갖지 않는다.

정적 번역 benchmark 데이터셋은 MVP 범위에 포함하지 않는다. 품질 보증은 모든 실제 작업에 동일한 검증 계약을 적용하고 판정 근거를 기록하는 방식으로 제공한다.

## 2. 품질 계층

### Q0 입력 무결성

- 지원 이미지 형식과 읽기 가능 여부
- region ID 유일성
- bbox 또는 polygon 유효성
- writing mode와 reading order 표현 가능 여부

Q0 실패는 작업을 중단한다.

### Q1 OCR 및 구조 품질

- 원문 전사 정확성
- text role 분류
- 세로 열과 혼합 writing mode 해석
- reading order와 대화 그룹
- 루비와 본문 관계

불확실한 영역은 보조 OCR, visual review 또는 사용자 검토로 보낸다.

### Q2 번역 품질

- 의미, 완전성, 자연스러움
- 캐릭터 말투, 화자 관계, 감정
- 앞뒤 대화와 페이지 맥락
- 프로젝트 용어와 호칭
- text role에 맞는 표현
- 렌더 가능한 길이와 구조

### Q3 이미지 합성 품질

- 원문 제거와 배경 보존
- 텍스트 위치, 방향, 크기, contrast
- 원본 스타일 근사
- 전체 페이지 가독성과 시선 흐름

### Q4 사용자 승인 품질

- 자동 gate 미통과 영역의 명시적 검토
- 자연어 수정 계획 승인
- 프로젝트 컨텍스트 변경 승인
- 강제 승인과 강제 export 기록

## 3. OCR Risk Score

OCR risk는 다음 신호로 계산한다.

- 주 OCR confidence
- 주·보조 OCR 문자열 불일치
- 감지 언어와 문자 분포 불일치
- 비정상 문자 또는 깨진 조합
- writing mode confidence
- reading order ambiguity
- crop 크기 대비 문자열 길이
- 루비·본문 관계 불확실성

정확한 가중치는 설정 가능한 정책 객체로 관리한다. 다음은 항상 high risk다.

- bbox 또는 polygon이 유효하지 않음
- reading order 후보가 충돌함
- 주·보조 OCR이 의미상 다른 결과를 반환함
- 본문과 루비를 구분할 수 없음

## 4. 번역 Review Rubric

각 항목은 1.0~5.0이다.

| 항목 | 평가 내용 |
|---|---|
| `semantic_fidelity` | 핵심 의미, 극성, 행위, 대상 보존 |
| `completeness` | 누락과 불필요한 추가 여부 |
| `naturalness` | 목표 언어 대사로서 자연스러움 |
| `character_voice` | 캐릭터 말투, 감정, 관계 일관성 |
| `context_fit` | 장면, 화자, 앞뒤 대화와의 일치 |
| `terminology` | 승인된 이름, 호칭, glossary 준수 |
| `text_role_fit` | 대사, 내레이션, 효과음 역할 적합성 |
| `renderability` | 영역에 배치 가능한 길이와 구조 |

가중 종합 점수 기본값:

```text
semantic_fidelity 25%
completeness      15%
naturalness       15%
character_voice   15%
context_fit       15%
terminology       10%
text_role_fit      3%
renderability      2%
```

## 5. Critical Issue

다음 이슈가 하나라도 있으면 점수와 무관하게 자동 승인하지 않는다.

- 의미 반전 또는 핵심 의미 손실
- 화자, 대상, 인물 관계 오류
- 이름, 숫자, 부정 표현, 호칭 오류
- 원문에 없는 중요 정보 생성
- 목표 언어가 아닌 결과
- 승인된 glossary의 의미 변경
- reading order 오류로 인한 문맥 왜곡
- 번역 결과 누락, 중복, 알 수 없는 region ID

## 6. 자동 승인과 재번역

자동 승인 조건:

- critical issue 없음
- 가중 종합 점수 `>= 4.0`
- `semantic_fidelity`, `completeness`, `character_voice` 각각 `>= 3.5`
- 모든 구조 검증 통과

재번역 정책:

- 실패 영역만 재번역한다.
- 이미 승인된 영역은 변경하지 않는다.
- reviewer는 issue, evidence summary, 개선 지시를 반환한다.
- 자동 재번역은 영역별 최대 2회다.
- 최대 횟수 이후에는 해당 영역만 사용자 검토로 보낸다.

## 7. 이미지 합성 품질

### 결정론적 검사

- bbox 밖 clipping
- 텍스트 또는 line overlap
- 최소 폰트 크기 위반
- contrast 부족
- 지원하지 않는 glyph
- 잘못된 writing mode
- 열·행 순서 오류
- 번역 영역 누락
- 루비와 본문 배치 충돌

### AI 시각 검사

visual mode가 활성화된 경우:

- 원문 잔상
- 인페인팅 배경 훼손
- 텍스트와 말풍선 대응
- 원본 스타일과의 불일치
- 효과음 방향과 강조
- 전체 페이지 시선 흐름
- 결과물 가독성

### 자동 수정

- 줄바꿈, 글자 크기, 자간, 행간, 정렬
- 텍스트 방향과 위치
- 색상, 외곽선, contrast
- 인페인팅 mask
- 인페인팅 backend escalation
- RenderPlan style

자동 수정은 최대 2회다. 남은 문제는 사용자 검토로 전환한다.

## 8. Visual Mode

- 기본값은 off다.
- 사용자가 활성화하고 이미지 전송에 동의한 경우에만 이미지와 crop을 외부 provider에 전달한다.
- 활성화 시 모든 번역 영역과 최종 페이지를 멀티모달로 검증한다.
- 비활성화 시 text 기반 검증과 결정론적 이미지 검사를 수행하고, 최종 시각 품질은 사용자 확인 대상으로 표시한다.

## 9. 승인 상태

```text
pending
approved_automatic
approved_user
approved_forced
needs_review
rejected
cancelled
```

`approved_forced`에는 사용자, 시각, 미해결 issue, 사유를 기록한다.

Export를 차단하는 blocking 상태:

- 미해결 `error` 또는 `critical` issue
- visual mode off 등으로 인해 필수 사용자 확인이 아직 완료되지 않은 상태

`warning`은 사용자 확인 후 일반 export할 수 있다.

## 10. 품질 기록

각 판정은 다음을 기록한다.

- job, thread, revision, region ID
- provider와 model version
- prompt contract version
- rubric 점수
- issue code와 severity
- evidence summary
- attempt
- decision
- 사용자 승인 또는 강제 승인 정보

API key, 전체 prompt, provider raw payload, 이미지 내용은 기록하지 않는다.
