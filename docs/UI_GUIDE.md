# UI 디자인 및 상호작용 가이드

## 1. 디자인 원칙

1. 결과 품질과 미해결 문제를 숨기지 않는다.
2. 자동화가 내린 판단과 사용자가 승인해야 할 결정을 구분한다.
3. 원본, OCR, 번역, 인페인팅, 최종 결과를 쉽게 비교할 수 있어야 한다.
4. 장시간 작업의 현재 단계와 진행률을 항상 확인할 수 있어야 한다.
5. 자연어 수정은 자유 실행이 아니라 변경 계획 승인 흐름으로 제공한다.

## 2. Main Window

기본 레이아웃:

```text
┌ Toolbar: Open | Run | Cancel | Output Path | Save As | Settings ┐
├ Left/Center: Image Comparison Viewer                            ┤
│   Original | OCR Overlay | Inpainted | Result                  │
├ Right: Region Inspector / Review Queue / Revision Plan         ┤
└ Bottom: Stage, Progress %, Status Message                       ┘
```

### Toolbar

- 이미지 열기
- 번역 실행
- 취소
- output 경로 선택
- Save As
- provider 및 프로젝트 설정
- 재개 가능한 작업 목록

Run은 필수 설정과 output 경로 검증 후 활성화한다. output 경로가 없더라도 사용자가 명시적으로 “검토 후 저장”을 선택하면 실행할 수 있다.

## 3. Image Comparison Viewer

필수 기능:

- zoom, pan
- 원본과 결과 split/overlay 비교
- OCR region polygon 표시
- writing mode와 reading order 표시
- text role별 overlay 구분
- 선택 region 강조
- issue severity 표시
- 원본, inpainted, rendered 탭

세로쓰기 표시:

- `vertical_rl` 열 순서 화살표
- 열 내부 상→하 순서
- 대화 그룹 간 order
- 루비와 본문 연결선

reading order가 불확실한 경우 overlay에서 대체 후보를 표시하고 사용자가 수정할 수 있어야 한다.

## 4. Progress UI

사용자에게 다음을 표시한다.

- 현재 단계
- 전체 진행률
- 현재 상태 메시지
- 실행 중, 취소 중, 검토 대기, 완료, 실패 상태
- 취소 가능 여부

표시 단계:

```text
이미지 준비
OCR 실행
OCR 교차 검증
페이지 구조 분석
시각 컨텍스트 분석
번역
번역 품질 검증
재번역
사용자 검토 대기
인페인팅
렌더링
결과 품질 검증
수정 적용
저장 준비
완료
```

규칙:

- progress는 감소하지 않는다.
- 재시도 시 현재 단계 메시지에 시도 횟수를 표시한다.
- interrupt 상태에서 progress를 유지하고 `사용자 검토 대기`로 표시한다.
- GUI thread에서 무거운 작업을 실행하지 않는다.

## 5. Region Inspector

선택 영역에 다음을 표시한다.

- 원본 crop
- 주 OCR, 보조 OCR, 승인 OCR
- OCR confidence와 불일치
- writing mode, text role, reading order
- 번역 후보와 승인 번역
- reviewer rubric 점수
- issue, 근거 요약, 개선 지시
- 적용된 RenderPlan

액션:

- OCR 수정
- reading order 수정
- 번역문 직접 수정
- 재번역
- 재검증
- 강제 승인
- 인페인팅 재처리
- 렌더 스타일 수정

각 액션은 역할이 명확히 분리되어야 한다.

## 6. Review Queue

review queue는 자동 승인을 통과하지 못한 항목만 모아 표시한다.

필터:

- OCR/reading order
- 번역 critical issue
- 번역 품질 점수 미달
- 인페인팅
- 렌더 레이아웃
- 최종 시각 확인 필요
- 프로젝트 컨텍스트 제안

각 항목은 영향을 받는 region, issue severity, 추천 액션을 표시한다.

## 7. 자연어 수정 UI

### 입력

- 현재 선택 region을 기본 대상으로 사용한다.
- 선택 없이도 위치·순서·text role 참조를 입력할 수 있다.
- 예: “오른쪽 위 대사를 존댓말로 바꿔줘.”

### 계획 미리보기

자연어 입력 후 즉시 적용하지 않고 다음을 표시한다.

- 해석된 요청
- 대상 region 후보
- 적용 범위 후보: 현재 영역, 현재 페이지, 프로젝트 규칙
- 이전 값과 제안 값
- 실행할 `RevisionAction`
- 필요한 재번역·재렌더·재검증
- 경고와 예상 영향

대상이 모호하면 이미지 위에 후보를 표시하고 사용자 선택을 기다린다.

### 승인

- 승인
- 계획 수정
- 대상 변경
- 취소

프로젝트 규칙 변경은 별도 확인을 요구한다.

### 수정 결과

- 새 candidate preview를 표시한다.
- 검증 통과 후 새 revision으로 확정한다.
- 검증 실패 시 issue와 추가 액션을 표시한다.

## 8. Revision History

- revision 목록
- 사용자 지시와 승인 계획
- 변경 region과 before/after diff
- 검증 결과
- Undo, Redo
- 이전 revision 복원

기존 revision을 수정하지 않는다. 복원은 활성 revision 변경 또는 revert revision 생성으로 처리한다.

## 9. Project Context UI

탭:

- 캐릭터
- 호칭과 관계
- glossary
- 말투와 스타일
- 효과음 규칙
- 제안 대기

AI suggestion은 다음을 표시한다.

- 제안 값
- 근거 region
- confidence
- 적용 범위
- 승인, 수정 후 승인, 거절

승인 전에는 이후 페이지의 고정 규칙으로 사용하지 않는다.

## 10. Provider와 Privacy 설정

- 주 OCR과 보조 OCR
- 번역 provider
- 검증 provider
- fallback 순서
- visual mode
- 이미지 전송 동의
- 인페인팅 backend 순서

번역 provider와 검증 provider가 같으면 독립성 경고를 표시한다.

visual mode 활성화 전에 다음을 표시한다.

- 전송 provider
- 전송 대상: 전체 이미지, crop
- 목적: OCR 교정, 번역 검증, 최종 결과 검증

## 11. Output과 Save UI

- 실행 전 output 파일 경로 선택
- 완료 후 Save As
- 포맷과 품질 설정
- overwrite 확인
- 자동 저장 on/off

미해결 `error`/`critical` issue 또는 필수 사용자 확인 대기가 있으면 Save를 비활성화하고 issue 수와 위치를 표시한다. `warning`은 확인 후 일반 저장할 수 있다. 강제 저장은 경고 확인과 사유 입력 후 허용한다.

## 12. 상태와 오류

- 사용자 메시지는 실패 단계와 해결 가능한 원인을 설명한다.
- provider raw error와 secret을 표시하지 않는다.
- 작업 실패와 사용자 취소를 구분한다.
- 재개 가능한 checkpoint가 있으면 새 작업 시작 전에 안내한다.

## 13. 시각 디자인

- 도구형 데스크톱 UI
- 품질 상태와 이미지 비교가 장식보다 우선
- 과도한 gradient, glow, glass effect 금지
- severity 색상은 텍스트/아이콘과 함께 사용하여 색상만으로 의미를 전달하지 않음
- 작은 텍스트와 낮은 contrast 금지

권장 semantic 색상:

| 상태 | 색상 |
|---|---|
| 승인 | 녹색 |
| 검토 필요 | 황색 |
| critical | 적색 |
| 처리 중 | 청색 |
| 비활성 | 중립 회색 |
