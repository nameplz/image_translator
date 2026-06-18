# Step 5: provider-smoke-release-gate

## 읽어야 할 파일

먼저 아래 파일들을 읽고 final MVP release gate 계약을 확인하라:

- `/AGENTS.md`
- `/docs/RELEASE.md`
- `/docs/TESTING.md`
- `/docs/PROVIDERS.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/ARCHITECTURE.md`
- `/phases/3-gui-export-release/step4.md`
- `/phases/4-real-provider-adapters/index.json`
- `/.harness/validation.json`
- `/scripts/validate_project.py`
- `/scripts/run_gui_tests.py`

## 작업

DeepL, OpenAI, Gemini, Grok 실제 provider adapter가 준비된 뒤 final MVP release gate를 완성하라.

1. provider smoke suite를 명시적으로 분리하라.
   - marker: `provider_smoke`
   - credential이 없으면 skip하고, credential 값은 출력하지 않는다.
   - smoke 결과는 provider ID, model ID, capability, schema conversion, redaction 결과만 기록한다.
2. final MVP release gate를 문서와 validation 절차에 연결하라.
   - 기본 gate: `python3 scripts/validate_project.py`
   - GUI gate: `python3 scripts/run_gui_tests.py`
   - provider smoke: `uv run pytest -m provider_smoke`
   - packaging smoke와 installed wheel smoke를 release checklist에 반영한다.
3. release 결과 기록 형식을 정하라.
   - provider와 model version
   - smoke 실행 일시와 skip 사유
   - dependency audit 결과
   - known issue와 미지원 기능

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
python3 scripts/run_gui_tests.py
uv run pytest -m provider_smoke
```

## 검증 절차

1. credential 없는 환경에서 default validation이 외부 provider 없이 통과하는지 확인한다.
2. credential 있는 release 환경에서 DeepL, OpenAI, Gemini, Grok smoke가 명시적으로 실행되는지 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "real provider smoke와 final MVP release gate 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- credential 없이 provider smoke 실패를 release failure로 기록하지 마라. Reason: credential 없는 개발 환경에서는 skip이 정상 동작이다.
- 기본 validation에 외부 유료 provider 호출을 포함하지 마라. Reason: 기본 gate는 deterministic해야 한다.
- critical vulnerability나 secret 노출을 known issue로 우회하지 마라. Reason: release gate 차단 조건이다.
