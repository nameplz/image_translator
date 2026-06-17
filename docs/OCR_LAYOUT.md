# OCR 및 레이아웃 스펙

## 1. 목적

OCR은 문자열 추출뿐 아니라 번역에 필요한 구조를 복원해야 한다. 특히 일본어 세로쓰기, 우→좌 열 순서, 혼합 writing mode, 회전 효과음, 루비·후리가나를 손실 없이 표현해야 한다.

## 2. Writing Mode

```text
horizontal_ltr  # 좌→우, 행 사이 상→하
horizontal_rtl  # 우→좌, 행 사이 상→하
vertical_rl     # 열 내부 상→하, 열 사이 우→좌
vertical_lr     # 열 내부 상→하, 열 사이 좌→우
rotated         # 임의 각도의 장식/효과음
unknown
```

`TextOrientation`:

```text
upright
rotated_90_cw
rotated_90_ccw
arbitrary_angle
```

writing mode는 문자열 언어와 독립적으로 저장한다.

## 3. Geometry

OCR raw 결과는 polygon 또는 rotated bounding box를 허용한다. normalization 이후 region은 다음을 만족해야 한다.

- geometry가 non-null
- 면적이 양수
- 이미지 경계와 교차
- 정규화된 좌표가 유효
- page 내 고유 region ID 보유

축 정렬 bbox만 저장해 회전 또는 세로 텍스트 정보를 잃지 않는다.

## 4. Reading Order

reading order는 세 계층으로 관리한다.

1. page/panel order
2. dialogue 또는 text group order
3. group 내부 line/column order

일본어 `vertical_rl` 기본 규칙:

- 한 열 내부는 상→하
- 열 사이는 우→좌
- 여러 말풍선의 순서는 panel과 대화 흐름 분석 결과를 사용

좌표 정렬만으로 최종 reading order를 확정하지 않는다. 다음 신호를 함께 사용한다.

- writing mode
- 열과 행 cluster
- 말풍선 및 panel 경계
- 화자 위치
- 대화 꼬리 방향
- OCR 텍스트의 문장 연결성
- 시각 컨텍스트 분석

여러 reading order 후보가 유사한 confidence를 가지면 사용자 검토 대상으로 표시한다.

## 5. Text Role

```text
dialogue
narration
sound_effect
sign
decorative
ruby
unknown
```

text role은 번역 스타일, 번역 여부, 렌더링 전략에 영향을 준다.

- dialogue: 캐릭터 말투와 대화 연결성을 우선
- narration: 문장 완전성과 서술 스타일을 우선
- sound_effect: 짧고 시각적으로 강한 표현을 우선
- sign: 정보 정확성을 우선
- decorative: 사용자가 번역 여부를 선택
- ruby: 본문과 관계를 보존하고 기본 미번역

## 6. 루비·후리가나

- ruby region은 `ruby_target_region_id`로 본문과 연결한다.
- 원본 ruby 문자열과 geometry를 보존한다.
- 기본적으로 본문만 번역한다.
- 사용자는 결과 이미지의 ruby 표시 여부를 선택할 수 있다.
- target language가 일본어이고 ruby 생성 기능을 명시적으로 활성화한 경우에만 새 ruby 후보를 생성할 수 있다.
- 본문과 연결되지 않은 작은 텍스트를 자동으로 ruby로 확정하지 않는다.

## 7. OCR 교차 확인

주 OCR은 전체 이미지를 처리한다. 다음 영역은 보조 OCR 대상이다.

- 낮은 OCR confidence
- 낮은 writing mode 또는 layout confidence
- 비정상 문자
- 문자열과 crop 형태 불일치
- reading order ambiguity
- ruby 관계 ambiguity
- 주 OCR 결과가 언어 규칙과 충돌

주·보조 OCR 결과는 별도 `OCRCandidate`로 보존한다. 자동으로 문자열을 합성하지 않는다.

visual mode가 활성화되면 reviewer가 crop, OCR 후보, 주변 region을 비교해 교정 후보와 근거를 반환할 수 있다.

## 8. 출력 방향

원본 writing mode는 번역과 검증에 항상 전달한다. 결과 렌더링은 목표 언어 표준을 우선한다.

기본값:

- 영어: `horizontal_ltr`
- 한국어: `horizontal_ltr`
- 일본어: region 형태와 프로젝트 설정에 따라 `horizontal_ltr` 또는 `vertical_rl`

방향 변경은 `RenderPlan`에 명시하고 품질 검증 대상에 포함한다.

## 9. 필수 테스트 사례

- 일본어 `vertical_rl` 두 열 이상의 순서
- 세로 대사 내부의 가로 숫자
- 가로 내레이션과 세로 말풍선 혼합
- 회전 효과음
- 좌우 페이지 분할과 panel order
- 본문과 루비 연결
- 불확실한 reading order의 검토 전환
- 목표 언어 표준 방향으로의 RenderPlan 변환
