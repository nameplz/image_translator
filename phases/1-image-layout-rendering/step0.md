# Step 0: image-io-resources

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/RELEASE.md`
- `/docs/ADR.md`
- `/phases/0-core-vertical-slice/index.json`
- `/src/image_translator/domain/`
- `/src/image_translator/services/`
- `/pyproject.toml`

## 작업

이미지 파일과 resource path를 다루는 service 기반을 구현하라.

1. 필요한 runtime dependency를 `pyproject.toml`에 추가하라.
   - `pillow`
   - `numpy`
   - `opencv-python-headless`
   - dependency 추가는 `uv add pillow numpy opencv-python-headless`로 수행하고 `uv.lock`을 함께 갱신하라.
   - dependency 도입과 같은 변경에서 `AGENTS.md`의 현재 상태, `tests/unit/test_bootstrap_contract.py`, 관련 문서를 함께 갱신하라.
2. 이미지 reference와 파일 검증 service를 구현하라.
   - 권장 파일: `/src/image_translator/domain/image.py`
   - 권장 파일: `/src/image_translator/services/image_io.py`
   - 지원 확장자와 실제 파일 타입을 모두 검증하라.
   - 사용자 경로, symlink, traversal 가능성을 고려하라.
   - user-facing error와 developer diagnostic을 분리할 typed error를 사용하라.
3. resource path abstraction을 구현하라.
   - 권장 파일: `/src/image_translator/config/resources.py`
   - source checkout, installed wheel, PyInstaller artifact를 고려하되 이 step에서는 source checkout과 wheel 경로 test를 우선한다.
   - 임의 module에서 source-tree-relative 경로 계산을 반복하지 않게 하라.
4. unit test를 추가하라.
   - 권장 파일: `/tests/unit/services/test_image_io.py`
   - 권장 파일: `/tests/unit/config/test_resources.py`
   - 잘못된 확장자, 깨진 이미지, input overwrite 위험, metadata redaction 기본값을 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "image IO validation과 resource path abstraction 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 사용자 파일 경로를 신뢰하지 마라. Reason: 사용자 파일과 경로는 보안 문서상 신뢰할 수 없는 입력이다.
- 입력 이미지와 같은 경로로 output을 허용하지 마라. Reason: 원본 손상을 방지해야 한다.
- `domain`에서 Pillow, NumPy, OpenCV를 import하지 마라. Reason: domain은 provider와 image processing runtime에서 독립적이어야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
