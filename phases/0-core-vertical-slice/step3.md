# Step 3: provider-contracts-mocks

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/PROVIDERS.md`
- `/docs/PROMPT_CONTRACTS.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/0-core-vertical-slice/step2.md`
- `/src/image_translator/domain/`
- `/src/image_translator/services/quality_policy.py`

## 작업

외부 SDK 없이 typed provider protocol과 mock adapter suite를 구현하라.

1. provider 공통 타입을 구현하라.
   - 권장 파일: `/src/image_translator/providers/base.py`
   - `ProviderAdapter`, `OCRAdapter`, `TranslatorAdapter`, `ReviewAdapter`, `InpaintingBackend`, `RenderingBackend` protocol을 정의한다.
   - `ProviderCapabilities`, `ProviderConfigIssue`, `ProviderType`, `ProviderUsageMetadata`를 domain/provider boundary 타입으로 정의한다.
2. mock adapter를 구현하라.
   - 권장 파일: `/src/image_translator/providers/mock.py`
   - mock OCR은 deterministic `RawOCRRegion` tuple을 반환한다.
   - mock translator는 요청 region마다 정확히 하나의 `TranslationCandidate`를 반환한다.
   - mock reviewer는 설정된 `RegionReview`를 반환하며 번역문을 생성하지 않는다.
   - visual input은 visual mode와 동의가 있을 때만 mock request에 기록되도록 하라.
3. contract test를 추가하라.
   - 권장 파일: `/tests/unit/providers/test_provider_contracts.py`
   - cardinality, capability enforcement, secret redaction, visual consent enforcement를 검증한다.
4. 실제 DeepL, Gemini, OpenAI, Grok SDK dependency를 아직 추가하지 마라. 이 step은 SDK 격리 경계와 mock 기반 테스트만 다룬다.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "provider protocols와 deterministic mock adapters 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- provider SDK 타입을 `providers` 밖으로 노출하지 마라. Reason: 외부 SDK 변경이 application과 domain에 전파되면 안 된다.
- API key 값을 source, test fixture, log에 넣지 마라. Reason: secret은 환경변수 또는 ignored user config에서만 읽어야 한다.
- visual mode와 이미지 전송 동의 없이 image reference나 crop을 provider에 전달하지 마라. Reason: 개인정보 전송 동의가 품질 workflow의 신뢰 경계다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
