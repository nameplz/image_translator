# Step 3: inpainting-rendering

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/QUALITY.md`
- `/docs/OCR_LAYOUT.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/WORKFLOWS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/1-image-layout-rendering/step2.md`
- `/src/image_translator/domain/`
- `/src/image_translator/services/layout_analysis.py`

## 작업

결과 이미지 생성을 위한 local inpainting/rendering service와 deterministic layout validation을 구현하라.

1. inpainting request/result 모델과 local backend를 구현하라.
   - 권장 파일: `/src/image_translator/services/inpainting.py`
   - 권장 파일: `/src/image_translator/providers/local_inpainting.py`
   - MVP 초기 backend는 simple mask fill 또는 OpenCV 기반 local backend로 충분하다.
   - backend escalation hook은 인터페이스만 두고 user config 기반 순서를 이후 step에서 연결하라.
2. rendering service를 구현하라.
   - 권장 파일: `/src/image_translator/services/rendering.py`
   - `RenderPlan`을 실행하고 `RenderedRegion`과 output image reference를 반환하라.
   - 목표 언어 표준 writing mode 기본값을 적용하라.
   - font fallback, glyph support check, contrast check를 deterministic하게 표현하라.
3. result layout validation을 구현하라.
   - 권장 파일: `/src/image_translator/services/result_validation.py`
   - clipping, overlap, minimum font size, contrast, unsupported glyph, missing region을 검사하라.
4. 테스트를 추가하라.
   - 권장 파일: `/tests/unit/services/test_rendering.py`
   - 권장 파일: `/tests/unit/services/test_result_validation.py`
   - 권장 파일: `/tests/unit/providers/test_local_inpainting.py`

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "local inpainting, rendering, deterministic result validation 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- rendering backend가 번역문을 변경하게 하지 마라. Reason: rendering은 RenderPlan 실행만 담당한다.
- 결정론적 layout validation 실패를 AI 시각 검사로 무시하지 마라. Reason: deterministic 검사와 AI 판단은 권한이 분리되어 있다.
- visual mode 동의 없이 외부 provider에 이미지나 crop을 전달하지 마라. Reason: 이미지 전송 동의는 필수 개인정보 경계다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
