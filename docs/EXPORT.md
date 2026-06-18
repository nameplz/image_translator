# 저장 및 Export 스펙

## 1. 목표

사용자가 결과 경로와 포맷을 명시적으로 제어할 수 있게 하고, 미해결 품질 문제가 정상 결과에 섞이는 것을 방지한다.

## 2. 경로 선택

- 실행 전에 output 파일 경로를 선택할 수 있다.
- 실행 전에 지정한 경로는 `JobDefinition.requested_output_path`에 저장한다.
- 품질 gate 통과 전에는 해당 경로에 파일을 생성하지 않는다.
- output 경로 없이 “검토 후 저장” 모드로 실행할 수 있다.
- 완료 후 Save As로 경로를 변경할 수 있다.
- 자동 저장은 사용자가 명시적으로 활성화한 경우에만 수행한다.

## 3. 경로 검증

저장 전 확인:

- 부모 디렉토리 존재 또는 생성 승인
- 부모 디렉토리 쓰기 가능 여부
- 지원 확장자
- 선택 format과 확장자 일치
- 입력 이미지와 다른 경로
- 기존 파일 존재 여부

기존 파일 덮어쓰기는 사용자 확인이 필요하다. 임시 파일에 먼저 기록하고 성공 후 atomic replace를 사용한다.

## 4. 포맷

지원 포맷:

- PNG: 기본, 품질 보존 우선
- JPEG: quality 설정 지원
- WebP: quality/lossless 설정 지원

format별 metadata 보존 정책은 명시적으로 설정한다. 기본값은 개인 정보가 포함될 수 있는 metadata를 제거하는 것이다.

## 5. Export Gate

일반 export 허용 조건:

- FinalImageResult가 승인 상태
- unresolved `error`/`critical` issue 없음
- `requires_user_confirmation` 필수 사용자 확인 대기 없음
- 저장 경로 검증 통과
- 최신 승인 revision과 일치

`requires_user_confirmation`은 unresolved `error`/`critical` issue가 없어도 일반 export를 막는
명시적 blocker다. visual mode off로 최종 시각 품질을 AI가 확인하지 못한 결과는
`requires_user_confirmation=["visual_quality_unconfirmed"]` 같은 사유를 유지하고, 사용자가
최종 preview를 확인하기 전까지 일반 export를 허용하지 않는다.

blocking issue가 있으면:

- 일반 Save 비활성화
- issue 목록과 위치 표시
- 사용자 확인 후 강제 export 가능
- `ForceApprovalRecord`에 issue, `requires_user_confirmation` 항목, 사용자 사유(reason)를 기록

`warning`은 사용자가 확인하면 일반 export할 수 있다.

## 6. 저장 실패

- 사용자 메시지에 경로와 해결 가능한 원인을 표시한다.
- 임시 파일을 정리한다.
- 기존 파일을 손상시키지 않는다.
- 저장 실패는 번역 결과와 revision을 삭제하지 않는다.
- 재시도와 Save As를 허용한다.

## 7. Output Naming

사용자가 경로를 지정하지 않고 자동 저장을 켠 경우 기본 규칙:

```text
<input-stem>.<target-language>.translated.<extension>
```

입력 파일과 같은 경로가 되면 이름에 suffix를 추가한다. 자동 overwrite는 허용하지 않는다.

## 8. Audit

export 기록:

- job ID와 revision ID
- output path
- format options
- export time
- 일반 또는 강제 export
- unresolved issue summary

전체 이미지 내용과 secret은 audit log에 기록하지 않는다.
