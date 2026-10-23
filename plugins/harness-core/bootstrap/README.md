# bootstrap — WSL2 개발 환경 이식 도구

새 PC(WSL2 Ubuntu 24.04)에 개발 환경을 재현한다. 훅이 아니라 **수동 도구**라서 플러그인 로딩과 무관하다.

## 사용
```bash
bash bootstrap.sh export     # 이전 PC: 인벤토리(manifest.txt) 생성 + 새 PC 로 안 따라가는 변경 경고
bash bootstrap.sh verify --all   # 새 PC: 검사만. 종료코드 0 = 전부 충족 ("끝났나?"의 유일한 판정)
bash bootstrap.sh            # 새 PC: 프로젝트를 체크박스로 골라 설치 (재실행 안전)
bash bootstrap.sh --projects kg,qmd | --all | --dry-run
bash bootstrap.sh selftest   # 판정 로직 시험 (부작용 없음)
```
새 PC 로 옮기는 파일은 `bootstrap.sh` 와 `manifest.txt` **두 개**(같은 폴더). `manifest.txt` 는 export 가 만드는
생성물(패키지·저장소 URL·크론 포함)이라 커밋하지 않는다(`.gitignore`).

## 결정
- **모든 단계는 check → install → check.** `verify` 는 앞의 check 만 돈다. 이식 중 실패는 거의 전부 "설치됨의 정의가
  없어서" 실행해 봐야 알았던 것이다(apt 누락, GGUF 모델, GPU 휠, 심링크, 유닛).
- 인벤토리는 사람 기억이 아니라 `export` 가 만든다. 코드가 요구하는 값(모델 경로, llama 휠 버전)은 코드·락에서 읽는다.
- `pipefail` 을 쓰지 않는다. `생산자 | grep -q` 는 grep 이 먼저 끝나면 생산자가 SIGPIPE 로 죽어 거짓 실패한다
  (`ssh -T`, `headroom install status` 에서 실제로 겪음). 설치 실패는 pipe 가 아니라 설치 후 재검사가 잡는다.
- headroom 은 **Docker 배포로 통일**한다. systemd 서비스(python)와 섞이면 "Docker deployments must be started by the
  Docker supervisor" 가 반복되어 재시작 카운터가 수백까지 오른다(552회). `hr_ok` 가 유닛 부재까지 검사한다.
- 로컬 패치(headroom #4207)는 앵커가 정확히 1곳일 때만 적용하고 아니면 실패한다(버전이 바뀌면 조용히 틀리지 않는다).

## 한계 (LIMITS)
- 설치 경로 전체(`*_add`)는 새 PC 에서 처음 실행된다. 자동 시험은 판정 로직(`selftest`)과 `verify`/`export` 뿐이다.
- 체크박스 화면(whiptail)은 TTY 가 필요해 자동 시험하지 못한다. 선택·의존 처리는 `--projects` 로 시험한다.
- `mobius` 설치(pip -e), 리랭커 내려받기 URL, `headroom install apply` 옵션은 도움말·매니페스트 기준 추정이다.
- `kg` 로컬 패치는 `kg-platform` 추적 파일을 수정한다(진행 표시, quant·analysis optional). 업스트림과 충돌할 수 있다.
- headroom 패치는 `headroom update` 로 사라진다 — `verify` 가 검사하고 `install` 이 다시 적용한다(#4209 머지 시 불필요).
- 사용자명이 `phantom` 이 아니면 `~/.agents` 심링크·유닛·크론의 절대경로가 일부 끊긴다(preflight 가 알린다).

## 시험
`selftest` 는 step 엔진·섹션 파서·크론 필터·의존 선택·go 바이너리 이름을 임시 디렉터리에서 확인한다. 변이 시험(결함을 주입해
시험이 실패하는지)은 2026-10-23 에 5종(NAS 필터 제거, 경로 검사 제거, verify 의 설치 흘러감, 의존 누락, 설치 후 재검사 제거)을
모두 감지했다. 결함을 고칠 때는 이 방식으로 시험이 그 결함을 잡는지 먼저 확인한다.
@experimental · Expiry 2026-12-31 · Owner phantom · Removal: 이식 완료 후 `verify` 통과 + 다음 이식 계획이 없을 때
