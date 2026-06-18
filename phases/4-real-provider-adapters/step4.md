# Step 4: grok-adapter

## 읽어야 할 파일

먼저 아래 파일들을 읽고 Grok translator/reviewer 계약을 확인하라:

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

Grok adapter를 translator와 reviewer capability에 맞게 구현하라.

1. Grok config와 model ID validation을 구현하라.
   - model ID는 명시적으로 설정한다.
   - credential과 provider raw error는 redaction한다.
2. structured output 변환과 error mapping을 구현하라.
   - batch cardinality, duplicate region ID, unknown region ID를 AI review 전에 실패시킨다.
   - timeout, rate limit, provider 5xx를 retryable 후보로 분류한다.
3. visual input gating을 구현하라.
   - provider와 선택 model capability가 visual input을 지원할 때만 visual request를 허용한다.
   - visual mode off 또는 동의 없음 상태에서는 image reference와 crop을 제거한다.
4. unit contract test와 `provider_smoke` test를 추가하라.
   - 기본 test는 offline fixture와 mock client로 실행한다.
   - 실제 Grok 호출은 `provider_smoke` marker에서만 실행하고 credential 없으면 skip한다.

## Acceptance Criteria

```bash
uv run pytest -q tests/unit
uv run pytest -m provider_smoke
python3 scripts/validate_project.py
```

## 검증 절차

1. Grok adapter가 provider protocol과 security contract를 만족하는지 확인한다.
2. reviewer output이 최종 번역문을 직접 생성하지 않는지 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "Grok translator/reviewer adapter 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- Grok raw payload, full prompt, credential 값을 저장하지 마라. Reason: 보안과 개인정보 계약 위반이다.
- provider output의 cardinality 검증을 생략하지 마라. Reason: region mapping은 결정론적이어야 한다.
- 사용자 설정 없는 provider fallback을 실행하지 마라. Reason: 비용과 결과 일관성에 영향을 준다.
