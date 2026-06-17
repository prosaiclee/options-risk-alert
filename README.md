# Options Risk Alert

15분 지연 미국 옵션 플로우 CSV를 받아 핵심 지수/ETF의 위험회피성 옵션 수요를 감지하는 MVP입니다.

## MVP 범위

- 감시 대상: `VIX`, `SPX/SPY`, `NDX/QQQ`, `SOXX/SMH`
- 출력 등급: `정상`, `관찰`, `주의`, `위험`
- 데이터 입력: Cboe/OPRA/CME 같은 외부 공급자에서 받은 데이터를 `OptionFlowSnapshot` CSV 스키마로 정규화
- 결과 성격: 매수/매도 신호가 아닌 위험 알림과 상황 설명

## 요구사항

- Python 3.10 이상 권장 (개발·테스트는 3.13 기준)
- 기본 CSV 모드(`--provider csv`)는 표준 라이브러리만으로 동작하며 추가 설치가 필요 없습니다.
- 의존성은 사용하는 기능에서만 필요하며, 모두 지연 로딩됩니다.
  - `yfinance`: `--provider yahoo`, `--put-value`
  - `fear-and-greed`: Fear & Greed 지표(기본 활성, `--no-fear-greed`로 끄거나 미설치 시 해당 섹션만 조회 실패로 표시)
- `.env` 로딩은 내장 파서를 사용하므로 `python-dotenv`가 필요하지 않습니다.

```powershell
python -m pip install -r requirements.txt
```

## CSV 필수/권장 필드

필수 필드는 `timestamp`, `symbol`입니다. 나머지는 없으면 0 또는 기본값으로 처리됩니다.

```csv
timestamp,symbol,put_premium_bought,call_premium_bought,puts_bought,calls_bought,otm_put_oi,otm_call_oi,iv30,hv20,norm_25d_skew_30,net_option_delta,dtx1,dtx2_5,dtx6_30,underlying_price,underlying_change_pct,is_event_day,large_trade_count,total_trade_count,vix_front_month,vix_second_month,source_delay_minutes
```

## 실행

```powershell
cd C:\workspace\projects\options-risk-alert
python -m options_risk_alert --history .\examples\history.csv --current .\examples\current.csv
python -m options_risk_alert --history .\examples\history.csv --current .\examples\current.csv --format json
```

## Yahoo Finance 개인 실험 모드

Yahoo Finance는 개인 실험용 데이터 소스로만 사용하세요. 이 모드는 옵션 체인의 `volume * mid price * 100`으로 프리미엄 흐름을 추정합니다. 실제 OPRA 체결 방향, 매수 주도 여부, tick-level 플로우는 알 수 없습니다.

```powershell
cd C:\workspace\projects\options-risk-alert
python -m pip install -r requirements.txt
python -m options_risk_alert --provider yahoo --history .\examples\history.csv --symbols SPY QQQ SOXX SMH --max-expirations 4
```

Yahoo 모드의 기준선도 같은 방식으로 저장한 과거 스냅샷을 사용하는 것이 가장 좋습니다. Cboe/OPRA 기반 history와 Yahoo 기반 current를 섞으면 데이터 정의가 달라 z-score가 과장될 수 있습니다.

Yahoo 스냅샷을 CSV로 쌓아 기준선을 만들 수 있습니다.

```powershell
python -m options_risk_alert --provider yahoo --history .\examples\history.csv --symbols SPY QQQ SOXX SMH --save-current .\data\yahoo_snapshots.csv --append-current
```

30거래일 이상 같은 시간대 스냅샷이 쌓이면, 이후에는 해당 파일을 `--history`로 사용하세요.

Yahoo 모드는 기본적으로 미국 정규장 외 시간과 주말/주요 휴장일에는 수집하지 않고 정상 종료합니다. `--current-latest` 기반 정기 리포트도 미국 시장 거래일이 아니면 전송하지 않습니다. 개인 실험을 위해 장외/휴장일에도 강제로 실행하려면 `--include-closed-market`을 추가하세요.

## Fear & Greed Index 보조 지표

리포트는 기본적으로 CNN Fear & Greed Index를 시장 심리 보조 지표로 함께 출력합니다. 기본적으로 `fear-and-greed` 패키지를 사용하고, 실패하면 직접 CNN JSON 엔드포인트 조회를 시도합니다. 조회가 차단되거나 변경되면 기존 옵션 플로우 리포트는 유지하고, Fear & Greed 섹션만 조회 실패로 표시합니다.

표시 형식은 `수치 / 등급 / 1년 내 데이터에서의 위치`입니다.

```powershell
python -m options_risk_alert --history .\examples\history.csv --current .\examples\current.csv
```

조회하지 않으려면 `--no-fear-greed`를 추가하세요.

## Telegram 알림

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 환경변수를 저장한 뒤 `--send-telegram`을 붙이면 리포트를 Telegram으로 보냅니다.
환경변수 대신 프로젝트 루트의 `.env` 파일에 저장해도 됩니다. `.env.example`을 참고하고 실제 `.env`는 Git에 올리지 마세요.

누적 CSV의 최신 스냅샷으로 리포트를 만들려면 `--current-latest`를 사용합니다.

```powershell
python -m options_risk_alert --history .\data\yahoo_snapshots.csv --current-latest --send-telegram --telegram-min-level 정상
```

권장 운영 방식:

- 정기 보고: 한국 장 시작 전 `08:30`, 미국 장 시작 전. `--telegram-min-level 정상`으로 정상 상태도 전송합니다.
- 이상 알림: 15분 수집 작업에 `--send-telegram`만 추가합니다. 기본값은 `--telegram-min-level 관찰`이므로 `정상`은 전송하지 않고, `관찰/주의/위험`만 전송합니다.

## Telegram 질문 응답

Telegram 봇으로 질문을 보내면 `--telegram-poll-once` 작업이 새 메시지를 읽고 답변합니다.

```powershell
python -m options_risk_alert --history .\data\yahoo_snapshots.csv --telegram-poll-once
```

질문 예시:

- `시장 상황 알려줘`
- `옵션 상황 알려줘`
- `풋옵션 가치 알려줘`
- `SOXX 헷지 후보`

실시간 대화처럼 쓰려면 위 명령을 Windows 작업 스케줄러에서 1분마다 실행하도록 등록합니다. 마지막으로 처리한 Telegram update id는 `data\telegram_offset.txt`에 저장됩니다.

더 즉각적인 응답을 원하면 long polling 모드를 계속 실행합니다.

```powershell
python -m options_risk_alert --history .\data\yahoo_snapshots.csv --telegram-listen
```

이 모드는 프로세스가 켜져 있는 동안 Telegram 메시지를 기다렸다가 새 질문에 바로 응답합니다.

## 풋옵션 가치 스크리닝

반도체 중심 자산 헤지를 위해 풋옵션이 상대적으로 싼 구간을 찾으려면 `--put-value`를 사용합니다. 기본 대상은 `QQQ`, `SOXX`, `SMH`입니다.

```powershell
python -m options_risk_alert --history .\data\yahoo_snapshots.csv --current-latest --put-value --put-value-symbols QQQ SOXX SMH
```

이 기능은 21-120일 만기, 5-20% OTM 풋을 대상으로 낮은 IV, 낮은 비용/보호폭, 좁은 bid-ask spread, open interest/volume을 함께 점수화합니다. 기본적으로 bid/ask가 없거나 스프레드가 40%를 넘는 후보는 제외합니다. 출력에는 후보 풋의 IV가 최근 1년 축적 데이터의 `iv30` 분포에서 어느 위치인지도 표시합니다. 이는 특정 옵션 계약의 1년 과거 가격이 아니라, 보유한 Yahoo 스냅샷 기준의 IV 상대 저렴도입니다. 실제 매수 추천이 아니라 헤지 후보 스크리닝입니다.

## 판정 방식

- 일반 주식/ETF/지수는 풋 매수 프리미엄, 풋/콜 프리미엄 비율, OTM 풋 비중, IV와 풋 스큐 동반 상승, 단기 만기 비중, 순델타 하방 쏠림을 같은 시간대 과거 기준선과 비교합니다.
- VIX는 별도로 해석합니다. `VIX 콜 매수 급증`은 변동성 확대 헤지 신호이고, `VIX 풋 매수 급증`은 변동성 하락 또는 공포 완화 베팅일 수 있습니다.
- 단일 대형 거래만으로 구성된 흐름은 `위험` 등급으로 바로 올리지 않습니다.
- 여러 그룹에서 동시에 `주의` 이상이 나오면 포트폴리오 등급을 상향합니다.

## CLI 옵션 레퍼런스

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--history` | (필수) | 같은 시간대 비교용 기준선 CSV 경로 |
| `--current` | - | 현재 스냅샷 CSV. `--provider csv`에서 필수 |
| `--current-latest` | off | `--history`의 최신 timestamp를 현재로, 이전 행을 기준선으로 사용 |
| `--provider` | `csv` | `csv` 또는 `yahoo` |
| `--symbols` | `SPY QQQ SOXX SMH` | Yahoo 수집 대상 심볼 |
| `--max-expirations` | `4` | 심볼당 수집할 Yahoo 만기 수 |
| `--save-current` | - | 수집한 현재 스냅샷을 저장할 CSV 경로 |
| `--append-current` | off | `--save-current`/풋 상세를 덮어쓰지 않고 누적 |
| `--save-put-details` | `.\data\yahoo_put_details.csv` | Yahoo 풋 만기/행사가 상세 저장 경로 |
| `--no-put-details` | off | 풋 상세 저장·출력 비활성화 |
| `--include-closed-market` | off | 장외/휴장일에도 Yahoo 수집·리포트 강제 실행 |
| `--no-fear-greed` | off | Fear & Greed 지표 조회 비활성화 |
| `--format` | `text` | `text` 또는 `json` |
| `--min-history-points` | `10` | 기준선 계산에 필요한 최소 표본 수 |
| `--send-telegram` | off | 리포트를 Telegram으로 전송 |
| `--telegram-min-level` | `관찰` | 전송 최소 등급(`정상`/`관찰`/`주의`/`위험`) |
| `--put-value` | off | 풋옵션 가치 후보 스크리닝 출력 |
| `--put-value-symbols` | `QQQ SOXX SMH` | 풋 가치 스크리닝 대상 |
| `--put-value-top` | `3` | 심볼당 표시할 후보 수 |
| `--put-value-max-spread` | `40.0` | 후보 제외 기준 bid-ask 스프레드(%) |
| `--html-report` | - | 정적 HTML 대시보드 출력 경로 |
| `--telegram-poll-once` | off | Telegram 새 메시지 1회 폴링·응답 |
| `--telegram-listen` | off | long polling으로 계속 응답 대기 |

## 테스트

```powershell
cd C:\workspace\projects\options-risk-alert
python -m unittest discover -s tests
```

## ETF 옵션 시각화 대시보드

누적 CSV의 최신 스냅샷을 기준으로 정적 HTML 대시보드를 만들 수 있습니다.

```powershell
python -m options_risk_alert --history .\data\yahoo_snapshots.csv --current-latest --html-report .\data\latest_options_dashboard.html
```

대시보드에는 최신 ETF별 옵션 현황, 풋 프리미엄 추이, 풋/콜 프리미엄 비율, IV30 추이, 풋옵션 만기/행사가 구간 상세가 포함됩니다. 생성된 HTML은 별도 서버 없이 브라우저에서 바로 열 수 있습니다.

## Vercel 배포 (보호된 정적 대시보드)

이 저장소는 정적 대시보드(`public/index.html`)를 Vercel에 배포하도록 구성되어 있습니다.

- **데이터 수집은 Vercel 밖**에서 합니다. Yahoo가 데이터센터 IP를 차단하고 yfinance가 무거워 Vercel 서버리스에는 부적합하기 때문입니다.
- **GitHub Actions**(`.github/workflows/dashboard.yml`)가 미국 정규장 시간에 주기적으로 스냅샷을 수집·누적하고 `public/index.html`을 재생성한 뒤 커밋합니다. Vercel은 push마다 자동 재배포합니다.
- **접근 보호**: 루트 `middleware.js`가 HTTP Basic Auth를 강제합니다. 자격증명은 Vercel 환경변수에서만 읽으며, 미설정 시 모든 요청을 401로 막습니다(fail-closed).

### 구성 요소

| 파일 | 역할 |
| --- | --- |
| `public/index.html` | 배포되는 정적 대시보드 (자동 생성·커밋) |
| `vercel.json` | `public/`을 사이트 루트로 서빙, 보안 헤더, 빌드 없음 |
| `middleware.js` | Basic Auth (env 자격증명, fail-closed) |
| `.vercelignore` | Python 수집기·데이터·테스트를 배포에서 제외 |
| `.github/workflows/dashboard.yml` | 정기 수집 → 재생성 → 커밋 |

### 최초 배포 절차 (1회)

1. 이 저장소를 **private** GitHub 저장소로 push 합니다.
2. Vercel에서 New Project → 해당 저장소 Import (Framework Preset: Other).
3. Vercel 프로젝트 환경변수에 자격증명을 추가합니다(저장소에 절대 커밋하지 않음).

   ```
   BASIC_AUTH_USER=<원하는 아이디>
   BASIC_AUTH_PASSWORD=<강력한 비밀번호>
   ```

4. 배포 후 대시보드 URL 접속 시 Basic Auth 창이 뜨면 정상입니다.
5. GitHub Actions는 기본 `GITHUB_TOKEN`만으로 데이터를 커밋합니다. 저장소 Settings → Actions → Workflow permissions를 **Read and write**로 설정하세요.

> Telegram 토큰 등 운영 비밀은 Vercel/GitHub에 올리지 않습니다. 대시보드 배포 경로에는 옵션 메트릭(파생 데이터)만 포함됩니다.
