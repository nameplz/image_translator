# Step 2: quality-export-policy

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/AGENTS.md`
- `/docs/QUALITY.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/EXPORT.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/phases/0-core-vertical-slice/step1.md`
- `/src/image_translator/domain/`
- `/tests/unit/domain/`

## 작업

번역 품질 승인과 export eligibility를 결정론적 정책으로 구현하라.

1. 번역 review 자동 승인 정책을 구현하라.
   - 권장 파일: `/src/image_translator/services/quality_policy.py`
   - 자동 승인 조건은 `docs/QUALITY.md`를 따른다.
   - critical issue가 있으면 점수와 무관하게 자동 승인하지 않는다.
   - `semantic_fidelity`, `completeness`, `character_voice` 각각 3.5 이상이어야 한다.
   - weighted total 기본 threshold는 4.0 이상이어야 한다.
2. export gate 정책을 구현하라.
   - 권장 파일: `/src/image_translator/services/export_gate.py`
   - unresolved `error` 또는 `critical` issue가 있으면 일반 export를 차단한다.
   - 필수 사용자 확인 대기가 있으면 일반 export를 차단한다.
   - `warning`은 사용자 확인 후 일반 export 가능해야 한다.
   - 강제 export는 `ForceApprovalRecord` 같은 명시적 record를 요구해야 한다.
3. 필요한 domain 타입이 부족하면 step1의 파일에 최소 범위로 추가하라.
4. 테스트를 먼저 추가하고 정책 구현을 통과시켜라.
   - 권장 파일: `/tests/unit/services/test_quality_policy.py`
   - 권장 파일: `/tests/unit/services/test_export_gate.py`

## Acceptance Criteria

```bash
python3 scripts/validate_project.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md` 규칙 위반 여부를 확인한다.
3. 최종 응답에 결과를 보고한다:
   - 성공 -> `status: completed`, `summary: "quality auto-approval policy와 export gate policy 구현"`
   - 실패 -> `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 -> `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- quality gate 판정을 LLM 호출에 맡기지 마라. Reason: 자동 승인과 export 차단은 결정론적이고 재현 가능해야 한다.
- reviewer 결과를 번역문으로 사용하지 마라. Reason: reviewer는 판정과 개선 지시만 반환한다.
- phase metadata와 git commit을 수정하지 마라. Reason: 메인 세션이 상태 전이와 커밋을 담당한다.
- 기존 테스트를 깨뜨리지 마라. Reason: 이후 step의 신뢰할 수 있는 기준선이 필요하다.
- `.harness/validation.json`이 없다는 이유로 Node/npm 명령을 추가하지 마라. Reason: 이 프로젝트 validation은 Python/uv로 고정되어 있다.
