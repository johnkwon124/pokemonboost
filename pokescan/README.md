# PokeScan

iPhone Safari 전용 정적 PWA. 아이폰 카메라로 포켓몬 카드 하단 번호를 비추면 자동 인식해서 카드 설명·분석과 현재 raw NM(일반 거래) 시세를 보여줍니다. 백엔드·DB 없음 — 스캔 결과는 앱을 닫으면 사라집니다.

## 동작 방식 (전부 브라우저)

```
iPhone Safari
  ↓ getUserMedia 라이브 프리뷰, 손이 멈췄을 때만 하단 번호 띠를 캡처
Cloud Vision API (브라우저 직접 호출, referrer 제한 키)
  ↓ 번호(예: 025/198) 추출 — 연속 2회 같은 번호로 읽혀야 확정(오인식 방지)
Pokemon TCG API (브라우저 직접 호출, 무인증)
  ↓ number + set.printedTotal 정밀 쿼리로 정확한 1장만 조회
규칙 기반 분석 → 결과 화면(메모리에만, 닫으면 휘발)
```

## 정확도·속도 설계

- **영문 카드**: 번호+세트총수(`028/150`)로 정밀 매칭. 연속 두 번 같은 번호로 읽혀야 확정(consensus) → 오인식 차단. 시크릿 레어(`198/197`)도 인식
- **일본어/한국어 카드**: 무료 DB 어디에도 일본/한국 전용 세트 번호 체계가 없으므로(TCGdex는 국제판 번역만 제공), 카드의 **포켓몬 이름**을 읽어 영문판에 매칭. PokeAPI 종족명 사전(일/한/영, 지연 로드)으로 이름 변환 → 영문판 후보를 이미지 그리드로 보여주고 사용자가 선택 → 영문판 시세를 "추정치"로 표시
- **진단 패널**: 스캔 화면 하단 "진단 정보"에서 OCR 결과·감지 언어·매칭 과정 확인 가능

## 설정 / 빌드 / 배포

```bash
cp .env.local.example .env.local   # NEXT_PUBLIC_GOOGLE_VISION_API_KEY 입력
npm install
npm run build                      # out/ 정적 파일 생성
```

`out/` 폴더를 정적 호스팅(Netlify/Cloudflare Pages/Vercel)에 올리면 됩니다. 카메라 API는 HTTPS 필수.

### Cloud Vision 키 제한 (필수)

키가 클라이언트에 노출되므로 Google Cloud 콘솔에서:
1. API 제한 → Cloud Vision API만
2. 애플리케이션 제한 → HTTP 리퍼러 → 배포 도메인(`https://your.app/*`) + `http://localhost:3000/*`

## 환경 변수

| 키 | 용도 | 필수 |
|----|------|------|
| `NEXT_PUBLIC_GOOGLE_VISION_API_KEY` | Cloud Vision OCR | 예 |
| `NEXT_PUBLIC_POKEMONTCG_API_KEY` | TCG 레이트 리밋 완화 | 선택 |
