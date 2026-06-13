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

- **번호 띠만 OCR**: 카드 전체 대신 하단 번호 영역만 읽어 노이즈 제거
- **consensus**: OCR이 연속 두 번 같은 번호를 읽어야 확정 → 한 번 잘못 읽어 엉뚱한 카드 뜨는 것 차단
- **세트 총수로 구분**: `028/150`과 `028/255`처럼 번호가 같아도 분모(set.printedTotal)로 정확히 구분
- **정밀 쿼리**: `number + set.printedTotal`로 1~3장만 받아 빠름 (수백 장 받아 거르지 않음)
- **시크릿 레어 유지**: `198/197`처럼 번호가 총수를 넘는 카드도 인식

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
