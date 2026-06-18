# Step 1: deepl-translator-adapter

## 읽어야 할 파일

먼저 아래 파일들을 읽고 DeepL text-only translator 계약을 확인하라:

- `/AGENTS.md`
- `/docs/PROVIDERS.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/PROMPT_CONTRACTS.md`
- `/docs/TESTING.md`
- `/phases/4-real-provider-adapters/step0.md`
- `/src/image_translator/providers/`
- `/tests/`

## 작업

DeepL translator adapter를 typed provider boundary 뒤에 구현하라.

1. DeepL adapter config validation을 구현하라.
   - API key는 환경변수 또는 ignored user config에서만 읽는다.
   - 오류 메시지는 환경변수 이름을 표시할 수 있지만 값을 포함하지 않는다.
2. DeepL text translation을 domain DTO로 변환하라.
   - text와 context hint만 전달한다.
   - visual input capability는 `false`로 선언한다.
   - 요청 region마다 정확히 하나의 candidate를 반환하고 cardinality mismatch는 실패시킨다.
3. retryable/non-retryable error mapping을 추가하라.
   - timeout, rate limit, 일시적 5xx는 retryable로 분류한다.
   - credential, 권한, language pair 오류는 non-retryable로 분류한다.
4. unit contract test와 `provider_smoke` test를 추가하라.
   - credential 없는 기본 test는 mock transport 또는 fixture로 실행한다.
   - 실제 DeepL 호출은 `provider_smoke` marker에서만 실행하고 credential 없으면 skip한다.

## Acceptance Criteria

```bash
uv run pytest -q tests/unit
uv run pytest -m provider_smoke
python3 scripts/validate_project.py
```

## 검증 절차

1. DeepL adapter가 provider protocol과 capability contract를 만족하는지 확인한다.
2. visual mode가 켜져도 DeepL에는 image reference나 crop이 전달되지 않는지 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "DeepL translator adapter 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- DeepL adapter에서 이미지나 crop을 전송하지 마라. Reason: DeepL은 text-only translator로 다룬다.
- credential 값을 로그, fixture, snapshot, error에 기록하지 마라. Reason: secret redaction 계약 위반이다.
- reviewer 책임을 DeepL translator에 넣지 마라. Reason: reviewer는 판정과 근거만 반환하는 별도 역할이다.
