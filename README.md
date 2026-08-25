# pokemonboost

두 개의 독립적인 도구가 들어 있습니다.

| 패키지 | 설명 |
| --- | --- |
| `pokemon_stock` | Target.com의 포켓몬 TCG 상품을 주기적으로 조회해 **재입고 시 알림**을 보내는 CLI 앱 |
| `research_agent` | LangGraph 기반 리서치 멀티에이전트 (Researcher → Writer → Reviewer) |

---

## pokemon_stock — Target 포켓몬 카드 재입고 모니터

Target 상품 페이지가 내부적으로 호출하는 RedSky JSON API를 그대로 조회해서,
**품절 → 재입고로 바뀌는 순간에만** 알림을 보냅니다. 재고가 유지되는 동안 반복
알림을 보내지 않으므로 알림 피로가 없고, 상태를 파일에 저장하므로 앱을 재시작해도
과거 알림이 다시 울리지 않습니다.

### 설치

```bash
pip install -r requirements.txt
```

### 3분 세팅

```bash
# 1) 설정 파일 생성
python -m pokemon_stock init

# 2) 감시할 상품의 TCIN 찾기 (Target 상품 URL의 "A-" 뒤 숫자)
python -m pokemon_stock search "pokemon booster bundle"

# 3) 매장 픽업도 감시한다면 매장 ID 찾기
python -m pokemon_stock stores 94301

# 4) config.yaml의 products / store_ids / location을 채운 뒤 지금 상태 확인
python -m pokemon_stock check

# 5) 알림이 실제로 오는지 테스트
python -m pokemon_stock notify-test

# 6) 감시 시작
python -m pokemon_stock watch
```

### 명령어

| 명령 | 하는 일 |
| --- | --- |
| `watch` | 설정한 주기로 계속 감시. `--once`(1회, cron용), `--interval N`, `--cycles N` |
| `check` | 지금 재고를 한 번 출력. 상태 파일·알림을 건드리지 않음. TCIN 직접 지정 가능 |
| `search <키워드>` | 키워드로 상품을 찾아 TCIN 출력 |
| `stores <우편번호>` | 근처 매장의 `store_id` 출력 (픽업 감시용) |
| `notify-test` | 설정된 모든 알림 채널로 샘플 알림 발송 |
| `init` | `config.example.yaml`을 `config.yaml`로 복사 |

### 설정

`config.yaml` (전체 주석은 `config.example.yaml` 참고):

```yaml
products:
  - tcin: "94300072"
    label: "Scarlet & Violet Booster Bundle"

channels: [shipping]        # shipping(배송) / pickup(매장 픽업)
store_ids: []               # pickup을 쓸 때 필요

location:
  zip: "94301"
  state: "CA"
  latitude: 37.44
  longitude: -122.16

polling:
  interval_seconds: 180     # 30초 미만은 거부 (차단 방지)
  jitter_seconds: 45
  realert_after_minutes: 0  # 0 = 재입고 순간에만 알림

notify:
  console: true
  desktop: false
  webhook: { enabled: false, url: "" }
  email:   { enabled: false, username: "", recipients: [] }
```

비밀값은 YAML 대신 환경변수를 쓰세요 (`.env.example` 참고). 환경변수가 항상 파일 값보다 우선합니다.

### 알림 채널

- **console** — 터미널 출력 + 벨소리 (기본값)
- **desktop** — macOS `osascript` / Linux `notify-send` / Windows 토스트
- **webhook** — Discord·Slack incoming webhook (`content`/`text` 둘 다 전송하므로 양쪽 호환)
- **email** — SMTP. Gmail은 2단계 인증 후 **앱 비밀번호**가 필요합니다

여러 채널을 동시에 켤 수 있고, 한 채널이 실패해도 나머지는 그대로 발송됩니다.

### 재입고 판정 규칙

- 감시 대상 채널(`channels`) 중 **하나라도** 구매 가능하면 "재고 있음"으로 봅니다.
- `IN_STOCK` / `LIMITED_STOCK` / `PRE_ORDER_SELLABLE`은 구매 가능으로 처리합니다.
- Target이 처음 보는 상태 문자열을 주면 `UNKNOWN`으로 남기고 **알림을 보내지 않습니다** — 오탐보다 로그를 남기는 쪽을 택했습니다.
- 알림은 `품절 → 재입고` 전환에서만 발생합니다. 재고가 계속 있는 동안 다시 받고 싶으면 `realert_after_minutes`를 설정하세요.

### 상시 실행

cron으로 5분마다 (`--once`가 1회 확인 후 종료):

```cron
*/5 * * * * cd /path/to/pokemonboost && /usr/bin/python3 -m pokemon_stock watch --once >> monitor.log 2>&1
```

또는 `watch`를 그대로 상주시키고 systemd/`launchd`/`tmux`로 관리해도 됩니다.

### 주의사항

- **요청 주기를 너무 짧게 잡지 마세요.** 기본 3분 + 무작위 지터가 안전선이고, 30초 미만은 앱이 거부합니다. 조회 실패가 연속되면 자동으로 백오프합니다.
- RedSky의 공개 웹 키는 가끔 교체됩니다. `401/403`이 나오면 target.com을 브라우저에서 열고 DevTools → Network에서 `redsky.target.com` 요청의 `key=` 값을 복사해 `TARGET_API_KEY`로 넣으세요.
- 이 앱은 **재고 확인과 알림만** 합니다. 자동 구매(봇 체크아웃)는 하지 않습니다.

### 테스트

```bash
pip install pytest
python -m pytest tests/ -q
```

저장된 RedSky 응답 픽스처로 파싱·상태 전환·CLI를 전부 오프라인 검증합니다.

---

## research_agent — LangGraph 리서치 워크플로

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py "양자 컴퓨팅 상용화 현황" --show-notes
```

Researcher가 web_search로 근거를 수집하고, Writer가 초안을 쓰고, Reviewer가 피드백하며
최대 3회까지 수정 루프를 돕니다.
