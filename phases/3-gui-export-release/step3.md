# Step 3: settings-privacy-export-ui

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/UI_GUIDE.md`
- `/docs/PROVIDERS.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/EXPORT.md`
- `/docs/QUALITY.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/3-gui-export-release/step2.md`
- `/src/image_translator/config/settings.py`
- `/src/image_translator/providers/registry.py`
- `/src/image_translator/services/export_service.py`
- `/src/image_translator/gui/`

## 작업

Provider/privacy settings, output path selection, Save As/export gate UI를 구현하라.

1. settings dialog를 구현하라.
   - 권장 파일: `/src/image_translator/gui/settings_dialog.py`
   - 주 OCR, 보조 OCR, 번역 provider, 검증 provider, fallback 순서, visual mode, image transmission consent, inpainting backend 순서를 표시하라.
   - config validation 결과를 표시하되 secret 값을 표시하지 마라.
   - 번역 provider와 검증 provider가 같으면 독립성 warning을 표시하라.
2. output path와 Save As flow를 구현하라.
   - 권장 파일: `/src/image_translator/gui/export_controller.py`
   - 실행 전 output 경로 선택과 “검토 후 저장” 모드를 지원하라.
   - 품질 gate 전에는 requested output path에 파일을 생성하지 않게 하라.
   - overwrite confirmation과 forced export reason 입력을 요구하라.
3. resume list placeholder를 연결하라.
   - 재개 가능한 checkpoint가 있으면 새 작업 시작 전에 표시할 수 있는 model/controller hook을 둔다.
4. GUI test를 추가하라.
   - 권장 파일: `/tests/gui/test_settings_export_ui.py`
   - visual mode consent gating, secret redaction, provider same warning, Save disabled by blocking issue, forced export confirmation을 검증하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
python3 scripts/run_gui_tests.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "provider/privacy settings와 export gate UI 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- visual mode 활성화 전에 전송 provider와 전송 대상을 숨기지 마라. Reason: 사용자는 이미지 전송에 명시적으로 동의해야 한다.
- API key 값을 UI, log, checkpoint에 표시하거나 저장하지 마라. Reason: secret redaction은 보안 계약이다.
- blocking issue가 남은 결과의 일반 Save를 활성화하지 마라. Reason: 일반 export는 unresolved `error`/`critical` issue와 필수 확인 대기를 차단해야 한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
