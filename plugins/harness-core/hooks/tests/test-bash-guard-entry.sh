#!/usr/bin/env bash
# test-bash-guard-entry.sh — 입구(auto-approve-readonly.sh) → bash_guard.py 흐름.
# 1급 불변식: 스위치가 없으면(미설정·off·잘못된 값) 출력이 변경 전 스크립트와 바이트 단위로 같다(spec §3.9).
# 실행: bash test-bash-guard-entry.sh   (종료 0=PASS, 1=FAIL)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../scripts/auto-approve-readonly.sh"
[ -f "$HOOK" ] || { echo "훅을 찾을 수 없다: $HOOK"; exit 1; }

FAILS=0
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILS=$((FAILS+1)); }

# /tmp 는 스크래치로 판정되므로 세계를 임시 루트 밖(이 폴더 아래)에 만든다.
T="$(mktemp -d -p "$HERE")"
trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT
unset HARNESS_BASH_GUARD HARNESS_BASH_GUARD_CLOCK_MARGIN
export HOME="$T/home" XDG_STATE_HOME="$T/state"
mkdir -p "$HOME/data" "$T/repo"
echo k > "$HOME/data/keep.txt"
( cd "$T/repo" && git init -q && mkdir .claude && echo k > keep.txt \
    && printf '{"env":{"HARNESS_BASH_GUARD":"on"}}' > .claude/settings.json )
# transcript 생성 시각 = 세션 시작. 위 파일들은 그 전이라 세션 전 파일이다(시계 여유는 세션 전 쪽으로 기운다).
TR="$T/transcript.jsonl"; : > "$TR"
LOG="$T/state/harness-core/bash-guard.jsonl"

# 입력 JSON — 쉘 인용으로 조립하지 않는다.
mkin() {
    python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]},
        "cwd":sys.argv[2],"session_id":"s-entry","transcript_path":sys.argv[3]}))' "$1" "$HOME" "$TR"
}
# run <훅> <명령> [env 할당...] → stdout (바이트 보존을 위해 파일로)
run() { local h="$1" c="$2"; shift 2; mkin "$c" | env "$@" bash "$h" 2>/dev/null; }
decision() { python3 -c 'import json,sys; s=sys.stdin.read().strip(); print(json.loads(s)["hookSpecificOutput"]["permissionDecision"] if s else "EMPTY")'; }

echo "== 1. 스위치 없음 동일성 (변경 전 스크립트와 바이트 비교) =="
OLDHOOK="$T/old-hook.sh"
( cd "$HERE" && git show "$(git merge-base HEAD origin/main)":plugins/harness-core/hooks/scripts/auto-approve-readonly.sh ) > "$OLDHOOK" \
    || fail "변경 전 스크립트를 꺼내지 못했다"
# 변경 전 스크립트는 $(dirname "$0")/code-read-guard.py 를 찾으므로 같은 폴더에 둔다.
OLDDIR="$T/oldscripts"; mkdir -p "$OLDDIR"
cp "$OLDHOOK" "$OLDDIR/auto-approve-readonly.sh"; cp "$HERE/../scripts/code-read-guard.py" "$OLDDIR/"
CMDS=('ls' 'rm -rf /tmp/x' 'rm -rf ~' 'git reset --hard' 'rmdir d' "echo 'rm -rf ~'" 'git push -f origin main'
      'cat a | grep b' '' 'dd if=a of=b' 'rm -rf src' 'chmod -R 777 /'
      # 변경 전 본문이 set -e 로 무출력·비0 종료하는 경우(rm_targets 무매치 + pipefail) — 종료 코드까지 같아야 한다
      '(rm -rf x)')
i=0
for c in "${CMDS[@]}"; do
    i=$((i+1))
    run "$OLDDIR/auto-approve-readonly.sh" "$c" > "$T/ref.$i"; rrc=$?
    same=1
    for sw in unset off bogus; do
        if [ "$sw" = unset ]; then run "$HOOK" "$c" > "$T/out.$i.$sw"
        else run "$HOOK" "$c" "HARNESS_BASH_GUARD=$sw" > "$T/out.$i.$sw"; fi
        orc=$?
        cmp -s "$T/ref.$i" "$T/out.$i.$sw" || { same=0; fail "[$c] $sw → 변경 전과 바이트 다름"; }
        [ "$rrc" = "$orc" ] || { same=0; fail "[$c] $sw → 종료 코드 $orc (변경 전 $rrc)"; }
    done
    [ "$same" = 1 ] && ok "[$c] 미설정·off·bogus = 변경 전 ($(decision < "$T/ref.$i"), rc $rrc)"
done

echo
echo "== 2. on (세션 env) =="
out="$(run "$HOOK" 'rm -rf ~/data' HARNESS_BASH_GUARD=on)"
d="$(printf '%s' "$out" | decision)"
[ "$d" = deny ] && ok "rm -rf ~/data → deny" || fail "rm -rf ~/data → $d (deny 여야)"
out2="$(run "$HOOK" 'ls' HARNESS_BASH_GUARD=on)"
d="$(printf '%s' "$out2" | decision)"
[ "$d" = allow ] && ok "ls → allow" || fail "ls → $d (allow 여야)"
case "$out$out2" in *'"ask"'*) fail "on 출력에 ask" ;; *) ok "on 출력에 ask 없음" ;; esac

echo
echo "== 3. on (대상 저장소 settings, 세션 env 없음) =="
d="$(run "$HOOK" "rm $T/repo/keep.txt" | decision)"
[ "$d" = deny ] && ok "스위치 저장소의 세션 전 미추적 파일 rm → deny" || fail "저장소 settings 스위치 → $d (deny 여야)"

echo
echo "== 4. 파이썬 기동 실패 → OLD =="
run "$HOOK" 'rm -rf ~/data' > "$T/ref.4"
run "$HOOK" 'rm -rf ~/data' PYTHONHOME=/nonexistent HARNESS_BASH_GUARD=on > "$T/out.4"
if cmp -s "$T/ref.4" "$T/out.4"; then ok "PYTHONHOME 파손 + on → OLD 그대로 ($(decision < "$T/out.4"))"
else fail "PYTHONHOME 파손 → OLD 와 다름 ($(decision < "$T/out.4"))"; fi

echo
echo "== 5. shadow =="
run "$HOOK" 'rmdir d' HARNESS_BASH_GUARD=shadow > "$T/out.5"
cmp -s "$T/ref.5" "$T/out.5" && ok "shadow 출력 = OLD (ask)" || fail "shadow 출력이 OLD 와 다름"
n="$(python3 -c '
import json,sys
try: lines=open(sys.argv[1],encoding="utf-8").read().splitlines()
except FileNotFoundError: lines=[]
print(sum(1 for l in lines if (r:=json.loads(l))["mode"]=="shadow" and r["old_decision"]=="ask"))' "$LOG")"
[ "$n" = 1 ] && ok "기록: shadow·old_decision=ask 1줄" || fail "기록 shadow 줄 수 $n (1 이어야)"

echo
if [ "$FAILS" -eq 0 ]; then echo "✓ bash-guard 입구 ALL PASS"; exit 0; fi
echo "✗ FAIL $FAILS"; exit 1
