# 프로젝트 컨텍스트 스펙

## 1. 목적

여러 이미지에서 캐릭터 이름, 호칭, 말투, 고유명사, 효과음 번역을 일관되게 유지한다. 잘못된 AI 추론이 작품 전체에 전파되지 않도록 모든 영속 규칙은 사용자 승인을 요구한다.

## 2. 컨텍스트 종류

### Character Profile

- 이름과 별칭
- 표시 이름
- 언어별 이름
- 관계와 호칭
- 말투, 존댓말/반말, 자주 쓰는 표현
- 확인된 근거 region

### Glossary

- source term
- target language별 승인 번역
- 번역 금지 또는 음차 규칙
- 대소문자와 표기 규칙
- 적용 범위

### Style Rule

- 기본 현지화 수준
- 대사·내레이션 스타일
- 금지 표현
- 문장부호
- 효과음 처리

### Render Rule

- text role별 기본 스타일
- 일본어 세로쓰기 사용 조건
- 루비 표시 정책
- 효과음 방향과 강조

## 3. 승인 Workflow

AI는 `ContextSuggestion`만 생성한다.

```text
suggested
 -> user edits or accepts
 -> approved
 -> project context version increment
```

거절 또는 미승인 suggestion은 이후 페이지에 적용하지 않는다.

승인 기록:

- suggestion ID
- 이전 값과 새 값
- 근거 page/region
- 적용 언어 방향
- 사용자 승인 시점
- 생성 revision

## 4. 현재 Page 임시 컨텍스트

현재 page에서 발견한 화자, 감정, 관계 후보는 현재 workflow에서 번역 hint로 사용할 수 있다. 다만 프로젝트 컨텍스트와 충돌하면 다음 규칙을 따른다.

1. 승인된 프로젝트 컨텍스트 우선
2. 충돌을 reviewer issue로 표시
3. 사용자에게 컨텍스트 변경 suggestion 제시
4. 자동으로 영속 규칙을 변경하지 않음

## 5. 자연어 규칙 변경

“앞으로 이 인물은 존댓말로 번역해줘”와 같은 지시는 다음 범위 후보를 생성한다.

- 현재 region
- 현재 page
- 프로젝트 전체

사용자가 프로젝트 전체 범위를 승인한 경우에만 context suggestion과 revision을 생성한다.

## 6. Version과 적용

- ProjectContext는 immutable version을 가진다.
- job 시작 시 사용할 context version을 기록한다.
- context 변경은 실행 중인 job에 자동 반영하지 않는다.
- 사용자가 현재 job에 새 context를 적용하면 관련 번역을 재검증한다.
- 과거 승인 결과는 자동 변경하지 않는다.

## 7. 충돌

다음은 자동 병합하지 않는다.

- 같은 source term의 서로 다른 승인 번역
- 같은 캐릭터의 상충하는 말투 규칙
- 언어 방향별 규칙 충돌
- 프로젝트 규칙과 사용자 현재 수정의 충돌

충돌은 사용자에게 근거와 영향을 표시하고 선택을 요구한다.

## 8. 저장과 개인정보

- OS app data의 프로젝트 저장소에 보관한다.
- API key와 provider raw payload를 저장하지 않는다.
- 이미지 전체 내용은 컨텍스트에 저장하지 않고 page/region reference만 기록한다.
- 프로젝트 삭제 시 관련 context와 revision 삭제 옵션을 제공한다.
