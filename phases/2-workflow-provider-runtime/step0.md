# Step 0: provider-runtime-config

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/PROVIDERS.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/PROJECT_CONTEXT.md`
- `/docs/WORKFLOWS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/0-core-vertical-slice/step3.md`
- `/src/image_translator/providers/`
- `/src/image_translator/config/`

## 작업

provider runtime 설정, registry, retry/fallback 정책을 구현하라.

1. typed settings를 구현하라.
   - 권장 파일: `/src/image_translator/config/settings.py`
   - provider ID, model ID, timeout, retry, fallback order, visual mode default, image transmission consent default를 명시하라.
   - API key 값은 환경변수 또는 ignored user config에서만 읽도록 인터페이스를 설계하라.
2. provider registry를 구현하라.
   - 권장 파일: `/src/image_translator/providers/registry.py`
   - adapter capability와 requested job settings를 검증하라.
   - 번역 provider와 reviewer provider가 같으면 warning issue를 반환하라.
   - fallback은 사용자가 설정한 순서가 있을 때만 선택하라.
3. retry/fallback classifier를 구현하라.
   - 권장 파일: `/src/image_translator/providers/retry.py`
   - retryable network/rate limit/server error와 non-retryable auth/capability/schema/consent error를 분리하라.
   - provider retry attempt와 품질 재번역 attempt를 별도 카운트로 유지하라.
4. 테스트를 추가하라.
   - 권장 파일: `/tests/unit/config/test_settings.py`
   - 권장 파일: `/tests/unit/providers/test_registry.py`
   - 권장 파일: `/tests/unit/providers/test_retry_policy.py`

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "typed provider settings, registry, retry/fallback policy 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 사용자 설정 없는 provider fallback을 실행하지 마라. Reason: provider 변경은 비용, 개인정보, 결과 일관성에 영향을 준다.
- API key 값을 source, committed config, logs, checkpoint에 저장하지 마라. Reason: secret은 환경변수 또는 ignored user config에서만 읽어야 한다.
- model ID를 provider의 latest alias에 의존하지 마라. Reason: release 문서상 provider/model version은 추적 가능해야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
