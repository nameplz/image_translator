# 보안 및 개인정보 스펙

## 1. 신뢰 경계

다음은 모두 신뢰할 수 없는 입력이다.

- 사용자 파일과 경로
- OCR 및 provider 응답
- 사용자 자연어 수정 지시
- project context import
- checkpoint와 user config 파일

모든 입력은 schema와 허용 목록으로 검증한다.

## 2. Secret

- API key는 환경변수 또는 ignored user config에서만 로드한다.
- source, committed config, docs, logs, checkpoint에 값을 저장하지 않는다.
- 오류 메시지는 환경변수 이름을 표시할 수 있지만 값을 포함하지 않는다.
- provider 요청과 로그에서 secret을 redaction한다.

## 3. 이미지 전송 동의

- visual mode 기본값은 off다.
- 사용자가 활성화하기 전에 provider와 전송 대상을 표시한다.
- 동의는 작업 설정에 기록한다.
- 동의가 없으면 전체 이미지와 crop을 외부 provider에 전달하지 않는다.
- local provider는 capability에서 cloud 여부를 명시한다.

## 4. 자연어 수정 보안

- 자연어 입력은 허용된 `RevisionAction`으로만 변환한다.
- shell, 파일 탐색, 임의 network, provider 설정 변경을 허용하지 않는다.
- 사용자 입력 속 prompt injection을 시스템 정책으로 해석하지 않는다.
- 구조화 계획을 사용자 승인 전 적용하지 않는다.
- target region과 범위가 모호하면 실행하지 않는다.

## 5. 파일과 경로

- 지원 이미지 확장자, 실제 파일 타입, 크기를 검증한다.
- symlink와 경로 traversal을 고려한다.
- input 파일을 덮어쓰지 않는다.
- output 저장은 임시 파일 후 atomic replace를 사용한다.
- user-facing 오류에 불필요한 내부 경로를 노출하지 않는다.

## 6. Checkpoint와 Local Data

- SQLite checkpoint와 프로젝트 데이터는 OS app data 경로에 저장한다.
- 이미지 배열, API key, provider raw payload, 전체 prompt를 저장하지 않는다.
- 필요한 이미지 reference는 사용자가 접근 가능한 로컬 경로만 저장한다.
- checkpoint 파일 권한을 가능한 범위에서 사용자 전용으로 제한한다.
- 완료·실패 checkpoint는 기본 30일 후 정리할 수 있다.
- 사용자에게 project, revision, checkpoint 삭제 기능을 제공한다.

## 7. Logging

기록 가능:

- job/thread/revision ID
- stage와 provider ID
- elapsed time
- issue code와 안전한 요약
- 성공·실패 상태

기록 금지:

- API key
- 전체 원문과 번역문
- 이미지 내용
- 전체 prompt와 provider raw response
- 개인 식별 metadata

## 8. Provider Error

- raw provider error를 UI에 그대로 표시하지 않는다.
- 사용자 메시지와 개발자 로그를 분리한다.
- provider 응답에 포함된 사용자 데이터와 credential을 redaction한다.

## 9. Dependency와 Release

- lockfile을 커밋한다.
- release 전에 dependency audit를 수행한다.
- provider SDK 변경은 smoke test로 확인한다.
- 알려진 critical vulnerability가 있으면 release를 차단한다.
