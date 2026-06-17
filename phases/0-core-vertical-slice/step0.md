# Step 0: project-package-boundaries

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/TESTING.md`
- `/pyproject.toml`
- `/.harness/validation.json`
- `/tests/unit/test_bootstrap_contract.py`

## 작업

Python package의 기본 경계와 테스트 구조를 ADR-011에 맞춰 정리하라.

1. 아래 디렉터리와 `__init__.py`를 필요한 만큼 생성하라.
   - `/src/image_translator/app`
   - `/src/image_translator/config`
   - `/src/image_translator/domain`
   - `/src/image_translator/providers`
   - `/src/image_translator/services`
   - `/src/image_translator/workflows`
   - `/src/image_translator/use_cases`
   - `/src/image_translator/persistence`
   - `/src/image_translator/gui`
   - `/src/image_translator/observability`
2. layer import direction을 검증하는 unit test를 추가하라.
   - 권장 파일: `/tests/unit/test_architecture_boundaries.py`
   - `domain`이 PySide6, LangGraph, provider SDK, OpenCV를 import하지 않는지 검사하라.
   - `services`가 `providers`를 import하지 않는지 검사하라.
   - `gui`가 graph node나 provider adapter를 직접 import하지 않는지 검사하라.
3. 공용 테스트 helper를 추가할 필요가 있으면 `/tests/conftest.py` 또는 `/tests/helpers/`에 둔다.
4. 구현 package 이름은 계속 `image_translator`로 유지하고, `py.typed`를 삭제하지 마라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "package layer scaffold와 architecture boundary test 추가"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- `domain`에서 GUI, LangGraph, provider SDK, OpenCV를 import하지 마라. Reason: domain은 Pydantic과 표준 라이브러리만 의존해야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
