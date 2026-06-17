# Provider Adapter 계약

## 1. 목적

외부 SDK와 모델 차이를 typed adapter 뒤에 격리한다. application과 graph는 provider 이름이나 SDK 타입이 아니라 domain DTO와 capability만 사용한다.

## 2. 공통 계약

모든 adapter는 다음을 제공한다.

```python
class ProviderAdapter(Protocol):
    provider_id: str
    display_name: str

    async def load(self) -> None: ...
    async def unload(self) -> None: ...
    def validate_config(self) -> tuple[ProviderConfigIssue, ...]: ...
    def capabilities(self) -> ProviderCapabilities: ...
```

공통 규칙:

- API key는 환경변수 또는 ignored user config에서만 읽는다.
- config 오류에는 환경변수 이름을 표시할 수 있지만 값을 포함하지 않는다.
- raw provider response를 domain 밖으로 반환하지 않는다.
- timeout, retryable error, non-retryable error를 구분한다.
- 취소 요청을 가능한 범위에서 전파한다.
- request fingerprint와 safe usage metadata를 반환한다.

## 3. Capability

`ProviderCapabilities`:

- provider type
- supported language pairs
- batch 지원 여부와 최대 batch size
- structured output 지원
- visual input 지원
- full image 및 crop 지원
- maximum input size
- streaming 지원
- cost metadata 지원
- local/cloud 구분

capability가 false인 입력을 adapter에 전달하지 않는다.

## 4. OCRAdapter

```python
class OCRAdapter(ProviderAdapter, Protocol):
    async def detect_regions(
        self,
        image_ref: ImageReference,
        language_hints: tuple[str, ...],
    ) -> tuple[RawOCRRegion, ...]: ...
```

역할:

- text geometry와 원문 후보 추출
- provider confidence와 layout 후보 반환

비역할:

- 최종 reading order 확정
- 번역
- 원본 snapshot 수정

MVP는 주 OCR과 보조 OCR을 별도로 선택할 수 있어야 한다.

## 5. TranslatorAdapter

```python
class TranslatorAdapter(ProviderAdapter, Protocol):
    async def translate_page(
        self,
        requests: tuple[TranslationRequest, ...],
    ) -> tuple[TranslationCandidate, ...]: ...
```

지원 provider:

- DeepL
- Gemini
- OpenAI
- Grok

규칙:

- 요청 region마다 정확히 하나의 candidate를 반환한다.
- text-only provider에는 이미지 reference를 전달하지 않는다.
- visual input은 visual mode, 사용자 동의, capability가 모두 true일 때만 전달한다.
- reviewer feedback은 별도 필드로 전달한다.
- 이미 승인된 영역을 재번역하지 않는다.

DeepL adapter:

- text와 context hint만 사용
- visual input capability는 false

Gemini/OpenAI/Grok adapter:

- provider와 선택 model이 지원할 때 visual input 가능
- structured page batch 결과를 domain candidate로 변환

## 6. ReviewAdapter

```python
class ReviewAdapter(ProviderAdapter, Protocol):
    async def correct_ocr(
        self,
        request: OCRCorrectionRequest,
    ) -> OCRCorrectionReview: ...

    async def build_page_context(
        self,
        request: PageContextRequest,
    ) -> PageContextReview: ...

    async def review_translation(
        self,
        request: TranslationReviewRequest,
    ) -> PageReview: ...

    async def review_result_image(
        self,
        request: ResultImageReviewRequest,
    ) -> ResultQualityReview: ...

    async def parse_revision_intent(
        self,
        request: RevisionIntentRequest,
    ) -> RevisionIntentParseResult: ...
```

지원 provider:

- Gemini
- OpenAI
- Grok

규칙:

- reviewer는 최종 번역문을 생성하지 않는다.
- OCR 교정은 후보와 근거만 반환한다.
- review 결과는 schema validation을 통과해야 한다.
- visual method는 visual mode와 동의를 확인한다.
- prompt injection으로 허용 action 또는 시스템 정책을 변경하지 않는다.

## 7. InpaintingBackend

```python
class InpaintingBackend(Protocol):
    backend_id: str
    async def remove_text(self, request: InpaintingRequest) -> InpaintingResult: ...
```

정책:

- 단순 배경은 빠른 local backend를 사용할 수 있다.
- 품질 실패 시 mask 조정 또는 고품질 backend로 escalation한다.
- escalation 순서는 user config에 정의한다.
- backend는 region이나 번역 결과를 mutation하지 않는다.

## 8. RenderingBackend

```python
class RenderingBackend(Protocol):
    async def render(self, request: RenderRequest) -> RenderResult: ...
```

역할:

- RenderPlan 실행
- font fallback
- horizontal/vertical writing
- outline, alignment, spacing 적용

비역할:

- 번역문 변경
- 품질 승인 결정

## 9. Retry와 Fallback

Retryable:

- timeout
- 일시적 network error
- rate limit
- provider 5xx 중 안전한 오류

Non-retryable:

- API key 또는 권한 오류
- 지원하지 않는 language pair
- 요청 크기 초과
- 사용자 동의 없는 visual input
- schema 계약과 지속적으로 불일치하는 provider

Provider retry는 최대 3회다. fallback은 사용자가 설정한 순서와 capability를 만족할 때만 수행한다.

## 10. Provider 선택 UI 규칙

- 선택 전에 config validation 결과를 표시한다.
- 번역 provider와 검증 provider가 같으면 독립성 경고를 표시한다.
- visual mode를 켜면 전송 대상과 provider를 표시하고 동의를 받는다.
- fallback 순서는 사용자가 직접 설정한다.
- provider 변경은 현재 job의 audit 기록에 남긴다.

## 11. Smoke Test

실제 provider smoke test는 marker로 분리하고 credential이 없으면 skip한다.

- 최소 지원 언어쌍 확인
- schema 변환 확인
- visual capability 확인
- config 오류 redaction 확인
- provider SDK 변경 감지
