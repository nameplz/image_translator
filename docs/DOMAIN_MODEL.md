# Domain Model

## 1. 공통 원칙

- 안정적인 경계에는 Pydantic 2 immutable model 또는 frozen dataclass를 사용한다.
- 모델은 provider SDK 타입과 GUI 타입을 포함하지 않는다.
- 원본 snapshot과 승인 결과는 mutation하지 않는다.
- collection은 가능한 경우 tuple과 immutable mapping으로 표현한다.
- 외부 입력은 model validation을 통과한 뒤 domain에 들어온다.

## 2. 식별자

모든 ID는 비어 있지 않은 문자열이며 생성 후 변경하지 않는다.

```text
ProjectId
JobId
PageId
RegionId
RevisionId
WorkflowThreadId
ProviderRequestId
```

region ID는 page 내에서 유일하다. job, thread, revision은 전역적으로 유일하다.

## 3. Geometry와 Layout

### `Point`

- `x: float`
- `y: float`

### `Polygon`

- `points: tuple[Point, ...]`
- 최소 3개 point
- 양수 면적

### `RotatedBoundingBox`

- center, width, height, rotation
- width와 height는 양수

### `WritingMode`

- `horizontal_ltr`
- `horizontal_rtl`
- `vertical_rl`
- `vertical_lr`
- `rotated`
- `unknown`

### `TextOrientation`

- `upright`
- `rotated_90_cw`
- `rotated_90_ccw`
- `arbitrary_angle`

### `ReadingOrder`

- `page_index: int`
- `group_index: int`
- `item_index: int`
- `confidence: float`
- `alternatives: tuple[ReadingOrderCandidate, ...]`

## 4. OCR Model

### `RawOCRRegion`

- provider가 반환한 원본 snapshot
- region ID, raw text, confidence
- polygon 또는 rotated bbox
- writing mode 후보와 confidence
- provider metadata의 안전한 요약

`RawOCRRegion`은 후속 서비스에 직접 전달하지 않는다.

### `OCRCandidate`

- region ID
- text
- language candidate
- provider ID
- confidence
- evidence summary

### `OCRDisagreement`

- region ID
- candidate IDs
- disagreement type
- severity
- review recommendation

### `NormalizedTextRegion`

- region ID
- approved source text
- non-null geometry
- source language
- writing mode와 orientation
- reading order
- text role
- ruby target ID
- OCR provenance

## 5. Context Model

### `PageContext`

- scene summary
- reading order notes
- dialogue groups
- speaker candidates
- region contexts

### `RegionContext`

- region ID
- speaker candidate
- addressee candidate
- tone
- emotion
- object references
- translation hint
- confidence

### `ProjectContext`

- approved glossary
- approved character profiles
- approved style rules
- version

### `ContextSuggestion`

- proposed type와 value
- evidence regions
- target scope
- confidence
- approval status

승인되지 않은 suggestion은 이후 page의 고정 규칙으로 사용할 수 없다.

## 6. Translation Model

### `TranslationRequest`

- region ID
- source text
- source/target language
- text role
- writing mode
- page context reference
- region context
- approved project context
- reviewer feedback
- optional image/crop reference

### `TranslationCandidate`

- region ID
- translated text
- provider ID와 model ID
- attempt
- request fingerprint
- created revision

### `TranslationResult`

- region ID
- approved translated text
- source/target language
- selected candidate ID
- approval status
- review reference

번역 결과는 region마다 정확히 하나만 승인될 수 있다.

## 7. 품질 Model

### `QualitySeverity`

- `info`
- `warning`
- `error`
- `critical`

### `QualityIssue`

- stable issue code
- severity
- scope
- region IDs
- summary
- evidence references
- recommended action
- resolved status

### `QualityEvidence`

- evidence type
- safe summary
- source region 또는 image reference
- confidence

### `RegionReview`

- region ID
- rubric scores
- total score
- critical issues
- non-critical issues
- evidence summary
- improvement instruction
- decision

### `PageReview`

- region reviews
- page-level issues
- context consistency summary
- provider/model/prompt contract version

## 8. Render Model

### `RenderStyle`

- font family
- weight
- size
- color
- outline
- alignment
- line spacing
- letter spacing
- writing mode

### `RenderPlan`

- region ID
- geometry
- translated text
- style
- overflow policy
- source style evidence

### `RenderedRegion`

- region ID
- applied plan
- output geometry
- deterministic validation result

### `ResultQualityReview`

- rendered image reference
- region issues
- page issues
- correction recommendations
- decision

## 9. Revision Model

### `RevisionAction`

허용 action은 [WORKFLOWS.md](WORKFLOWS.md)에 정의된 목록으로 제한한다.

### `RevisionTarget`

- resolved region IDs
- target scope
- resolution evidence
- ambiguity status

### `RevisionPlan`

- plan ID
- base revision ID
- normalized user instruction
- target
- actions
- before/after proposal
- required validation
- warnings
- approval status

### `RevisionRecord`

- revision ID
- parent revision ID
- approved plan
- domain diff
- validation results
- created time
- approval record

완료된 revision은 변경하지 않는다. Undo/Redo는 활성 revision pointer를 변경하거나 새 revert revision을 생성한다.

## 10. Job과 Progress Model

### `JobDefinition`

- job ID
- project ID
- input path
- requested output path
- source/target language
- provider selection
- fallback order
- visual mode
- image transmission consent
- processing profile

### `JobStatus`

```text
queued
preparing
ocr_running
analyzing_layout
translating
reviewing_translation
waiting_for_user
inpainting
rendering
reviewing_result
ready_to_export
exporting
complete
failed
cancelled
```

### `JobSnapshot`

- job ID
- status
- monotonic progress
- stage
- user-facing message
- cancel availability
- interrupt summary
- error summary

## 11. Workflow Model

### `WorkflowInterruptPayload`

- interrupt type
- job/thread/revision ID
- affected region IDs
- issue summaries
- preview references
- allowed actions
- recommended action

### `TranslationWorkflowResult`

- approved translation results
- unresolved issues
- page context
- context suggestions
- audit references

### `FinalImageResult`

- approved image reference
- render plans
- unresolved issues
- approval status
- export eligibility

## 12. Export Model

### `ExportRequest`

- final image result reference
- output path
- format options
- overwrite confirmation
- forced export confirmation

### `ForceApprovalRecord`

- user-visible issue list
- reason
- timestamp
- affected revision

## 13. 불변 조건

- normalization 이후 geometry는 non-null이다.
- region ID는 page 내에서 유일하다.
- 원본 OCR snapshot은 변경하지 않는다.
- 승인 번역과 후보 번역은 분리한다.
- reviewer 결과는 번역 결과로 사용할 수 없다.
- 승인되지 않은 프로젝트 컨텍스트는 이후 page에 적용하지 않는다.
- 자연어 수정은 승인된 RevisionPlan 없이 적용할 수 없다.
- 완료 revision은 mutation하지 않는다.
- 미해결 `error`/`critical` issue 또는 필수 사용자 확인 대기가 있는 결과는 일반 export 대상이 아니다.
