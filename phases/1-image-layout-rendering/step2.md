# Step 2: reading-order-layout

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/OCR_LAYOUT.md`
- `/docs/WORKFLOWS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/QUALITY.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/1-image-layout-rendering/step1.md`
- `/src/image_translator/services/ocr_normalization.py`
- `/src/image_translator/services/ocr_risk.py`

## 작업

혼합 writing mode, 일본어 `vertical_rl`, text role, ruby 관계를 다루는 layout analysis service를 구현하라.

1. reading order service를 구현하라.
   - 권장 파일: `/src/image_translator/services/layout_analysis.py`
   - `vertical_rl`은 열 내부 상->하, 열 사이 우->좌 순서를 보존하라.
   - `horizontal_ltr`, `horizontal_rtl`, `vertical_lr`, `rotated`를 명시적으로 처리하라.
   - confidence가 낮거나 후보가 충돌하면 `ReadingOrderUncertainError` 또는 review-required result로 표현하라.
2. text role과 ruby 관계 classification 기반을 추가하라.
   - 권장 파일: `/src/image_translator/services/text_role_classifier.py`
   - `dialogue`, `narration`, `sound_effect`, `sign`, `decorative`, `ruby`, `unknown`을 지원하라.
   - ruby region은 `ruby_target_region_id`를 통해 본문과 연결하고, 연결 불확실성은 자동 확정하지 마라.
3. 테스트 fixture를 추가하라.
   - 권장 파일: `/tests/unit/services/test_layout_analysis.py`
   - 권장 파일: `/tests/unit/services/test_text_role_classifier.py`
   - vertical two-column ordering, mixed horizontal/vertical page, rotated sound effect, ruby target link, ambiguous order interrupt를 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "reading order, text role, ruby layout analysis 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 좌표 정렬만으로 최종 reading order를 확정하지 마라. Reason: writing mode, panel/group, 대화 흐름 신호를 함께 고려해야 한다.
- 불확실한 reading order를 자동 승인하지 마라. Reason: reading order 오류는 번역 문맥 왜곡을 만든다.
- 연결되지 않은 작은 텍스트를 자동으로 ruby로 확정하지 마라. Reason: ruby 관계가 불확실하면 사용자 검토 대상이어야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
