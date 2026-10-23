#!/usr/bin/env bash
# bootstrap.sh — WSL2 Ubuntu 24.04 개발 환경 이식. 이 파일 + manifest.txt 두 개로 끝난다.
#
# 사용
#   bash bootstrap.sh export                 이전 PC: 인벤토리(manifest.txt) 생성 + 미푸시 변경 경고
#   bash bootstrap.sh                        새 PC: 설치 (프로젝트를 체크박스로 고른다)
#   bash bootstrap.sh verify                 새 PC: 검사만 — "끝났나?"의 유일한 판정 (종료코드 0 = 전부 충족)
#   bash bootstrap.sh selftest               이 스크립트의 판정 로직 자체 시험 (부작용 없음, 변이 시험은 README)
#   옵션: --projects kg,qmd   --all   --dry-run
#
# 설계 원칙 — 이식 중 겪은 실패들의 공통 뿌리는 "설치됨"의 정의가 없었다는 것이다.
#   1) 모든 단계는 check → install → check. verify 는 앞의 check 만 돈다.
#   2) 인벤토리는 사람 기억이 아니라 export 가 만든다(패키지 매니저별 목록·apt 출처·저장소 원격 URL).
#   3) git 밖 상태(모델 GGUF·심링크·systemd 유닛·.env)는 코드가 요구하는 값을 코드에서 읽어 검사한다.
#   4) 환경 전제(GPU 드라이버 재부팅, WSL systemd)는 설치 전에 검사하고 이유를 말한 뒤 멈춘다.
#   5) 생성물은 손으로 복사하지 않고 만드는 명령을 부른다(headroom 유닛, kg-search 유닛의 venv 경로).
# 위치·관리: claude-project-config/plugins/harness-core/bootstrap/ (README.md). manifest.txt 는 export 가 만드는 생성물이라 커밋하지 않는다.
# 훅이 아니라 수동 도구라서 플러그인 로딩에는 영향이 없다. 이 PC 외 환경 변경은 install 모드에서만 일어난다.
set -u
# pipefail 을 쓰지 않는다: `생산자 | grep -q` 는 grep 이 먼저 끝나면 생산자가 SIGPIPE 로 죽어 파이프 전체가 실패로 판정된다
# (ssh -T 와 headroom status 에서 실제로 겪었다). 설치 실패는 pipe 가 아니라 설치 후 재검사(step)가 잡는다.

M="$(cd "$(dirname "$0")" && pwd)"; MF="$M/manifest.txt"; STATE="$HOME/.bootstrap-state"
MODE=install; DRY=0; PICKARG=""; RES=(); NOTES=(); SEL=()
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/go/bin:/usr/local/go/bin:$HOME/.dotnet/tools:$PATH"
KG="$HOME/knowledge"

while [ $# -gt 0 ]; do
  case "$1" in
    export|install|verify|selftest) MODE=$1;;
    --dry-run) DRY=1;;
    --all) PICKARG=all;;
    --projects) shift; PICKARG=${1:-};;
    --projects=*) PICKARG=${1#*=};;
    *) echo "알 수 없는 인자: $1 (사용법은 파일 머리말)"; exit 2;;
  esac; shift
done

# ───────────────────────── 공용 ─────────────────────────
has()  { command -v "$1" >/dev/null 2>&1; }
log()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
rec()  { RES+=("$1|$2"); case $1 in ok) printf '  \033[32m✓\033[0m %s\n' "$2";; new) printf '  \033[36m✚\033[0m %s\n' "$2";;
           MISS) printf '  \033[31m✗\033[0m %s (미충족)\n' "$2";; FAIL) printf '  \033[31m✗\033[0m %s (실패)\n' "$2";; dry) ;; esac; }
sec()    { awk -v s="[$1]" '$0==s{f=1;next} /^\[/{f=0} f&&NF&&!/^#/' "$MF"; }     # 주석·빈 줄 제외
secraw() { awk -v s="[$1]" '$0==s{f=1;next} /^\[/{f=0} f' "$MF"; }                 # 그대로(crontab 용)
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; report; exit 1; }
crit() { [ "$MODE" = verify ] && return 0; die "$*"; }                             # 필수 단계 실패: 설치 모드에선 중단
load_nvm() {
  export NVM_DIR="$HOME/.nvm"
  declare -F nvm >/dev/null && return 0
  [ -s "$NVM_DIR/nvm.sh" ] || return 1
  set +u; . "$NVM_DIR/nvm.sh"; nvm use default >/dev/null 2>&1; set -u    # nvm.sh 는 nounset 과 충돌
}

# step 이름 검사함수 설치함수 [인자…] — 검사 통과면 건너뛰고, 아니면 설치 후 같은 검사로 확인한다.
step() {
  local n=$1 c=$2 i=$3; shift 3
  if "$c" "$@" >/dev/null 2>&1; then rec ok "$n"; return 0; fi
  if [ "$MODE" = verify ]; then rec MISS "$n"; return 1; fi
  if [ "$DRY" = 1 ]; then rec dry "$n"; echo "  [dry] $n → $i $*"; return 0; fi
  echo "  → $n 설치"
  "$i" "$@"
  if "$c" "$@" >/dev/null 2>&1; then rec new "$n"; return 0; fi
  rec FAIL "$n"; return 1
}

report() {
  local r ok=0 nw=0 ms=0 fl=0 dr=0
  for r in "${RES[@]:-}"; do case ${r%%|*} in ok) ok=$((ok+1));; new) nw=$((nw+1));; MISS) ms=$((ms+1));; FAIL) fl=$((fl+1));; dry) dr=$((dr+1));; esac; done
  log "요약  ✓기존 $ok · ✚신규 $nw · ✗미충족 $ms · ✗실패 $fl$([ "$dr" -gt 0 ] && echo " · 예정 $dr")  (선택: ${SEL[*]:-없음})"
  for r in "${RES[@]:-}"; do case ${r%%|*} in MISS|FAIL) echo "  ✗ ${r#*|}  [${r%%|*}]";; esac; done
  if [ "${#NOTES[@]}" -gt 0 ]; then echo; echo "참고·수동 항목:"; printf '  - %s\n' "${NOTES[@]}"; fi
  [ $((ms+fl)) -eq 0 ]
}

# ───────────────────────── export (이전 PC) ─────────────────────────
do_export() {
  has python3 || { echo "python3 필요"; exit 1; }
  load_nvm 2>/dev/null || true
  local out; out="$(mktemp)"
  {
    echo "# manifest.txt — 'bash bootstrap.sh export' 가 $(hostname) 에서 $(date +%F) 에 생성. 손으로 고치지 말고 다시 export 한다."
    python3 -I - <<'PY'
import re, subprocess
pk = subprocess.run(["apt-mark", "showmanual"], capture_output=True, text=True).stdout.split()
pol = subprocess.run(["apt-cache", "policy", *pk], capture_output=True, text=True).stdout
src, cur = {}, None
for ln in pol.splitlines():
    if ln and not ln.startswith(" "):
        cur = ln.rstrip(":"); src[cur] = set()
    elif cur:
        m = re.match(r"^ {8}\d+ (\S+)", ln)                      # 모든 버전의 저장소 URL (설치 버전이 저장소에서 사라졌을 수 있다)
        if m: src[cur].add(m.group(1))
def origin(urls):
    real = [u for u in urls if not u.startswith("/")]
    if not real: return "local"
    for u in real:                                              # 어느 미러든 루트가 /ubuntu 이거나 ubuntu.com 이면 Ubuntu
        host, _, path = re.sub(r"^https?://", "", u).partition("/")
        if host.endswith("ubuntu.com") or path.startswith("ubuntu"): return "ubuntu"
    return re.sub(r"^https?://([^/]+).*", r"\1", real[0])
ub = [p for p in pk if origin(src.get(p, set())) == "ubuntu"]
ex = [(p, origin(src.get(p, set()))) for p in pk if origin(src.get(p, set())) != "ubuntu"]
print("[apt]"); print("\n".join(ub))
print("[apt-external]"); print("\n".join(f"{p}\t{o}" for p, o in ex))
PY
    echo "[nvm]";       ls "$HOME/.nvm/versions/node" 2>/dev/null | sed 's/^v//'
    echo "[npm]";       npm ls -g --depth=0 2>/dev/null | sed -n 's/.*── //p'
    echo "[pipx]";      pipx list --short 2>/dev/null | awk '{print $1}'
    echo "[uvtool]";    uv tool list 2>/dev/null | awk '!/^-/ && NF{print $1}'
    echo "[uvpython]";  ls "$HOME/.local/share/uv/python" 2>/dev/null | sed -n 's/^cpython-\([0-9]*\.[0-9]*\.[0-9]*\)-.*/\1/p' | sort -u
    echo "[cargo]";     python3 -I -c "import json,os;d=json.load(open(os.path.expanduser('~/.cargo/.crates2.json')))['installs'];print('\n'.join(k.split(' (')[0].replace(' ','@') for k in d))" 2>/dev/null
    echo "[go]";        for f in "$HOME"/go/bin/*; do [ -x "$f" ] && go version -m "$f" 2>/dev/null | awk '$1=="path"{print $2"@latest"; exit}'; done
    echo "[dotnet]";    dotnet tool list -g 2>/dev/null | awk 'NR>2{print $1}'
    echo "[vscode]";    code --list-extensions 2>/dev/null | grep -E '^[A-Za-z0-9-]+\.[A-Za-z0-9._-]+$'   # 첫 실행의 서버 설치 로그가 섞이므로 형식으로 거른다
    echo "[pip-user]";  python3 -m pip list --user --format=freeze 2>/dev/null
    echo "[kv]";        echo "codeql=$(codeql version 2>/dev/null | sed -n 's/.*release \([0-9][0-9.]*[0-9]\).*/\1/p')"
    echo "[repos]"
    find "$HOME" -maxdepth 3 -name .git -not -path '*/node_modules/*' -not -path '*/.claude/plugins/*' -not -path '*/.cache/*' \
         -not -path '*/.nvm/*' -not -path '*/.cargo/*' -not -path '*/.oh-my-zsh/*' 2>/dev/null | sed 's|/\.git$||' | sort |
      while read -r d; do u=$(git -C "$d" remote get-url origin 2>/dev/null | sed -E 's|//[^@/]*@|//|'); [ -n "$u" ] && printf '%s\t%s\n' "${d#"$HOME"/}" "$u"; done
    for g in .claude-vcs .codex-vcs .homecfg-vcs; do u=$(git --git-dir="$HOME/$g" remote get-url origin 2>/dev/null); [ -n "$u" ] && printf '%s\t%s\n' "$g" "$u"; done
    echo "[crontab]";   crontab -l 2>/dev/null
  } > "$out"
  mv "$out" "$MF"
  log "manifest.txt 생성 ($MF)"
  awk '/^\[/{if(s)print "  " s ": " n; s=substr($0,2,length($0)-2); n=0; next} NF&&!/^#/{n++} END{print "  " s ": " n}' "$MF"
  log "이전 PC 에서 새 PC 로 따라가지 않는 변경 (푸시·커밋 필요 여부를 판단하세요)"
  sec repos | while IFS=$'\t' read -r d _; do
    [ -e "$HOME/$d/.git" ] || continue
    a=$(git -C "$HOME/$d" rev-list --count '@{u}..HEAD' 2>/dev/null || echo "?"); n=$(git -C "$HOME/$d" status --short 2>/dev/null | wc -l)
    { [ "$a" = 0 ] && [ "$n" = 0 ]; } || echo "  $d: 미푸시 커밋 $a · 미커밋/미추적 $n  (브랜치 $(git -C "$HOME/$d" branch --show-current))"
  done
  echo; echo "기본 브랜치가 아닌 저장소는 새 PC 가 기본 브랜치를 clone 하므로 내용이 다를 수 있다."
}

# ───────────────────────── 프로젝트 선택 ─────────────────────────
PROJECTS=(gpu docker qmd kg codeql headroom mobius viberank bounty obsidian money math kg-eval site pip-user)
DEFAULT="gpu docker qmd kg codeql headroom bounty obsidian"
declare -A DESC=(
  [gpu]="NVIDIA CUDA 툴킷 (WSL) — kg·qmd GPU 가속"
  [docker]="Docker Desktop 연동 점검 — kg 의 Neo4j 용"
  [qmd]="qmd 검색 — 패치·모델 3개·컬렉션 점검"
  [kg]="knowledge 그래프 + kg-search 서비스 (GPU 휠·모델·Neo4j·적재)"
  [codeql]="CodeQL 번들"
  [headroom]="headroom 프록시 (Docker 배포, Claude 라우팅)"
  [mobius]="mobius — Claude 계정 자동 전환 데몬"
  [viberank]="viberank — 사용량을 외부로 제출 (보안 정책 확인 후)"
  [bounty]="bounty 저장소"
  [obsidian]="obsidian 볼트 저장소"
  [money]="money 저장소" [math]="math 저장소" [kg-eval]="kg-eval — KG 평가셋" [site]="phantomn.github.io 저장소"
  [pip-user]="pip --user 패키지 전체 (impacket 등, --no-deps 로 복원)"
)
declare -A DEPS=([kg]="qmd docker" [kg-eval]="kg" [headroom]="docker")

add_dep() { local d; [[ " ${SEL[*]:-} " == *" $1 "* ]] && return 0; for d in ${DEPS[$1]:-}; do add_dep "$d"; done; SEL+=("$1"); }
select_projects() {
  local saved="$STATE/projects" sel="" p def
  if [ -n "$PICKARG" ]; then
    if [ "$PICKARG" = all ]; then sel="${PROJECTS[*]}"; else sel="${PICKARG//,/ }"; fi
  elif [ "$MODE" = verify ] || [ "$DRY" = 1 ]; then
    sel=$([ -f "$saved" ] && cat "$saved" || echo "$DEFAULT")
  else
    [ -t 0 ] || { echo "대화형 터미널이 아니다 — --projects a,b,c 또는 --all 로 지정"; exit 2; }
    has whiptail || sudo apt-get install -y whiptail >/dev/null
    def=" $([ -f "$saved" ] && cat "$saved" || echo "$DEFAULT") "
    local args=()
    for p in "${PROJECTS[@]}"; do args+=("$p" "${DESC[$p]}" "$([[ $def == *" $p "* ]] && echo ON || echo OFF)"); done
    sel=$(whiptail --title "bootstrap — 설치할 프로젝트" --checklist "스페이스: 선택/해제 · 엔터: 확정 · 의존 항목은 자동 추가" 24 100 15 "${args[@]}" 3>&1 1>&2 2>&3) \
      || { echo "선택 취소"; exit 1; }
    sel=${sel//\"/}
  fi
  for p in $sel; do [[ " ${PROJECTS[*]} " == *" $p "* ]] || { echo "알 수 없는 프로젝트: $p"; exit 2; }; add_dep "$p"; done
  if [ "$MODE" = install ] && [ "$DRY" = 0 ]; then mkdir -p "$STATE"; echo "${SEL[*]}" > "$saved"; fi   # verify·dry-run 은 상태를 쓰지 않는다
}
selected() { [[ " ${SEL[*]:-} " == *" $1 "* ]]; }

# ───────────────────────── 사전 점검 ─────────────────────────
preflight() {
  log "preflight"
  grep -qi microsoft /proc/version || die "WSL2 가 아니다 — 이 스크립트는 WSL2 Ubuntu 전용"
  # shellcheck disable=SC1091
  . /etc/os-release; [ "$VERSION_ID" = 24.04 ] || NOTES+=("Ubuntu $VERSION_ID (기준 24.04)")
  [ "$USER" = phantom ] || NOTES+=("사용자명 '$USER' — ~/.agents 심링크·유닛·크론이 /home/phantom 절대경로라 일부가 끊긴다")
  [ -f "$MF" ] || die "manifest.txt 없음 — 이전 PC 에서 'bash bootstrap.sh export' 후 이 폴더에 복사"
  [ -d /run/systemd/system ] || die "WSL systemd 꺼짐 — /etc/wsl.conf 에 [boot] systemd=true 후 'wsl --shutdown'"
  systemctl --user show-environment >/dev/null 2>&1 || die "사용자 systemd 에 연결 불가 — wsl --shutdown 후 다시 열기"
  local need=60 free; { selected kg || selected qmd; } && need=100
  free=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9); [ "$free" -ge "$need" ] || die "여유 디스크 ${free}G < ${need}G"
  curl -fsS --max-time 10 -o /dev/null https://github.com || die "github.com 에 연결 불가"
  if [ "$MODE" = install ] && [ "$DRY" = 0 ]; then sudo -v || die "sudo 필요"; fi
}

# ───────────────────────── 코어: apt ─────────────────────────
dpkg_has() { dpkg -s "$1" >/dev/null 2>&1; }
apt_one()  { sudo apt-get install -y "$1"; }
apt_missing() { local p; while read -r p; do dpkg_has "$p" || { apt-cache show "$p" >/dev/null 2>&1 && echo "$p"; }; done < <(sec apt); }
apt_ok()   { [ -z "$(apt_missing)" ]; }
apt_add()  { sudo apt-get update; apt_missing | xargs -r sudo apt-get install -y; }
chrome_add() { local d; d=$(mktemp -d); curl -fL -o "$d/c.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo apt-get install -y "$d/c.deb"; }
core_apt() {
  log "apt"
  local p ext o
  for p in git curl zsh whiptail cron; do step "apt:$p" dpkg_has apt_one "$p"; done
  step "apt:pipx(명령)" cmd_ok apt_one pipx          # pip --user 로 깔려 있어도 충족: 요구는 패키지가 아니라 명령
  step "apt:manifest $(sec apt | wc -l)개" apt_ok apt_add || crit "apt 패키지 설치 불완전 — 위 목록 확인"
  mapfile -t ext < <(sec apt-external)
  for p in "${ext[@]}"; do
    IFS=$'\t' read -r p o <<<"$p"
    case $p in
      google-chrome-stable) step "apt:$p" dpkg_has chrome_add "$p";;
      cuda-*|tailscale-*) ;;                                  # cuda=gpu 프로젝트, tailscale=Windows 쪽 사용
      *) dpkg_has "$p" || NOTES+=("수동 설치 필요(출처 $o): $p");;
    esac
  done
}

# ───────────────────────── 코어: 셸·런타임·도구 ─────────────────────────
cmd_ok()   { has "$1"; }
omz_ok()   { [ -d "$HOME/.oh-my-zsh" ]; }
omz_add()  { RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"; }
shell_ok() { [ "$(basename "$(getent passwd "$USER" | cut -d: -f7)")" = zsh ]; }
shell_add(){ chsh -s /usr/bin/zsh; }
nvm_ok()   { [ -s "$HOME/.nvm/nvm.sh" ]; }
nvm_add()  { curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash; }
node_ok()  { load_nvm && nvm ls "$1" >/dev/null 2>&1; }
node_add() { load_nvm && nvm install "$1"; }
nodedef_ok(){ load_nvm && [ "$(nvm version default)" = "v$1" ]; }
nodedef_add(){ load_nvm && nvm alias default "$1" && nvm use "$1" >/dev/null; }
npm_ok()   { load_nvm && npm ls -g --depth=0 2>/dev/null | grep -qF -- "── $1"; }
npm_add()  { load_nvm && npm i -g "$1"; }
uv_add()   { curl -LsSf https://astral.sh/uv/install.sh | sh; }
uvpy_ok()  { uv python list --only-installed 2>/dev/null | grep -q "cpython-$1"; }
uvpy_add() { uv python install "$1"; }
uvtool_ok(){ uv tool list 2>/dev/null | grep -q "^$1 "; }
uvtool_add(){ uv tool install "$1"; }
pipx_ok()  { pipx list --short 2>/dev/null | grep -q "^$1 "; }
pipx_add() { pipx install "$1"; }
rustup_add(){ curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; }
cargo_ok() { cargo install --list 2>/dev/null | grep -q "^$1 v"; }
cargo_add(){ cargo install --locked --version "$2" "$1" || cargo install --locked "$1"; }
go_bin()   { local m=${1%@*} b; b=${m##*/}; if [[ $b =~ ^v[0-9]+$ ]]; then m=${m%/*}; b=${m##*/}; fi; echo "$b"; }
go_ok()    { [ -x "$HOME/go/bin/$(go_bin "$1")" ]; }
go_add()   { go install "$1"; }
dotnet_ok(){ dotnet tool list -g 2>/dev/null | awk 'NR>2{print tolower($1)}' | grep -qx "$(tr 'A-Z' 'a-z' <<<"$1")"; }
dotnet_add(){ dotnet tool install -g "$1"; }
vsc_ok()   { grep -qixF -- "$1" <<<"${VSC_EXT:-}"; }
vsc_add()  { code --install-extension "$1"; }
# GPU 사용 가능 여부 — nvidia-smi 가 죽으면(Windows 드라이버 갱신 후 재부팅 누락 등) 비정상
smi_ok()   { [ -e /dev/dxg ] && nvidia-smi -L >/dev/null 2>&1; }

core_runtimes() {
  log "셸·런타임·도구"
  local x n v IFS_OLD=$IFS arr hi=""
  step "shell:oh-my-zsh" omz_ok omz_add; step "shell:기본 셸 zsh" shell_ok shell_add
  step "node:nvm" nvm_ok nvm_add || crit "nvm 설치 실패"
  mapfile -t arr < <(sec nvm | sort -V); for v in "${arr[@]}"; do step "node:$v" node_ok node_add "$v"; hi=$v; done
  [ -n "$hi" ] && step "node:default=$hi" nodedef_ok nodedef_add "$hi"
  mapfile -t arr < <(sec npm)
  for x in "${arr[@]}"; do
    case $x in corepack@*|npm@*|qmd@*) continue;; @node-llama-cpp/*) smi_ok || continue;; esac   # qmd@0.0.0 는 중복 항목, CUDA 바이너리는 GPU 가 있을 때만
    step "npm:$x" npm_ok npm_add "$x"
  done
  step "py:uv" cmd_ok uv_add uv || crit "uv 설치 실패"
  mapfile -t arr < <(sec uvpython);  for x in "${arr[@]}"; do step "py:$x" uvpy_ok uvpy_add "$x"; done
  mapfile -t arr < <(sec uvtool);    for x in "${arr[@]}"; do step "uvtool:$x" uvtool_ok uvtool_add "$x"; done
  mapfile -t arr < <(sec pipx);      for x in "${arr[@]}"; do step "pipx:$x" pipx_ok pipx_add "$x"; done
  step "rust:rustup" cmd_ok rustup_add rustup || crit "rustup 설치 실패"
  mapfile -t arr < <(sec cargo)
  for x in "${arr[@]}"; do IFS=@ read -r n v <<<"$x"; step "cargo:$n" cargo_ok cargo_add "$n" "$v"; done
  IFS=$IFS_OLD
  has go || crit "go 없음(apt golang-go)"
  mapfile -t arr < <(sec go);        for x in "${arr[@]}"; do step "go:$(go_bin "$x")" go_ok go_add "$x"; done
  if has dotnet; then mapfile -t arr < <(sec dotnet); for x in "${arr[@]}"; do step "dotnet:$x" dotnet_ok dotnet_add "$x"; done
  else NOTES+=("dotnet 없음 — apt 에 dotnet-sdk 가 있었는지 확인"); fi
  if has code; then VSC_EXT=$(code --list-extensions 2>/dev/null); mapfile -t arr < <(sec vscode)
    for x in "${arr[@]}"; do step "vscode:$x" vsc_ok vsc_add "$x"; done
  else NOTES+=("Windows 에 VS Code 설치 후 WSL 에서 'code' 가 잡혀야 확장 $(sec vscode | wc -l)개를 설치할 수 있다"); fi
}

# ───────────────────────── 코어: git·ssh·claude ─────────────────────────
sshkey_ok(){ [ -f "$HOME/.ssh/id_ed25519" ]; }
sshkey_add(){ mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh" && ssh-keygen -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519" -C "$(hostname)"; }
# ssh -T 는 인증에 성공해도 종료코드 1 이고 pipefail 이 있으므로 출력만 본다
ghssh_ok() { local o; o=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1); [[ $o == *"successfully authenticated"* ]]; }
ghssh_add(){ echo "GitHub → Settings → SSH keys 에 등록할 공개키:"; cat "$HOME/.ssh/id_ed25519.pub"; read -rp "등록했으면 Enter: " _; }
ghcli_ok() { gh auth status >/dev/null 2>&1; }
ghcli_add(){ gh auth login; }
gituser_ok(){ [ -n "$(git config --global user.email)" ]; }
gituser_fix(){ echo "git config --global user.name/user.email 설정 필요(회사 계정 분리는 includeIf 권장)"; return 1; }
claude_add(){ curl -fsSL https://claude.ai/install.sh | bash; }
core_git() {
  log "git·ssh·claude"
  step "git:ssh 키" sshkey_ok sshkey_add || crit "ssh 키"
  step "git:GitHub SSH 인증" ghssh_ok ghssh_add || crit "GitHub 인증 없이는 저장소를 받을 수 없다"
  step "git:gh 로그인" ghcli_ok ghcli_add
  step "claude:설치" cmd_ok claude_add claude || crit "claude 설치 실패"
}

# ───────────────────────── 저장소·하네스 ─────────────────────────
repo_url() { sec repos | awk -F'\t' -v d="$1" '$1==d{print $2}'; }
repo_ok()  { local u; u=$(repo_url "$1"); [ -n "$u" ] && [ "$(git -C "$HOME/$1" remote get-url origin 2>/dev/null)" = "$u" ]; }
repo_add() {
  local u; u=$(repo_url "$1"); [ -n "$u" ] || { echo "manifest 에 없는 저장소: $1"; return 1; }
  if [ -e "$HOME/$1" ]; then echo "$HOME/$1 가 이미 있고 원격이 다르다($(git -C "$HOME/$1" remote get-url origin 2>&1)) — 옮기거나 지우세요"; return 1; fi
  mkdir -p "$(dirname "$HOME/$1")" && git clone "$u" "$HOME/$1"
}
STORES=(".claude-vcs|$HOME/.claude" ".codex-vcs|$HOME/.codex" ".homecfg-vcs|$HOME")
store_ok() { git --git-dir="$HOME/$1" rev-parse HEAD >/dev/null 2>&1; }
store_add() {                                   # README 의 bare-sibling 복구(root .git 금지). 덮어쓸 파일은 먼저 백업
  local gd="$HOME/$1" wt=$2 url bk="$HOME/.bootstrap-backup/$1" f
  url=$(repo_url "$1"); [ -n "$url" ] || { echo "manifest 에 $1 원격이 없다"; return 1; }
  mkdir -p "$wt"; git clone --bare "$url" "$gd" || return 1
  git --git-dir="$gd" --work-tree="$wt" config core.bare false
  while read -r f; do [ -e "$wt/$f" ] && { mkdir -p "$bk/$(dirname "$f")"; cp -a "$wt/$f" "$bk/$f"; }; done < <(git --git-dir="$gd" ls-tree -r --name-only HEAD)
  git --git-dir="$gd" --work-tree="$wt" checkout -f || return 1
  case $1 in
    .claude-vcs)  git --git-dir="$gd" config core.hooksPath "$HOME/.claude/git-hooks";;
    .homecfg-vcs) [ -f "$HOME/.config/homecfg/exclude" ] && cp "$HOME/.config/homecfg/exclude" "$gd/info/exclude";;
  esac
}
plugins_ok() { python3 -I - <<'PY'
import json, os, sys
b = os.path.expanduser("~/.claude/plugins"); ok = True
for k, v in json.load(open(b + "/installed_plugins.json"))["plugins"].items():
    for e in v:
        if not os.path.exists(e["installPath"]): print("미설치", k); ok = False
for k, v in json.load(open(b + "/known_marketplaces.json")).items():
    if not os.path.exists(v["installLocation"]): print("마켓 없음", k); ok = False
sys.exit(0 if ok else 1)
PY
}
plugins_add() { bash "$HOME/.claude/plugin-reconcile.sh"; }
mcp_names() { python3 -I -c 'import json,sys;print(" ".join(json.load(open(sys.argv[1]))["servers"]))' "$HOME/.agents/mcp/universal.json"; }
mcp_ok()  { python3 -I -c 'import json,sys;sys.exit(0 if sys.argv[1] in json.load(open(sys.argv[2])).get("mcpServers",{}) else 1)' "$1" "$HOME/.claude.json"; }
mcp_add() { python3 -I - "$1" "$HOME/.agents/mcp/universal.json" <<'PY'
import json, subprocess, sys
name, path = sys.argv[1:3]
sys.exit(subprocess.run(["claude", "mcp", "add-json", "-s", "user", name, json.dumps(json.load(open(path))["servers"][name])]).returncode)
PY
}
mcpdup_ok()  { ! "$HOME/.claude/check-canon.sh" 2>&1 | grep -q '플러그인 이중기동'; }
mcpdup_fix() { "$HOME/.claude/check-canon.sh" --fix-mcp --apply; }
mcpkey_names() { python3 -I -c 'import json,re,sys;print(" ".join(sorted(set(re.findall(r"\$\{([A-Z_0-9]+)", open(sys.argv[1]).read())))))' "$HOME/.agents/mcp/universal.json"; }
mcpkey_ok()  { local k; for k in $(mcpkey_names); do grep -Eq "^(export )?$k=.+" "$HOME/.zshrc.secrets" 2>/dev/null || return 1; done; }
mcpkey_fix() { echo "~/.zshrc.secrets 에 새로 발급한 키를 기입: $(mcpkey_names)  (값은 이전 PC 에서 복사하지 않는다)"; return 1; }
canon_ok()   { "$HOME/.claude/check-canon.sh" >/dev/null 2>&1; }
canon_fix()  { "$HOME/.claude/check-canon.sh" 2>&1 | grep '★' | head -20; return 1; }
core_harness() {
  log "하네스 복구 (~/.agents → ~/.claude·~/.codex·homecfg → 플러그인·MCP)"
  local s n
  step "harness:.agents" repo_ok repo_add .agents || crit ".agents 없이는 하네스를 복구할 수 없다"
  for s in "${STORES[@]}"; do step "harness:${s%%|*}" store_ok store_add "${s%%|*}" "${s#*|}"; done
  step "git:user.email" gituser_ok gituser_fix
  step "harness:플러그인·마켓플레이스" plugins_ok plugins_add
  if [ -f "$HOME/.agents/mcp/universal.json" ]; then
    for n in $(mcp_names); do step "harness:mcp:$n" mcp_ok mcp_add "$n"; done
    step "harness:MCP 이중기동 수복" mcpdup_ok mcpdup_fix
    step "harness:MCP 키(.zshrc.secrets)" mcpkey_ok mcpkey_fix
  fi
  step "harness:게이트(check-canon 위반 0)" canon_ok canon_fix
}

# ───────────────────────── 크론 ─────────────────────────
# 스냅샷에서 (1) 개인 NAS 백업 줄 (2) 새 PC 에 없는 경로를 부르는 줄을 뺀다. $HOME·~·/home/phantom 은 현재 홈으로 바꾼다.
cron_desired() {
  local l ok tok
  secraw crontab | while IFS= read -r l; do
    l=${l//\$HOME/$HOME}; l=${l//\/home\/phantom/$HOME}
    case $l in ''|\#*) echo "$l"; continue;; *backup-nas.sh*) continue;; esac
    ok=1
    for tok in $(grep -oE "$HOME/[A-Za-z0-9_.-]+" <<<"$l" | sort -u); do [ -e "$tok" ] || { ok=0; break; }; done
    [ "$ok" = 1 ] && echo "$l"
  done
}
cron_cur() { crontab -l 2>/dev/null | awk '/^# >>> bootstrap-migrated/{s=1;next} /^# <<< bootstrap-migrated/{s=0;next} s'; }
cron_ok()  { [ "$(cron_cur)" = "$(cron_desired)" ]; }
cron_add() {
  local rest; rest=$(crontab -l 2>/dev/null | awk '/^# >>> bootstrap-migrated/{s=1;next} /^# <<< bootstrap-migrated/{s=0;next} !s')
  printf '%s\n# >>> bootstrap-migrated (bootstrap.sh — 다시 실행하면 이 블록만 교체)\n%s\n# <<< bootstrap-migrated\n' "$rest" "$(cron_desired)" | crontab -
}
core_cron() {
  log "cron"
  systemctl is-active --quiet cron || NOTES+=("cron 서비스가 active 가 아니다 — 'sudo service cron start' / wsl.conf [boot] systemd=true")
  step "cron:이식 블록(스냅샷에서 경로가 있는 줄만)" cron_ok cron_add
}

# ───────────────────────── 프로젝트 ─────────────────────────
unit_put() { mkdir -p "$HOME/.config/systemd/user" && cat > "$HOME/.config/systemd/user/$1" && systemctl --user daemon-reload; }

# --- gpu
smi_fix()    { echo "  nvidia-smi 실패. Windows 쪽 NVIDIA 드라이버를 설치·갱신했다면 재부팅(또는 wsl --shutdown) 후 다시 실행하세요."; return 1; }
cuda_ok()    { [ -e /usr/local/cuda/lib64/libcudart.so.13 ] && [ -e /usr/local/cuda/lib64/libcublas.so.13 ]; }
cuda_add()   { local d; d=$(mktemp -d); curl -fL -o "$d/k.deb" https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb \
                 && sudo dpkg -i "$d/k.deb" && sudo apt-get update && sudo apt-get install -y cuda-toolkit-13-0; }
cudapath_ok(){ grep -q 'cuda/lib64' "$HOME/.zshrc" 2>/dev/null; }
cudapath_add(){ printf '\n# CUDA Toolkit 13 (WSL2)\nexport PATH="/usr/local/cuda/bin:$PATH"\nexport LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"\n' >> "$HOME/.zshrc"; }
p_gpu() {
  [ -e /dev/dxg ] || { NOTES+=("gpu: /dev/dxg 없음 — WSL 이 GPU 를 못 받음(프로젝트 건너뜀)"); return 0; }
  step "gpu:nvidia-smi 동작(Windows 드라이버)" smi_ok smi_fix || return 0
  step "gpu:CUDA 툴킷 13.0" cuda_ok cuda_add
  step "gpu:~/.zshrc 의 CUDA 경로" cudapath_ok cudapath_add
}

# --- docker
docker_fix() { echo "  Windows 에 Docker Desktop 설치 → Settings > Resources > WSL integration 에서 이 배포판 켜기"; return 1; }
p_docker() { step "docker:docker info" cmd_docker docker_fix; }
cmd_docker() { docker info >/dev/null 2>&1; }

# --- qmd (패키지는 코어 npm 단계가 manifest 의 고정 버전으로 설치한다)
QMD_MODELS=(hf_ggml-org_embeddinggemma-300M-Q8_0.gguf hf_ggml-org_qwen3-reranker-0.6b-q8_0.gguf hf_tobil_qmd-query-expansion-1.7B-q4_k_m.gguf)
qmdpatch_ok() { load_nvm && python3 "$HOME/.agents/qmd/apply-patches.py" --check; }     # #993·rerank 결합식. qmd-maintain.sh 가드가 요구
qmdpatch_add(){ load_nvm && python3 "$HOME/.agents/qmd/apply-patches.py"; }
qmdmodel_ok() { local f; for f in "${QMD_MODELS[@]}"; do [ -s "$HOME/.cache/qmd/models/$f" ] || return 1; done; }
qmdmodel_add(){ load_nvm && qmd pull --progress; }
qmdcfg_ok()   { [ -s "$HOME/.config/qmd/index.yml" ]; }
qmdcfg_fix()  { echo "  ~/.config/qmd/index.yml 은 homecfg 가 복원한다 — 하네스 단계 결과 확인"; return 1; }
p_qmd() {
  step "qmd:패치(#993·rerank 결합식)" qmdpatch_ok qmdpatch_add
  step "qmd:모델 3개(~/.cache/qmd/models)" qmdmodel_ok qmdmodel_add
  step "qmd:컬렉션 설정" qmdcfg_ok qmdcfg_fix
  local p
  while read -r p; do p=${p/#\~/$HOME}
    case $p in */.cache/qmd/skill-catalog|*/.claude/qmd-sessions) continue;; esac     # 색인 스크립트가 만드는 디렉터리
    [ -e "$p" ] || NOTES+=("qmd 컬렉션 경로 없음: $p — 저장소를 받거나 index.yml 에서 컬렉션을 빼세요")
  done < <(sed -n 's/^[[:space:]]*path:[[:space:]]*//p' "$HOME/.config/qmd/index.yml" 2>/dev/null)
  NOTES+=("qmd 첫 색인은 수 시간 걸릴 수 있어 자동 실행하지 않음: bash ~/.agents/qmd/qmd-maintain.sh  (로그 ~/.cache/qmd/maintain.log)")
}

# --- kg (knowledge) — 요구 사항은 코드·락·pyproject 에서 읽는다
kgrun()      { ( cd "$KG" && set -a && . ./.env && set +a && "$@" ); }
kgvenv()     { ( cd "$KG" && poetry env info -p 2>/dev/null ); }
kgconst()    { ( cd "$KG" && "$(kgvenv)/bin/python" -c "$1" 2>/dev/null ); }
kgvenv_ok()  { local v; v=$(kgvenv) && [ -x "$v/bin/python" ] && ( cd "$KG" && "$v/bin/python" -c 'import neo4j_graphrag' ); }
kgvenv_add() { ( cd "$KG" && poetry install ); }
llama_ok()   { ( cd "$KG" && "$(kgvenv)/bin/python" -c 'import llama_cpp,sys; sys.exit(0 if llama_cpp.llama_supports_gpu_offload() else 1)' ); }
llama_add()  {   # pyproject.toml 주석: GPU 빌드는 별도 휠. --no-deps 로 numpy 등 락에 고정된 의존성을 건드리지 않는다
  local v idx
  v=$(awk '/^name = "llama-cpp-python"/{f=1} f&&/^version = /{gsub(/"/,"",$3);print $3;exit}' "$KG/poetry.lock")
  idx=$(grep -o 'https://[^ ]*/whl/cu[0-9]*' "$KG/pyproject.toml" | head -1)
  "$(kgvenv)/bin/pip" install --force-reinstall --no-deps "llama-cpp-python==$v" --extra-index-url "${idx:-https://abetlen.github.io/llama-cpp-python/whl/cu130}"
}
egguf_path() { kgconst 'from kg import embed; print(embed._GGUF)' || echo "$HOME/.cache/qmd/models/hf_ggml-org_embeddinggemma-300M-Q8_0.gguf"; }
egguf_ok()   { [ -s "$(egguf_path)" ]; }
egguf_add()  { load_nvm && qmd pull --progress; }
rr_path()    { kgconst 'from kg import search; print(search.RERANKER)' || echo "$HOME/.cache/kg-models/bge-reranker-v2-m3-Q8_0.gguf"; }
rr_ok()      { local p; p=$(rr_path); [ "$(head -c4 "$p" 2>/dev/null)" = GGUF ] && [ "$(stat -c %s "$p")" -gt 100000000 ]; }
rr_add()     { local p; p=$(rr_path); mkdir -p "$(dirname "$p")" && curl -fL -C - -o "$p" https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF/resolve/main/bge-reranker-v2-m3-Q8_0.gguf; }
# .env 는 셸 source·systemd EnvironmentFile·docker compose 세 파서가 읽으므로 비밀번호 문자를 제한한다
kgenv_ok()   { [ -f "$KG/.env" ] && grep -q '^KG_NEO4J_PASSWORD=.\{8,\}' "$KG/.env" && ! grep -q '^KG_NEO4J_PASSWORD=changeme' "$KG/.env" && [ "$(stat -c %a "$KG/.env")" = 600 ]; }
kgenv_add()  {
  local pw; [ -t 0 ] || { echo "대화형 입력 필요"; return 1; }
  until [[ ${pw:-} =~ ^[A-Za-z0-9._@%+=:-]{8,}$ ]]; do read -rsp "Neo4j 비밀번호 (8자 이상, 영문·숫자·._@%+=:- 만): " pw; echo; done
  { grep -v '^KG_NEO4J_PASSWORD=' "$KG/.env.example"; printf 'KG_NEO4J_PASSWORD=%s\n' "$pw"; } > "$KG/.env"; chmod 600 "$KG/.env"
}
kgpatch_text() { cat <<'PATCH'
--- a/kg/embed.py	2026-10-23 14:21:57.560114534 +0900
+++ b/kg/embed.py	2026-10-23 14:21:57.594448162 +0900
@@ -4,7 +4,7 @@
 B: 청크 텍스트 sha256 → 벡터 SQLite 캐시(설계 §7). 안 바뀐 청크 재임베딩 0. 캐시는 재생성 가능이라 git 제외.
 공식 프롬프트(Google AI 모델카드): query=`task: search result | query: `, document=`title: none | text: `."""
 from __future__ import annotations
-import hashlib, os, sqlite3, struct
+import hashlib, os, sqlite3, struct, time
 from functools import cached_property
 from pathlib import Path
 from neo4j_graphrag.embeddings import Embedder
@@ -64,6 +64,13 @@
         return [float(x) for x in self._model.embed(_Q_PREFIX + text)]
 
     def embed_documents(self, texts: list[str]) -> list[list[float]]:
-        out = [self._embed_one(_D_PREFIX + t) for t in texts]
-        self._db.commit()  # 배치 끝에 한 번 커밋
+        # 진행 표시 + 주기 커밋: 오래 걸리는 첫 빌드(캐시 없음)에서 진행이 보이고, 중단해도 캐시가 남아 이어서 한다
+        out, n, t0 = [], len(texts), time.monotonic()
+        for i, t in enumerate(texts, 1):
+            out.append(self._embed_one(_D_PREFIX + t))
+            if i % 1000 == 0 or i == n:
+                self._db.commit()
+                el = time.monotonic() - t0
+                print(f"  임베딩 {i}/{n} ({i / n:.0%}) 경과 {el:.0f}s, 남은 약 {el / i * (n - i):.0f}s", flush=True)
+        self._db.commit()
         return out
--- a/kg/registry.py	2026-10-23 15:07:32.879431294 +0900
+++ b/kg/registry.py	2026-10-23 15:07:32.909983557 +0900
@@ -61,11 +61,11 @@
 
 
 PROJECTS: dict[str, Project] = {
-    "quant": Project(adapter="duckdb",
+    "quant": Project(adapter="duckdb", optional=True,   # 로컬: quant.duckdb(3.5GB, git 제외)가 없는 PC 에서 빌드가 격리(종료코드 3)로 끝나지 않게
         types={"Portfolio": ("id",), "Method": ("id",), "Holding": ("asset", "portfolio")},
         rels=frozenset({"USES_METHOD", "HAS_HOLDING"}),         # 지식→프로젝트(DESCRIBES) 관계는 만들지 않는다 — pf_designed.file 은 원천 .jsonl 이라 문서가 없다(spec §10.2)
         community_rels=frozenset({"USES_METHOD"})),
-    "analysis": Project(adapter="analysis-meta", types={"Challenge": ("slug",)}),
+    "analysis": Project(adapter="analysis-meta", optional=True, types={"Challenge": ("slug",)}),   # 로컬: ~/analysis 가 없는 PC
     "bounty-coverage": Project(optional=True,
         ledger_glob="~/bounty/.claude/tools/coverage/.knowledge/ledger/*.kg.jsonl",
         types={"Target": ("name",), "EntryPoint": ("epKey",), "Sink": ("sinkKey",),
PATCH
}
kgpatch_ok()  { kgpatch_text | git -C "$KG" apply --reverse --check -; }     # 이미 적용됨
kgpatch_add() { kgpatch_text | git -C "$KG" apply - ; }                        # 진행 표시·주기 커밋 + quant·analysis optional
neo_ok()      { [ "$(docker inspect -f '{{.State.Health.Status}}' "${KG_NEO4J_CONTAINER:-knowledge-neo4j}" 2>/dev/null)" = healthy ]; }
neo_add()     { ( cd "$KG" && docker compose -f compose.yaml up -d --wait --wait-timeout 300 ); }
kgbuilt_ok()  { [ -s "$HOME/.cache/kg-build/last-scope.json" ] && kgrun poetry run python -m kg.status; }
kgbuilt_add() { kgrun poetry run python build.py; }
kglink_ok()   { [ "$(readlink "$HOME/.local/bin/kg")" = "$KG/scripts/kg" ]; }
kglink_add()  { mkdir -p "$HOME/.local/bin" && ln -sf "$KG/scripts/kg" "$HOME/.local/bin/kg"; }
kgsvc_ok()    { systemctl --user is-active --quiet kg-search; }
kgsvc_add() {
  local py i; py="$(kgvenv)/bin/python"
  { cat <<EOF
[Unit]
Description=kg.search 상주 서버 (모델·드라이버 상시 적재)
After=docker.service

[Service]
WorkingDirectory=$KG
EnvironmentFile=$KG/.env
Environment=KG_SEARCH_IDLE=0
EOF
    [ -d /usr/local/cuda/lib64 ] && echo "Environment=LD_LIBRARY_PATH=/usr/local/cuda/lib64"   # systemd 서비스는 셸 환경을 물려받지 않는다
    cat <<EOF
ExecStart=$py -m kg.search --serve
Restart=always
RestartSec=1
MemorySwapMax=0
TimeoutStopSec=20

[Install]
WantedBy=default.target
EOF
  } | unit_put kg-search.service
  systemctl --user reset-failed kg-search 2>/dev/null; systemctl --user enable --now kg-search
  for i in $(seq 1 45); do systemctl --user is-active --quiet kg-search && return 0; sleep 2; done
  journalctl --user -u kg-search -n 15 --no-pager; return 1
}
kgq_ok()   { timeout 90 "$HOME/.local/bin/kg" "지식" >/dev/null 2>&1; }
kgq_fix()  { journalctl --user -u kg-search -n 15 --no-pager; return 1; }
p_kg() {
  step "kg:저장소(knowledge ← kg-platform)" repo_ok repo_add knowledge || return 0
  step "kg:poetry 환경" kgvenv_ok kgvenv_add || return 0
  if smi_ok; then step "kg:llama-cpp GPU 휠" llama_ok llama_add
  else NOTES+=("kg: GPU 를 못 쓴다 — 임베딩이 CPU(청크당 약 200ms, 첫 적재 수 시간). gpu 프로젝트를 선택하고 드라이버를 점검하세요"); fi
  step "kg:임베딩 GGUF(코드 상수 embed._GGUF)" egguf_ok egguf_add
  step "kg:리랭커 GGUF(코드 상수 search.RERANKER)" rr_ok rr_add
  step "kg:.env (권한 600)" kgenv_ok kgenv_add || return 0
  step "kg:로컬 패치" kgpatch_ok kgpatch_add
  step "kg:Neo4j 컨테이너 healthy" neo_ok neo_add || return 0
  step "kg:그래프 적재(build.py)" kgbuilt_ok kgbuilt_add
  step "kg:kg CLI 심링크" kglink_ok kglink_add
  step "kg:kg-search 서비스" kgsvc_ok kgsvc_add
  step "kg:질의 시험" kgq_ok kgq_fix
}

# --- codeql
cq_ver()    { sec kv | sed -n 's/^codeql=//p'; }
cq_ok()     { codeql version 2>/dev/null | grep -q "release $(cq_ver)\."; }
cq_add()    { local v; v=$(cq_ver); mkdir -p "$HOME/codeql-home" && ( cd "$HOME/codeql-home" && gh release download "codeql-bundle-v$v" -R github/codeql-action -p codeql-bundle-linux64.tar.gz --clobber && tar xzf codeql-bundle-linux64.tar.gz ) \
               && ln -sf "$HOME/codeql-home/codeql/codeql" "$HOME/.local/bin/codeql"; }
p_codeql()  { step "codeql:번들 $(cq_ver)" cq_ok cq_add; }

# --- headroom (유닛은 headroom 이 생성한다)
# Docker 방식으로 통일한다. systemd 서비스(python)와 섞이면 "Docker deployments must be started by the Docker supervisor"가 반복되며
# 재시작 카운터가 수백까지 오른다(2026-10-23 새 PC 실측 552회). 그래서 유닛이 없고 런타임이 docker 인지까지 검사한다.
hr_rt()     { python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1])).get("runtime_kind",""))' "$HOME/.headroom/deploy/default/manifest.json" 2>/dev/null; }
hr_ok()     { [ "$(hr_rt)" = docker ] && [ ! -e "$HOME/.config/systemd/user/headroom-default.service" ] \
                && [ "$(docker inspect -f '{{.State.Status}}' headroom-default 2>/dev/null)" = running ] \
                && [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/readyz)" = 200 ]; }
hr_add()    {
  systemctl --user disable --now headroom-default.service 2>/dev/null; rm -f "$HOME/.config/systemd/user/headroom-default.service"; systemctl --user daemon-reload
  headroom install remove --profile default >/dev/null 2>&1
  headroom install apply --preset persistent-docker --profile default --port 8787 --providers manual --backend anthropic --mode cache --no-telemetry --no-rate-limit \
    && for _ in $(seq 1 30); do [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/readyz)" = 200 ] && return 0; sleep 3; done; return 1; }
# 이슈 #4207(Docker 가 $HOME 을 root:root 로 만들어 모델 캐시 쓰기 실패)과 NEO4J_/QDRANT_ 자격 복사를 막는 로컬 패치. headroom 업데이트 시 소실되므로 검사한다.
hrpatch_file() { local p; p=$(uv tool dir 2>/dev/null)/headroom-ai; ls "$p"/lib/python3.*/site-packages/headroom/install/runtime.py 2>/dev/null | head -1; }
hrpatch_ok()   { local f; f=$(hrpatch_file); [ -n "$f" ] && grep -q 'HF_HOME={container_home}' "$f" && grep -q MEMORY_BACKEND_ENV_PREFIXES "$f"; }
hrpatch_add()  {
  local f; f=$(hrpatch_file); [ -n "$f" ] || return 1; python3 -I - "$f" <<'PY2'
import sys
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
def sub(a, b):
    global s
    if s.count(a) != 1: sys.exit("앵커 불일치(headroom 버전 변경?): " + a[:40])
    s = s.replace(a, b)
if "MEMORY_BACKEND_ENV_PREFIXES" not in s:
    sub('    "LANGSMITH_",\n)\n', '    "LANGSMITH_",\n)\nMEMORY_BACKEND_ENV_PREFIXES = ("NEO4J_", "QDRANT_")\n')
    sub('        if name.startswith(PASSTHROUGH_ENV_PREFIXES) and name not in runtime_env:\n',
        '        if name.startswith(MEMORY_BACKEND_ENV_PREFIXES) and not manifest.memory_enabled:\n            continue\n        if name.startswith(PASSTHROUGH_ENV_PREFIXES) and name not in runtime_env:\n')
if "HF_HOME={container_home}" not in s:
    sub('        f"HOME={container_home}",\n', '        f"HOME={container_home}",\n        "--env",\n        f"HF_HOME={container_home}/.headroom/cache/huggingface",\n        "--env",\n        f"XDG_CACHE_HOME={container_home}/.headroom/cache",\n')
open(p, "w", encoding="utf-8").write(s)
PY2
}
hrroute_ok(){ python3 -I -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1])).get("env",{}).get("ANTHROPIC_BASE_URL")=="http://127.0.0.1:8787" else 1)' "$HOME/.claude/settings.json"; }
hrroute_fix(){ echo "  ~/.claude/settings.json 의 env.ANTHROPIC_BASE_URL 을 http://127.0.0.1:8787 로 (homecfg 복원 결과 확인)"; return 1; }
p_headroom(){
  step "headroom:docker 연동" cmd_docker docker_fix || return 0
  step "headroom:로컬 패치(#4207)" hrpatch_ok hrpatch_add
  step "headroom:docker 배포(default)·유닛 없음" hr_ok hr_add
  step "headroom:Claude 라우팅(8787)" hrroute_ok hrroute_fix
  NOTES+=("headroom: Docker Desktop 이 꺼져 있으면 프록시가 안 떠 Claude 연결이 거부된다. headroom update 후에는 패치가 사라지므로 verify 로 확인")
}

# --- mobius
mobius_add(){ python3 -m pip install --user --break-system-packages -e "$HOME/mobius-py"; }
mobsvc_ok() { systemctl --user is-active --quiet mobius; }
mobsvc_add(){ unit_put mobius.service <<EOF
[Unit]
Description=Mobius — Claude Code 계정 자동 전환 데몬
After=network-online.target

[Service]
Type=simple
ExecStart=$HOME/.local/bin/mobius auto --watch
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
  systemctl --user enable --now mobius; }
p_mobius()  { step "mobius:저장소" repo_ok repo_add mobius-py && step "mobius:설치(pip -e)" cmd_ok mobius_add mobius && step "mobius:서비스" mobsvc_ok mobsvc_add; }

# --- viberank — 사용량을 외부 서비스로 제출한다. 기본 해제
vr_ok()     { systemctl --user is-enabled --quiet viberank.timer; }
vr_add() {
  local node npx; node=$(ls -d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null | sort -V | tail -1); npx="$(dirname "$(dirname "$(readlink -f "$node")")")/lib/node_modules/npm/bin/npx-cli.js"
  unit_put viberank.service <<EOF
[Unit]
Description=Submit AI coding usage to viberank

[Service]
Type=oneshot
ExecStart=$node $npx -y viberank-cli@latest submit --quiet
EOF
  unit_put viberank.timer <<'EOF'
[Unit]
Description=Daily viberank submission

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl --user enable --now viberank.timer; }
p_viberank(){ load_nvm; NOTES+=("viberank: 매일 AI 코딩 사용량을 외부로 제출한다 — 회사 PC 는 보안 정책 확인 후 사용"); step "viberank:타이머" vr_ok vr_add; }

# --- 저장소만 있는 프로젝트
p_bounty()   { step "bounty:저장소" repo_ok repo_add bounty; NOTES+=("bounty/targets 의 대용량 작업물(APK 등, 약 15GB)은 git 밖 — 필요하면 별도 복사"); selected kg || NOTES+=("bounty: .mcp.json 의 neo4j MCP 는 kg 프로젝트(~/knowledge)가 있어야 동작"); }
p_obsidian() { step "obsidian:저장소" repo_ok repo_add obsidian; NOTES+=("obsidian: Windows 에 Obsidian 앱 설치 후 ~/obsidian 을 볼트로 열기"); }
p_money()    { step "money:저장소" repo_ok repo_add money; }
p_math()     { step "math:저장소" repo_ok repo_add math; }
p_kg_eval()  { step "kg-eval:저장소" repo_ok repo_add kg-eval; }
p_site()     { step "site:저장소" repo_ok repo_add phantomn.github.io; }

# --- pip --user (freeze 는 전이 의존성까지 담으므로 --no-deps 로 resolver 충돌 없이 복원)
pipu_ok()  { python3 -I - "$MF" <<'PY'
import subprocess, sys
want = set()
on = False
for ln in open(sys.argv[1], encoding="utf-8"):
    ln = ln.rstrip("\n")
    if ln.startswith("["): on = ln == "[pip-user]"; continue
    if on and "==" in ln: want.add(ln.split("==")[0].lower().replace("_", "-"))
have = {l.split("==")[0].lower().replace("_", "-") for l in subprocess.run(["python3", "-m", "pip", "list", "--user", "--format=freeze"], capture_output=True, text=True).stdout.splitlines() if "==" in l}
sys.exit(0 if want <= have else 1)
PY
}
pipu_add() { local f; f=$(mktemp); sec pip-user > "$f"; python3 -m pip install --user --break-system-packages --no-deps -r "$f"; }
p_pip_user(){ step "pip-user:$(sec pip-user | wc -l)개" pipu_ok pipu_add; }

# ───────────────────────── selftest ─────────────────────────
# 판정 로직(step 엔진·크론 필터·섹션 파서·의존 선택·go 바이너리 이름)을 임시 디렉터리에서 시험한다. 시스템은 건드리지 않는다.
do_selftest() {
  local T fails=0; T=$(mktemp -d); trap 'rm -rf "$T"' RETURN
  t() { if [ "$2" = "$3" ]; then printf '  \033[32mPASS\033[0m %s\n' "$1"; else printf '  \033[31mFAIL\033[0m %s (기대 [%s] 실제 [%s])\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }
  # 1) step 엔진: 있음→ok, 없음→설치→new, 설치했는데 안 생김→FAIL, verify 는 설치 안 함, dry 는 설치 안 함
  c_f() { [ -e "$T/$1" ]; }; i_mk() { touch "$T/$1"; }; i_no() { :; }
  touch "$T/have"; local R1
  R1=$( RES=(); MODE=install; DRY=0
        step a c_f i_mk have >/dev/null; step b c_f i_mk made >/dev/null; step c c_f i_no nope >/dev/null 2>&1
        printf '%s ' "${RES[@]}" )
  t "step: ok/new/FAIL 분류" "ok|a new|b FAIL|c " "$R1"
  ( MODE=verify; DRY=0; RES=(); step v c_f i_mk vv >/dev/null 2>&1 ); t "verify 는 설치하지 않는다" "no" "$([ -e "$T/vv" ] && echo yes || echo no)"
  ( MODE=install; DRY=1; RES=(); step d c_f i_mk dd >/dev/null 2>&1 ); t "dry-run 은 설치하지 않는다" "no" "$([ -e "$T/dd" ] && echo yes || echo no)"
  # 2) 섹션 파서: 주석·빈 줄 제외, secraw 는 그대로
  printf '[x]\n# c\na\n\nb\n[y]\nz\n' > "$T/mf"
  t "sec: 주석·빈 줄 제외" "a b " "$( MF="$T/mf"; sec x | tr '\n' ' ' )"
  t "secraw: 그대로" "4" "$( MF="$T/mf"; secraw x | wc -l | tr -d ' ' )"
  # 3) 크론 필터: NAS 백업 줄 제거, 없는 경로 줄 제거, /home/phantom·$HOME 은 현재 홈으로
  mkdir -p "$T/home/keep"
  printf '[crontab]\n# 주석\n0 * * * * ls /home/phantom/keep\n1 * * * * ls $HOME/missing\n2 * * * * scripts/backup-nas.sh\n[end]\n' > "$T/cr"
  t "cron: 유지/제거 판정" "# 주석|0 * * * * ls $T/home/keep" "$( HOME="$T/home"; MF="$T/cr"; cron_desired | paste -sd'|' )"
  # 4) 의존 선택: kg 는 qmd·docker 를 끌고 온다 (중복 없이)
  t "의존 선택 closure" "qmd docker kg" "$( SEL=(); add_dep kg; add_dep kg; echo "${SEL[*]}" )"
  # 5) go 모듈 → 바이너리 이름 (버전 접미사 /v2 제거)
  t "go_bin: /v2 접미사" "gitleaks" "$(go_bin github.com/zricethezav/gitleaks/v8@latest)"
  t "go_bin: cmd 하위" "nuclei" "$(go_bin github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest)"
  echo; [ "$fails" -eq 0 ] && echo "selftest: 전부 통과" || echo "selftest: 실패 $fails건"
  return "$fails"
}

# ───────────────────────── 실행 ─────────────────────────
case $MODE in
  export) do_export; exit 0;;
  selftest) do_selftest; exit $?;;
esac
select_projects
preflight
core_apt
core_runtimes
core_git
core_harness
for p in "${PROJECTS[@]}"; do
  selected "$p" || continue
  log "프로젝트: $p — ${DESC[$p]}"
  "p_${p//-/_}"
done
core_cron
[ "$MODE" = verify ] || NOTES+=("claude 로그인(처음 실행 시), SSH 키가 이전 PC 와 같다면 안정된 뒤 새 키로 교체하고 이전 키 폐기")
report
