# Step 2: result-quality-graph

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/WORKFLOWS.md`
- `/docs/QUALITY.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/PROVIDERS.md`
- `/docs/EXPORT.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/2-workflow-provider-runtime/step1.md`
- `/src/image_translator/workflows/result_quality.py`
- `/src/image_translator/services/result_validation.py`
- `/src/image_translator/services/rendering.py`
- `/src/image_translator/services/inpainting.py`

## 작업

ResultQualityGraph를 문서 계약에 맞춰 구현하라.

1. state와 input/output DTO를 구현 또는 보강하라.
   - 권장 파일: `/src/image_translator/workflows/result_quality.py`
   - `ResultQualityInput`, `ResultQualityState`, `FinalImageResult`를 serializable boundary로 유지하라.
2. `docs/WORKFLOWS.md`의 node를 구현하라.
   - `validate_render_structure`
   - `inspect_layout`
   - `inspect_inpainting`
   - `review_final_image`
   - `plan_result_corrections`
   - `apply_result_corrections`
   - `route_result_decision`
   - `interrupt_for_result_review`
   - `finalize_result`
3. 자동 수정 loop를 구현하라.
   - 자동 수정 attempt는 최대 2회다.
   - correction은 RenderPlan 수정, mask 수정, backend escalation, rerender로 제한한다.
   - unresolved `error`/`critical` issue 또는 필수 사용자 확인 대기가 있으면 export eligibility를 false로 유지한다.
4. 테스트를 추가하라.
   - 권장 파일: `/tests/unit/workflows/test_result_quality_graph.py`
   - 권장 파일: `/tests/integration/test_result_quality_graph_mock.py`
   - clipping, overlap, glyph, visual mode off confirmation, max correction attempt, export blocked를 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "ResultQualityGraph correction loop와 export eligibility 연결 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 최종 이미지 자동 수정 attempt를 2회를 초과하게 하지 마라. Reason: 품질 문서가 자동 수정 한계를 명시한다.
- unresolved blocking issue가 있는 결과를 일반 export eligible로 표시하지 마라. Reason: 품질 실패가 정상 결과처럼 저장되면 안 된다.
- AI 시각 검사가 결정론적 render structure 실패를 승인하게 하지 마라. Reason: 구조 검증 실패는 AI 판단으로 우회할 수 없다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
