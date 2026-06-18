# LangGraph Workflow 스펙

## 1. 공통 규칙

- graph node는 입력 state를 mutation하지 않고 state patch를 반환한다.
- 외부 provider 호출 node는 request fingerprint로 결과를 식별한다.
- node가 resume 시 다시 실행될 수 있으므로 외부 부작용은 idempotent해야 한다.
- 구조 검증 실패는 AI 판단으로 우회하지 않는다.
- 사용자 interrupt는 직렬화 가능한 `WorkflowInterruptPayload`만 전달한다.
- graph stream update는 GUI용 `JobSnapshot`으로 변환한다.
- 각 node는 시작·완료·재시도·실패 이벤트를 기록한다.

Checkpoint 저장 가능 상태:

- Workflow state와 interrupt payload는 `JSON-serializable` 값만 포함한다.
- Pydantic DTO는 checkpoint 저장 전 `model_dump(mode="json")` 결과로 표현 가능해야 한다.
- 저장 가능한 값은 str, int, float, bool, null, list, dict와 그 조합으로 제한한다.
- 파일이나 이미지 자체는 저장하지 않고 stable image reference 또는 safe local path string만 저장한다.
- 금지: `Path`, PIL image, NumPy array, raw provider payload, full prompt, API key, image/crop bytes.

공통 routing 결과:

```text
continue
retry_provider
use_fallback
retry_quality
interrupt_user
complete
fail
cancel
```

## 2. 전체 Orchestration

```text
RunImageTranslationUseCase
  1. validate JobDefinition
  2. load image
  3. run primary OCR
  4. normalize OCR
  5. invoke TranslationQualityGraph
  6. create inpaint and RenderPlan
  7. render image
  8. invoke ResultQualityGraph
  9. create FinalImageResult
 10. enable export gate
```

`RunImageTranslationUseCase`는 graph state를 직접 수정하지 않는다. graph 입출력을 domain DTO로 변환하고 진행 이벤트를 전달한다.

## 3. TranslationQualityGraph

### 3.1 Input

`TranslationWorkflowInput`:

- job ID, project ID, revision ID
- source image reference
- source/target language
- normalized regions
- primary OCR snapshots
- provider selection과 fallback 순서
- visual mode와 이미지 전송 동의
- 승인된 프로젝트 컨텍스트
- 번역 profile

### 3.2 State

`TranslationWorkflowState`의 핵심 필드:

```text
input
regions
ocr_candidates_by_region
ocr_decisions_by_region
reading_order_decision
page_context
context_suggestions
translation_candidates_by_region
approved_translations_by_region
reviews_by_region
translation_attempts_by_region
provider_attempts
issues
interrupt_payload
status
```

region별 map은 region ID를 key로 사용한다. 승인된 번역은 후보 목록과 분리한다.

### 3.3 Nodes

#### `prepare_page`

- region ID uniqueness, geometry, writing mode, reading order 입력을 검증한다.
- 프로젝트 설정과 provider capability를 검증한다.
- visual mode가 켜졌지만 이미지 전송 동의가 없으면 실패한다.

실패 조건:

- 잘못된 geometry
- 중복 region ID
- 지원하지 않는 language pair
- 필수 provider 설정 누락

#### `score_ocr_risk`

- 각 region의 OCR risk score와 이유를 계산한다.
- 보조 OCR 대상과 visual 교정 대상을 결정한다.

#### `cross_check_ocr`

- 위험 영역에만 보조 OCR adapter를 호출한다.
- 후보를 비교하고 `OCRDisagreement`를 생성한다.
- 자동 병합하지 않는다.

#### `correct_ocr_with_vision`

- visual mode가 활성화된 위험 영역만 reviewer에 전달한다.
- crop, 주변 region, OCR 후보를 사용한다.
- 교정 후보와 근거를 반환하며 원본 OCR을 덮어쓰지 않는다.

#### `resolve_ocr`

- 충분한 confidence의 OCR 후보를 승인한다.
- reading order 또는 전사가 불확실하면 사용자 검토 대상으로 표시한다.
- OCR 사용자 검토가 필요하면 번역 전에 interrupt한다.

#### `classify_page_layout`

- text role, writing mode, page/panel/group reading order를 확정한다.
- 루비와 본문 관계, 대화 그룹을 생성한다.

#### `build_page_context`

- 장면, 화자 후보, 감정, 인물 관계, 대화 흐름을 생성한다.
- 프로젝트 컨텍스트 변경 후보를 생성한다.
- 후보는 현재 workflow에서 참고할 수 있지만, 이후 페이지의 영속 규칙이 되려면 사용자 승인이 필요하다.

#### `translate_page`

- 승인 OCR, reading order, page context, 프로젝트 컨텍스트를 translator에 전달한다.
- 페이지 batch를 기본으로 호출한다.
- provider가 batch를 지원하지 않으면 adapter가 안정적인 순서로 분할한다.
- 이미 승인된 region은 재번역 요청에 포함하지 않는다.

#### `validate_translation_structure`

다음을 결정론적으로 검증한다.

- 요청과 결과 cardinality
- missing, duplicate, unknown region ID
- 빈 번역
- source/target language 불일치
- 허용되지 않은 provider output
- schema 및 길이 제한

실패 시 provider retry 또는 fallback 가능 오류가 아니면 작업을 중단한다.

#### `review_page_translation`

- 모든 미승인 번역을 페이지 단위로 검증한다.
- text 기반 검증은 항상 실행한다.
- visual mode가 활성화되면 전체 페이지와 모든 region crop을 포함한다.
- region별 rubric 점수, critical issue, evidence summary, 개선 지시를 반환한다.

#### `route_translation_decision`

region별 결정:

```text
approve:
  critical issue 없음
  total >= 4.0
  semantic_fidelity/completeness/character_voice >= 3.5

retry_quality:
  기준 미달
  translation_attempt < 2
  reviewer가 actionable feedback 제공

interrupt_user:
  critical issue 지속
  translation_attempt >= 2
  OCR/reading order 불확실
  reviewer 판정 자체가 불확실
```

#### `interrupt_for_translation_review`

사용자에게 다음을 전달한다.

- 문제 region과 이미지 위치
- 원문 OCR 후보
- 번역 후보 이력
- reviewer 점수와 근거 요약
- 추천 수정 방향
- 허용 액션

사용자 응답:

- 번역문 수정 후 재검증
- OCR 또는 reading order 수정 후 재번역
- 강제 승인
- 작업 취소

#### `finalize_translation`

- 승인 번역, unresolved issue, page context, context suggestion을 `TranslationWorkflowResult`로 반환한다.
- 승인되지 않은 결과를 렌더 입력으로 표시하지 않는다.

### 3.4 Edges

```text
START
 -> prepare_page
 -> score_ocr_risk
 -> cross_check_ocr       [위험 영역 존재]
 -> correct_ocr_with_vision [visual mode + 교정 대상]
 -> resolve_ocr
 -> interrupt_for_translation_review [OCR 검토 필요]
 -> classify_page_layout
 -> build_page_context
 -> translate_page
 -> validate_translation_structure
 -> review_page_translation
 -> route_translation_decision
    -> translate_page [재번역 대상 존재]
    -> interrupt_for_translation_review [사용자 검토 필요]
    -> finalize_translation [모두 승인 또는 강제 승인]
 -> END
```

## 4. ResultQualityGraph

### 4.1 Input

- 승인된 번역 결과
- 원본 이미지와 inpainted image reference
- rendered image reference
- regions와 RenderPlan
- visual mode
- inpainting/rendering backend capability

### 4.2 Nodes

#### `validate_render_structure`

- 누락 region, 잘못된 mapping, writing mode, glyph 지원을 검증한다.

#### `inspect_layout`

- clipping, overlap, 최소 글자 크기, contrast, line spacing을 검사한다.

#### `inspect_inpainting`

- mask coverage와 원문 잔존 가능성을 결정론적으로 검사한다.
- visual mode에서 reviewer가 잔상과 배경 훼손을 평가한다.

#### `review_final_image`

- visual mode에서 페이지 전체 결과와 원본을 비교한다.
- region별 및 page-level 시각 issue를 반환한다.

#### `plan_result_corrections`

issue를 허용된 correction으로 변환한다.

- RenderPlan 수정
- mask 수정
- inpainting backend escalation
- rerender

#### `apply_result_corrections`

- correction plan을 application service에 전달한다.
- 새 rendered image reference와 attempt를 기록한다.

#### `route_result_decision`

- issue 없음: finalize
- 자동 수정 가능하고 attempt < 2: correction loop
- 그 외: 사용자 interrupt

#### `interrupt_for_result_review`

원본, inpainted, rendered preview와 issue 위치를 사용자에게 제공한다.

#### `finalize_result`

승인된 이미지 reference, RenderPlan, unresolved issue를 반환한다.

### 4.3 Edges

```text
START
 -> validate_render_structure
 -> inspect_layout
 -> inspect_inpainting
 -> review_final_image [visual mode]
 -> plan_result_corrections
 -> apply_result_corrections [수정 가능]
 -> inspect_layout
 -> route_result_decision
    -> finalize_result
    -> interrupt_for_result_review
 -> END
```

자동 수정 attempt는 최대 2회다.

## 5. NaturalRevisionGraph

### 5.1 목적

사용자의 자연어 수정 지시를 임의 실행하지 않고, 허용된 변경 계획으로 변환하여 승인·적용·재검증한다.

### 5.2 허용 Action

```text
replace_translation
adjust_tone
adjust_localization
propose_glossary_change
propose_character_rule
change_font
change_font_size
change_weight
change_alignment
change_color
change_outline
change_writing_mode
move_region
resize_region
retry_inpainting
retry_translation
retry_quality_review
```

목록에 없는 action은 거절한다.

### 5.3 Nodes

#### `parse_revision_intent`

- 자연어에서 요청 action, constraint, 참조 표현을 추출한다.
- 자유 도구 호출이나 파일 접근 요청을 거절한다.

#### `resolve_target_regions`

- 현재 선택 region을 우선한다.
- “첫 말풍선”, “오른쪽 위 대사”, “모든 효과음”을 geometry와 reading order로 해석한다.
- 여러 후보가 있으면 사용자 선택을 요구한다.

#### `determine_rule_scope`

적용 범위 후보:

- current region
- current page
- project rule

프로젝트 규칙 변경은 별도 승인을 요구한다.

#### `create_revision_plan`

다음을 포함하는 immutable plan을 생성한다.

- target
- action
- before/after proposal
- affected revisions와 regions
- 필요한 재검증
- 예상 위험과 경고

#### `interrupt_for_plan_approval`

사용자가 계획을 승인, 수정, 거절한다.

#### `apply_revision`

- 승인된 action만 적용한다.
- 기존 revision을 변경하지 않고 새 candidate revision을 생성한다.

#### `revalidate_revision`

- 번역 변경은 TranslationQualityGraph의 관련 단계로 전달한다.
- 시각 변경은 ResultQualityGraph로 전달한다.
- 프로젝트 규칙 변경은 승인 repository에 저장하고 현재 결과를 재검증한다.

#### `commit_revision`

- 모든 필수 검증이 완료된 candidate를 새 revision으로 확정한다.

### 5.4 Edges

```text
START
 -> parse_revision_intent
 -> resolve_target_regions
 -> interrupt_for_target_selection [모호함]
 -> determine_rule_scope
 -> create_revision_plan
 -> interrupt_for_plan_approval
    -> END [거절]
    -> apply_revision [승인]
 -> revalidate_revision
 -> interrupt_for_revision_review [검증 실패]
 -> commit_revision
 -> END
```

## 6. Provider Retry와 Fallback

Provider retry:

- transient network, rate limit, retryable server error만 최대 3회
- exponential backoff와 jitter 사용
- schema 오류는 같은 응답을 재파싱하지 않고 provider 재호출 또는 fallback 판단

Fallback:

- 사용자가 설정한 순서가 있을 때만 사용
- capability와 language pair가 호환되는 provider만 선택
- provider 변경 사실을 사용자 상태와 품질 기록에 표시

품질 재번역 attempt와 provider retry attempt는 별도로 계산한다.

## 7. Progress Mapping

진행률은 감소하지 않는다. 기본 단계 가중치:

```text
입력/OCR              0.00 - 0.18
OCR 교차 검증         0.18 - 0.28
페이지 분석           0.28 - 0.38
번역                  0.38 - 0.58
번역 품질 검증        0.58 - 0.70
인페인팅              0.70 - 0.80
렌더링                0.80 - 0.88
결과 품질 검증        0.88 - 0.97
저장 준비             0.97 - 1.00
```

재시도 시 progress를 되돌리지 않고 stage message에 attempt를 표시한다. interrupt 상태에서는 현재 progress를 유지한다.
