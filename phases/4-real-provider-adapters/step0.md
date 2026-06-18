# Step 0: provider-sdk-and-fixtures

## 읽어야 할 파일

먼저 아래 파일들을 읽고 provider boundary와 release 계약을 확인하라:

- `/AGENTS.md`
- `/docs/PROVIDERS.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/PROMPT_CONTRACTS.md`
- `/docs/TESTING.md`
- `/docs/RELEASE.md`
- `/docs/ARCHITECTURE.md`
- `/phases/0-core-vertical-slice/step3.md`
- `/phases/2-workflow-provider-runtime/step0.md`
- `/pyproject.toml`
- `/uv.lock`

## 작업

실제 provider adapter 구현을 위한 SDK dependency, offline fixture, smoke test 기반을 준비하라.

1. DeepL, OpenAI, Gemini, Grok SDK 도입 범위를 확정하라.
   - SDK를 import하는 코드는 `providers` adapter 내부에만 둔다.
   - dependency 추가 시 같은 변경에서 `pyproject.toml`, `uv.lock`, 테스트, 관련 문서를 갱신하라.
   - provider별 optional extra나 dependency group을 도입한다면 release 설치 명령과 validation 문서도 함께 갱신하라.
2. provider contract fixture를 추가하라.
   - credential 없이 실행 가능한 schema conversion fixture를 우선 둔다.
   - raw provider payload, 전체 prompt, API key, 이미지 bytes를 fixture나 snapshot에 저장하지 마라.
3. `provider_smoke` marker 정책을 명확히 적용하라.
   - 실제 외부 호출은 credential이 있을 때만 실행하고, 없으면 skip한다.
   - 기본 `python3 scripts/validate_project.py` gate는 외부 유료 provider를 호출하지 않는다.

## Acceptance Criteria

```bash
uv run pytest -q tests/unit
uv run pytest -m provider_smoke
python3 scripts/validate_project.py
```

## 검증 절차

1. credential 없는 환경에서 unit test와 default validation이 외부 provider 없이 통과하는지 확인한다.
2. credential 있는 환경에서 `provider_smoke` marker가 명시적으로 실행되는지 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "provider SDK dependency와 fixture 기반 준비"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 기본 validation에서 DeepL, OpenAI, Gemini, Grok 실제 API를 호출하지 마라. Reason: provider smoke는 credential이 있을 때 별도 marker로 실행해야 한다.
- API key, raw provider payload, 전체 prompt, 이미지 bytes를 저장하지 마라. Reason: 보안과 개인정보 계약 위반이다.
- provider SDK 타입을 `providers` 밖으로 노출하지 마라. Reason: 외부 SDK 변경이 domain과 workflow에 전파되면 안 된다.
