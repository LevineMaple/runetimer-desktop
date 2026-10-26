# NEXON Lv2 Gothic — 포함 경위 및 사용 조건 기록

## 파일 출처

- 서체명: 넥슨Lv2고딕 (NEXON Lv2 Gothic)
- 저작권자: NEXON Korea Corporation
- 공식 배포처: [NEXON LEVEL UP](https://levelup.nexon.com/index.html)
- 사용정책: [넥슨 브랜드 가이드 - 서체](https://brand.nexon.com/ko/ci-brand-guidelines/typeface#section-lv2-gothic)
  (패키지 메타데이터에 적힌 https://levelup.nexon.com/index.html#policy 는 현재 접속되지 않음)
- 이 저장소에 넣은 경로: npm 패키지 [`@kfonts/nexon-lv2-gothic`](https://www.npmjs.com/package/@kfonts/nexon-lv2-gothic) v0.2.0
  (패키지의 원본 `README.md`와 `metadata.json`을 이 디렉터리에 함께 보존)

포함 파일 (`src/`, 수정 없이 원본 그대로):

| 파일 | Weight |
|---|---|
| `NEXON_Lv2_Gothic_Light.ttf` | 300 |
| `NEXON_Lv2_Gothic.ttf` | 400 |
| `NEXON_Lv2_Gothic_Medium.ttf` | 500 |
| `NEXON_Lv2_Gothic_Bold.ttf` | 700 |

## 이 프로젝트에서의 사용 형태

1. 앱 UI 폰트 — `pip_timer_auto_detect_app.pyw`가 실행 시 TTF를 등록해 설정 화면 등에 사용
2. 실행 파일 번들 — `rune_timer.spec`의 datas로 TTF 4종이 exe에 포함되어 재배포됨
3. 문서 임베딩 — 사용자 가이드 PDF 생성 시 TTF를 로드했으며, 배포된 PDF에는 서브셋 폰트가 임베드되어 있음 (생성 도구는 현재 저장소에 없음)

즉 이 프로젝트는 **폰트 파일 자체를 재배포**하며, 폰트를 수정하거나 폰트 자체를
판매하지 않습니다.

## 라이선스 성격

이 폰트는 OFL/Apache 같은 SPDX 표준 오픈소스 라이선스가 아니라 넥슨이 정한
**자체 사용정책**을 따릅니다. 따라서 이 저장소의 GPL-3.0-or-later는 이 폰트
파일에 적용되지 않으며, 사용 조건의 최종 기준은 위 공식 정책 페이지입니다.

## 확인 이력

정책 내용은 변경될 수 있으므로, 배포 시점마다 아래 표를 갱신하세요.

| 확인일 | 확인자 | 확인한 URL | 결과 |
|---|---|---|---|
| 2026-09-05 | 2차 출처 조사 | noonnu.cc/font_page/435, fonts.taedonn.com | 아래 내용 확인. 공식 페이지는 접속 불가로 미확인 |
| (미확인) | | brand.nexon.com/ko/ci-brand-guidelines/typeface | 공식 원문 확인 필요 |

## 확인된 조건 (2026-09-05, 2차 출처 기준)

공식 페이지(levelup.nexon.com, brand.nexon.com) 접속이 되지 않아 폰트 정보
사이트를 통해 확인한 내용이다. **공식 원문 확인으로 대체되어야 한다.**

| 항목 | 조건 |
|---|---|
| 상업적 이용 | 가능. 개인·기업 모두 무료 |
| 인쇄물, 웹, 영상, 포장지, BI/CI | 사용 가능 |
| 임베딩 | 가능. 프로그램 내 폰트 탑재, E-book 제작 포함 |
| 소프트웨어 번들 | 서체의 저작권 안내를 포함하면 가능 |
| 수정·편집 | **금지.** 배포되는 형태 그대로 사용해야 함 |
| 유료 판매 | **금지.** 폰트 파일 자체를 판매할 수 없음 |
| 출처 표기 | 권장 |

### 이 프로젝트에 대한 판단

1. **exe 번들 (사용 형태 2) — 허용 범위로 판단.** "저작권 안내를 포함한
   소프트웨어 번들·임베디드 사용 가능" 조건에 해당하며, 파일을 수정하지
   않고 원본 그대로 포함한다. 저작권 안내는 THIRD_PARTY_LICENSES.txt와
   이 파일이 담당한다.
2. **PDF 서브셋 임베드 (사용 형태 3) — 허용 범위로 판단.** 임베딩 항목에
   해당한다.
3. **저장소에 TTF 원본을 그대로 두는 것 (사용 형태 1의 전제) — 회색지대.**
   정책 본문은 "자유롭게 사용 및 배포"라고 하지만, 폰트 정보 사이트의
   요약표는 "폰트 파일의 수정·복제·배포" 금지로 표기한다. 두 서술이
   상충하므로 공식 원문 확인이 필요하다. 공개 저장소에 폰트 파일을 그대로
   올려두는 것이 문제가 된다면, 저장소에서 TTF를 빼고 빌드 시 공식
   배포처에서 내려받도록 바꾸는 선택지가 있다.

### 출처

- https://noonnu.cc/font_page/435
- https://fonts.taedonn.com/post/NEXON+Lv2+Gothic
