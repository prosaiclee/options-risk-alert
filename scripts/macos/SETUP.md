# Mac mini 홈서버 설정 (수집 + 텔레그램)

Mac mini를 상시 구동 서버로 만들어 ① 대시보드용 데이터 수집·푸시와 ② 텔레그램
알림/질문응답을 모두 돌리는 절차입니다. 대시보드 자체는 Vercel에서 서빙되므로
Mac mini는 데이터만 만들어 push 하면 됩니다.

> 사전: GitHub Actions의 자동 수집 cron은 비활성화되어 있습니다(Mac mini가 단일
> 수집원). 둘을 동시에 켜면 같은 repo에 push 경쟁이 생깁니다.

아래에서 `YOURNAME`은 Mac 사용자명으로 바꾸세요. 클론 위치는
`/Users/YOURNAME/options-risk-alert`를 가정합니다.

## 1. 필수 도구 설치 (터미널)

```bash
# Homebrew가 없으면 먼저 설치: https://brew.sh
brew install python git
```

## 2. 저장소 클론

```bash
cd ~
git clone https://github.com/prosaiclee/options-risk-alert.git
cd options-risk-alert
```

## 3. 파이썬 가상환경 + 의존성

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -r requirements.txt
```

## 4. 텔레그램 토큰 (.env) — git에 올리지 않음

```bash
cp .env.example .env
nano .env     # 실제 토큰/챗 ID 입력 후 저장 (Ctrl+O, Enter, Ctrl+X)
```

## 5. git 신원 + 무인 push 설정 (SSH 권장)

launchd 작업은 비밀번호를 입력할 수 없으므로 SSH 키로 무인 push를 설정합니다.

```bash
# 5-1. 커밋 작성자를 prosaiclee로 (Vercel/GitHub 일관성)
git config user.name "prosaiclee"
git config user.email "150650793+prosaiclee@users.noreply.github.com"

# 5-2. SSH 키 생성 후 공개키를 GitHub에 등록
ssh-keygen -t ed25519 -C "macmini" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
#   → 출력된 줄을 GitHub → Settings → SSH and GPG keys → New SSH key 에 붙여넣기

# 5-3. 원격을 SSH로 전환
git remote set-url origin git@github.com:prosaiclee/options-risk-alert.git
ssh -T git@github.com    # "successfully authenticated" 나오면 OK
```

## 6. 스크립트 실행 권한 + 1회 수동 테스트

```bash
chmod +x scripts/collect_and_push.sh scripts/telegram_poll.sh
./scripts/collect_and_push.sh     # 장중이면 수집·push, 장외면 "Nothing to push"
```

## 7. launchd 작업 등록 (자동 실행)

plist 안의 `/Users/REPLACE_ME/...` 경로를 본인 경로로 바꿔 복사합니다.

```bash
mkdir -p ~/Library/LaunchAgents
sed "s#/Users/REPLACE_ME#$HOME#g" scripts/macos/com.optionsrisk.collect.plist  > ~/Library/LaunchAgents/com.optionsrisk.collect.plist
sed "s#/Users/REPLACE_ME#$HOME#g" scripts/macos/com.optionsrisk.telegram.plist > ~/Library/LaunchAgents/com.optionsrisk.telegram.plist

launchctl load ~/Library/LaunchAgents/com.optionsrisk.collect.plist
launchctl load ~/Library/LaunchAgents/com.optionsrisk.telegram.plist
```

- `com.optionsrisk.collect` : 15분마다 수집 + 대시보드 + 알림 + push (장외는 자동 skip)
- `com.optionsrisk.telegram`: 60초마다 텔레그램 질문 폴링·응답

## 8. 동작 확인

```bash
launchctl list | grep optionsrisk          # 등록 확인
tail -f data/collect.log data/telegram.log  # 실행 로그
```

## 잠자기(sleep) 방지

Mac mini가 잠들면 작업이 멈춥니다. 시스템 설정 → 디스플레이/배터리에서
"잠자기 안 함"으로 두거나:

```bash
sudo pmset -a sleep 0 disksleep 0
```

## 작업 중지/해제

```bash
launchctl unload ~/Library/LaunchAgents/com.optionsrisk.collect.plist
launchctl unload ~/Library/LaunchAgents/com.optionsrisk.telegram.plist
```

## 노트북에서 돌리던 작업 정리

Mac mini로 옮긴 뒤에는 Windows 노트북의 작업 스케줄러에 등록했던 수집/텔레그램
작업을 **비활성화**하세요. 두 머신이 같은 repo에 push 하면 충돌합니다.
