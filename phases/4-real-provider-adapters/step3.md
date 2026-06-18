# Step 3: gemini-adapter

## 읽어야 할 파일

먼저 아래 파일들을 읽고 Gemini translator/reviewer 계약을 확인하라:

- `/AGENTS.md`
- `/docs/PROVIDERS.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/PROMPT_CONTRACTS.md`
- `/docs/QUALITY.md`
- `/docs/TESTING.md`
- `/phases/4-real-provider-adapters/step0.md`
- `/src/image_translator/providers/`
- `/tests/`

## 작업

Gemini adapter를 translator, reviewer, visual-capable provider로 구현하라.

1. Gemini config와 model ID validation을 구현하라.
   - model ID는 명시적으로 설정하고 provider의 latest alias에 의존하지 않는다.
   - credential 오류는 redaction된 user-facing issue로 변환한다.
2. structured output과 schema repair 정책을 구현하라.
   - 첫 schema parse 실패는 계약상 허용된 correction request 한 번으로 제한한다.
   - 반복 실패는 provider error로 분류하고 fallback은 사용자 설정이 있을 때만 수행한다.
3. visual input gating을 구현하라.
   - visual mode와 이미지 전송 동의가 없으면 page image와 crop을 전달하지 않는다.
   - visual capability와 request size 제한을 사전에 검증한다.
4. unit contract test와 `provider_smoke` test를 추가하라.
   - 기본 test는 offline fixture와 mock client로 실행한다.
   - 실제 Gemini 호출은 `provider_smoke` marker에서만 실행하고 credential 없으면 skip한다.

## Acceptance Criteria

```bash
uv run pytest -q tests/unit
uv run pytest -m provider_smoke
python3 scripts/validate_project.py
```

## 검증 절차

1. Gemini adapter가 translator와 reviewer 역할을 분리하는지 확인한다.
2. visual mode off에서 이미지 reference가 provider request에 포함되지 않는지 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "Gemini translator/reviewer adapter 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- Gemini response의 전체 reasoning이나 raw payload를 UI, 로그, fixture에 저장하지 마라. Reason: 개인정보와 prompt 계약 위반이다.
- reviewer가 최종 번역문을 직접 생성하게 하지 마라. Reason: 생성과 평가 책임을 분리해야 한다.
- visual consent 없이 이미지나 crop을 전달하지 마라. Reason: 이미지 전송 동의는 필수 개인정보 경계다.
