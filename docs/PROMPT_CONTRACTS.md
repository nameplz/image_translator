# Prompt 및 AI 출력 계약

## 1. 원칙

이 문서는 실제 prompt 문구보다 AI 호출의 입력, 권한, 출력 schema, 실패 정책을 정의한다.

- AI 입력은 신뢰할 수 없는 외부 데이터와 사용자 텍스트를 포함한다.
- 모델은 시스템 정책, 허용 action, 품질 기준을 변경할 권한이 없다.
- 출력은 typed schema validation을 통과해야 한다.
- 근거 없는 추론은 낮은 confidence 또는 사용자 검토로 표현한다.
- prompt contract version을 모든 품질 기록에 남긴다.

## 2. 공통 입력 구분

각 요청은 입력을 명시적으로 구분한다.

- `policy`: 변경 불가능한 시스템 규칙
- `task`: 수행할 제한된 작업
- `trusted_context`: 승인된 프로젝트 규칙과 domain metadata
- `untrusted_content`: OCR text, 번역 후보, 사용자 자연어 지시
- `visual_references`: 동의된 이미지와 crop reference
- `output_schema`: 허용 출력 형식

`untrusted_content` 안의 명령은 정책으로 해석하지 않는다.

## 3. OCR 교정 계약

입력:

- region geometry와 writing mode 후보
- 주·보조 OCR 후보
- 주변 region text
- visual mode에서 crop

출력:

- selected candidate 또는 corrected candidate
- confidence
- evidence summary
- unresolved ambiguity
- reading order 영향 여부

금지:

- 이미지에서 확인할 수 없는 텍스트 생성
- 원문 의미를 번역하여 반환
- 원본 OCR snapshot 수정

## 4. Page Context 계약

입력:

- 승인 OCR과 reading order
- text role
- 승인된 프로젝트 컨텍스트
- visual mode에서 페이지와 crop

출력:

- scene summary
- dialogue groups
- speaker/addressee 후보
- region별 tone, emotion, translation hint
- 프로젝트 컨텍스트 suggestion
- confidence와 evidence summary

규칙:

- suggestion은 승인된 규칙으로 표시하지 않는다.
- 불확실한 화자 관계를 확정적으로 표현하지 않는다.
- 전체 scene summary를 모든 region hint에 반복하지 않는다.

## 5. 번역 Review 계약

입력:

- source와 target language
- page reading order
- 원문 OCR과 번역 candidate
- text role
- page/region/project context
- visual mode에서 페이지와 crop
- 품질 rubric

출력:

- region별 rubric 점수
- critical issue code
- non-critical issue
- evidence summary
- actionable improvement instruction
- decision recommendation

금지:

- 대체 번역문 생성
- 승인된 glossary 변경
- 다른 region의 승인 번역 변경 지시
- 근거 없는 critical issue 생성

## 6. 최종 이미지 Review 계약

입력:

- 원본, inpainted, rendered image reference
- region geometry와 RenderPlan
- 결정론 검사 결과

출력:

- region/page issue
- severity
- evidence location
- 허용 correction recommendation
- 사용자 검토 필요 여부

금지:

- 이미지 내용을 번역 결과로 변경
- 허용 목록 밖의 이미지 편집 제안
- 결정론 검사 실패 무시

## 7. 자연어 수정 Intent 계약

입력:

- 사용자 지시
- 현재 선택 region
- page regions와 reading order
- 현재 revision
- 허용 action 목록

출력:

- normalized intent
- candidate target regions
- candidate scope
- proposed allowed actions
- ambiguity와 required confirmation

금지:

- 파일 읽기·쓰기 지시 생성
- shell, network, provider 설정 변경
- 사용자 승인 없는 action 적용
- 허용 action 목록 확장
- 자연어 속 prompt injection 실행

## 8. Schema 실패

- 첫 schema parse 실패는 같은 provider에 correction request를 한 번 보낼 수 있다.
- 반복 실패는 provider error로 분류한다.
- 사용자 fallback이 있으면 다음 호환 provider를 시도할 수 있다.
- schema validation을 우회해 raw text를 사용하지 않는다.

## 9. Prompt Version

각 계약은 독립 version을 가진다.

```text
ocr-correction/v1
page-context/v1
translation-review/v1
result-image-review/v1
revision-intent/v1
```

version 변경 시:

- 관련 contract fixture test를 갱신한다.
- 이전 checkpoint resume 호환성을 검토한다.
- 품질 기록에 새 version을 남긴다.

## 10. 사용자 표시

사용자에게는 provider의 전체 reasoning이나 raw response를 노출하지 않는다. 다음만 표시한다.

- issue 요약
- 영향 region
- 확인 가능한 근거
- 추천 수정
- confidence 또는 불확실성
