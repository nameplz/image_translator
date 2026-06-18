# Step 4: mock-mvp-integration-release-gates

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/TESTING.md`
- `/docs/RELEASE.md`
- `/docs/SECURITY_PRIVACY.md`
- `/docs/PRD.md`
- `/docs/QUALITY.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/3-gui-export-release/step3.md`
- `/.harness/validation.json`
- `/scripts/validate_project.py`
- `/src/image_translator/`
- `/tests/`

## 작업

MVP mock workflow 기준으로 integration, GUI, release readiness gate를 강화하라. 이 단계는
mock MVP integration gate이며, 실제 provider adapter를 포함한 final MVP release gate는
`4-real-provider-adapters` phase 이후에 완성한다.

1. mock provider 기반 전체 workflow integration test를 완성하라.
   - 권장 파일: `/tests/integration/test_mock_mvp_workflow.py`
   - fixture image -> OCR -> vertical/mixed layout -> TranslationQualityGraph -> inpainting -> rendering -> ResultQualityGraph -> natural revision -> export 경로를 검증하라.
   - 성공, 사용자 interrupt, provider retry, fallback, cancel, resume 경로를 각각 검증하라.
2. GUI critical flow test를 보강하라.
   - output path 실행 전 선택, quality gate 전 파일 미생성, Save As, overwrite 확인, 일반 Save 차단, 자연어 plan preview를 검증하라.
3. release smoke를 추가하라.
   - 권장 파일: `/tests/integration/test_installed_resource_paths.py`
   - source tree 밖 resource loading, wheel import, py.typed marker, checkpoint path abstraction을 검증하라.
4. security/release scan helper를 추가하거나 기존 validation에 연결하라.
   - secret 또는 개인 경로가 committed config/log/test fixture에 없는지 검사하라.
   - dependency audit은 release gate 문서에 맞춰 명령 또는 수동 절차를 명시하라.
5. validation gate가 80% coverage, ruff, mypy를 유지하는지 확인하라.

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
python3 scripts/run_gui_tests.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "mock MVP integration, GUI, release readiness gates 보강"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- 외부 유료 provider를 기본 validation에서 호출하지 마라. Reason: provider smoke는 credential이 있을 때 별도 marker로 실행해야 한다.
- release gate에서 known critical vulnerability를 무시하지 마라. Reason: release 문서는 critical vulnerability가 있으면 차단하도록 요구한다.
- coverage 기준을 낮추지 마라. Reason: 프로젝트 validation은 80% coverage gate를 기본 계약으로 사용한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
