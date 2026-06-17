# Step 1: translation-quality-graph

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/WORKFLOWS.md`
- `/docs/QUALITY.md`
- `/docs/PROMPT_CONTRACTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/PROVIDERS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/2-workflow-provider-runtime/step0.md`
- `/src/image_translator/workflows/translation_quality.py`
- `/src/image_translator/providers/`
- `/src/image_translator/services/`

## 작업

TranslationQualityGraph를 문서 계약에 맞춰 실제 node/edge 단위로 완성하라.

1. state와 input/output DTO를 구현 또는 보강하라.
   - 권장 파일: `/src/image_translator/workflows/translation_quality.py`
   - `TranslationWorkflowInput`, `TranslationWorkflowState`, `TranslationWorkflowResult`를 serializable immutable boundary로 유지하라.
2. `docs/WORKFLOWS.md`의 node를 구현하라.
   - `prepare_page`
   - `score_ocr_risk`
   - `cross_check_ocr`
   - `correct_ocr_with_vision`
   - `resolve_ocr`
   - `classify_page_layout`
   - `build_page_context`
   - `translate_page`
   - `validate_translation_structure`
   - `review_page_translation`
   - `route_translation_decision`
   - `interrupt_for_translation_review`
   - `finalize_translation`
3. routing 규칙을 구현하라.
   - critical issue 없음, total >= 4.0, 핵심 rubric >= 3.5이면 approve.
   - 기준 미달이고 `translation_attempt < 2`이며 actionable feedback이 있으면 retry.
   - 그 외 사용자 interrupt를 생성하라.
   - visual mode off에서는 image/crop reference를 provider request에 포함하지 마라.
4. graph test를 추가하라.
   - 권장 파일: `/tests/unit/workflows/test_translation_quality_graph.py`
   - 권장 파일: `/tests/integration/test_translation_quality_graph_mock.py`
   - missing/duplicate/unknown region ID가 AI review 전에 실패하는지 검증하라.
   - 승인된 region은 다른 region 재번역 중 변경되지 않는지 검증하라.
   - 최대 2회 재번역 후 문제 region만 interrupt되는지 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "TranslationQualityGraph node/edge/routing 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- graph node에서 입력 state를 mutation하지 마라. Reason: LangGraph resume과 audit을 위해 state patch/new state만 반환해야 한다.
- reviewer가 최종 번역문을 생성하게 하지 마라. Reason: reviewer는 판정, 근거, 개선 지시만 반환한다.
- 결정론적 cardinality와 schema 검증을 LLM에 맡기지 마라. Reason: provider output은 신뢰할 수 없는 입력이다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
