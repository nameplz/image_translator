# Image Translator 스펙 문서 지도

## 문서 우선순위

문서가 충돌하면 다음 순서를 따른다.

1. [QUALITY.md](QUALITY.md)
2. [DOMAIN_MODEL.md](DOMAIN_MODEL.md)
3. [WORKFLOWS.md](WORKFLOWS.md)
4. [ARCHITECTURE.md](ARCHITECTURE.md)
5. [PRD.md](PRD.md)
6. 나머지 상세 문서

## 제품과 품질

- [PRD.md](PRD.md): 제품 목표, 범위, 사용자 시나리오
- [QUALITY.md](QUALITY.md): 품질 계층, rubric, 승인 기준
- [OCR_LAYOUT.md](OCR_LAYOUT.md): 세로쓰기, reading order, 루비, 혼합 레이아웃

## 구현 계약

- [ARCHITECTURE.md](ARCHITECTURE.md): 레이어, 상태 소유권, persistence
- [ADR.md](ADR.md): 확정된 기술·제품 결정
- [DOMAIN_MODEL.md](DOMAIN_MODEL.md): DTO와 불변 조건
- [WORKFLOWS.md](WORKFLOWS.md): LangGraph node와 routing
- [PROVIDERS.md](PROVIDERS.md): provider adapter 계약
- [PROMPT_CONTRACTS.md](PROMPT_CONTRACTS.md): AI 입력·출력·권한 계약

## 사용자 작업 흐름

- [UI_GUIDE.md](UI_GUIDE.md): 진행, 검토, 자연어 수정, revision UI
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md): 캐릭터·호칭·용어 규칙
- [EXPORT.md](EXPORT.md): 저장 경로와 export gate

## 검증과 운영

- [TESTING.md](TESTING.md): 테스트 전략과 필수 사례
- [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md): secret, 이미지 전송, checkpoint
- [RELEASE.md](RELEASE.md): CI, resource, packaging, release gate
