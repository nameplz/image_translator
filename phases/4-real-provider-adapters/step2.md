# Step 2: openai-adapter

## 읽어야 할 파일

먼저 아래 파일들을 읽고 OpenAI translator/reviewer 계약을 확인하라:

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

OpenAI adapter를 translator와 reviewer capability에 맞게 구현하라.

1. OpenAI config와 model ID validation을 구현하라.
   - model ID는 명시적으로 설정하고 provider의 latest alias에 의존하지 않는다.
   - API key는 환경변수 또는 ignored user config에서만 읽는다.
2. structured output 변환을 구현하라.
   - translator output은 region ID cardinality와 schema를 결정론적으로 검증한다.
   - reviewer output은 판정, 근거, 개선 지시만 반환하고 최종 번역문을 직접 생성하지 않는다.
3. visual input gating을 구현하라.
   - visual mode, 사용자 이미지 전송 동의, capability가 모두 true일 때만 image reference나 crop을 전달한다.
   - visual mode off에서는 text-only request fingerprint를 사용한다.
4. unit contract test와 `provider_smoke` test를 추가하라.
   - 기본 test는 offline fixture와 mock client로 실행한다.
   - 실제 OpenAI 호출은 `provider_smoke` marker에서만 실행하고 credential 없으면 skip한다.

## Acceptance Criteria

```bash
uv run pytest -q tests/unit
uv run pytest -m provider_smoke
python3 scripts/validate_project.py
```

## 검증 절차

1. OpenAI translator/reviewer capability가 `docs/PROVIDERS.md`와 일치하는지 확인한다.
2. visual consent 없이 이미지나 crop이 요청에 포함되지 않는지 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "OpenAI translator/reviewer adapter 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- OpenAI raw payload나 full prompt를 checkpoint, 로그, fixture에 저장하지 마라. Reason: 보안과 개인정보 계약 위반이다.
- schema validation을 LLM 출력에 맡기지 마라. Reason: provider output은 신뢰할 수 없는 외부 입력이다.
- 사용자 설정 없는 fallback을 실행하지 마라. Reason: provider 변경은 비용과 개인정보 경계에 영향을 준다.
