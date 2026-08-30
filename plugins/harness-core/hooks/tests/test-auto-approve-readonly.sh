#!/usr/bin/env bash
# test-auto-approve-readonly.sh — auto-approve-readonly.sh 의 teeth.
#
# ★왜 이 테스트가 존재하는가 (2026-08-30).
#   이 훅은 stdout 으로 **JSON 을 내는 것이 계약**이다. 그런데 결함은 "JSON 이 안 나온다"가
#   아니라 "**특정 입력에서만** 깨진 JSON 이 나온다"는 형태로 왔다. 위험 패턴 매치 시 사유에
#   정규식을 문자열 연결로 박았고(`perl\s+-e`), `\s` 는 JSON 에 없는 이스케이프라 파싱이
#   실패해 훅 출력이 통째 폐기됐다. 미매치 경로(allow)는 리터럴이라 멀쩡했으므로 **무증상**이었다.
#   ⇒ 가드가 가장 필요한 순간에만 조용히 증발했다. 사람이 눈으로 볼 수 있는 종류가 아니다.
#
#   그래서 이 테스트의 1급 불변식은 "**어떤 입력에도 stdout 은 유효 JSON 이거나 비어 있다**"이며,
#   패턴 목록을 소스에서 뽑아 **전수**로 돌린다. 패턴이 추가돼도 자동으로 커버된다 —
#   목록을 여기 복사하면 그것이 또 갈라진다.
#
# 실행: bash test-auto-approve-readonly.sh   (종료 0=PASS, 1=FAIL)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../scripts/auto-approve-readonly.sh"
[ -f "$HOOK" ] || { echo "훅을 찾을 수 없다: $HOOK"; exit 1; }

FAILS=0
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILS=$((FAILS+1)); }

# 입력 JSON 생성 — 쉘 인용으로 조립하지 않는다(테스트가 같은 병에 걸리면 안 된다).
mkin() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1"; }

# 훅 실행 → stdout. env 는 호출자가 넘긴 것만 반영.
run() { mkin "$1" | bash "$HOOK" 2>/dev/null; }

# stdout 이 비었거나 유효 JSON 인가 + permissionDecision 추출
decision() {
    python3 -c '
import json,sys
s=sys.stdin.read().strip()
if not s: print("EMPTY"); sys.exit(0)
try: d=json.loads(s)
except Exception as e: print("BROKEN:"+str(e)); sys.exit(0)
print(d.get("hookSpecificOutput",{}).get("permissionDecision","NODECISION"))'
}

echo "== ① 계약: 모든 위험 패턴에서 stdout 이 유효 JSON 인가 (전수) =="
# 패턴을 소스에서 뽑는다 — 목록 복사 금지(갈라진다).
mapfile -t PATTERNS < <(python3 - "$HOOK" <<'PY'
import re,sys
src=open(sys.argv[1],encoding='utf-8').read()
m=re.search(r'DANGEROUS_PATTERNS=\((.*?)\n\)',src,re.S)
for p in re.findall(r"^\s*'([^']*)'",m.group(1),re.M): print(p)
PY
)
[ "${#PATTERNS[@]}" -gt 0 ] || fail "패턴 목록을 추출하지 못했다"
echo "  (패턴 ${#PATTERNS[@]}개)"

# 정규식을 실제로 매치시킬 구체 명령을 만든다: 메타문자를 그럴듯한 리터럴로 치환.
concrete() {
    python3 -c '
import sys,re
p=sys.argv[1]
s=p
s=s.replace(r"\s+"," ").replace(r"\s"," ")
s=s.replace(".*"," X ")
s=re.sub(r"\[\|\]","|",s)
s=s.replace(r"\.",".").replace(r"\$","$")
s=re.sub(r"\?","",s)
s=re.sub(r"[()]","",s)
print(s)' "$1"
}

for p in "${PATTERNS[@]}"; do
    cmd="$(concrete "$p")"
    out="$(run "$cmd")"
    d="$(printf '%s' "$out" | decision)"
    case "$d" in
        BROKEN:*) fail "패턴 '$p' → 깨진 JSON ($d)" ;;
        ask)      ok "패턴 '$p' → ask" ;;
        EMPTY|allow|deny|NODECISION)
            # 매치 안 됐을 수 있다(구체화 실패). JSON 자체는 유효하므로 계약 위반은 아니다.
            ok "패턴 '$p' → $d (구체화가 매치시키지 못함 — 계약은 준수)" ;;
    esac
done

echo
echo "== ② 회귀: 결함을 낳은 실제 명령들 =="
for c in "perl -e 'select(undef,undef,undef,60)'" \
         "python3 -c 'print(1)'" \
         "node -e 'x'" \
         "ruby -e 'x'" \
         "tee /etc/hosts" \
         "git checkout -- ."; do
    d="$(run "$c" | decision)"
    case "$d" in
        BROKEN:*) fail "회귀: [$c] → $d" ;;
        *)        ok "회귀: [$c] → $d" ;;
    esac
done

echo
echo "== ③ 정상 경로 =="
d="$(run 'ls -la' | decision)";        [ "$d" = "allow" ] && ok "평범한 명령 → allow" || fail "평범한 명령 → $d (allow 여야)"
d="$(run '' | decision)";              [ "$d" = "EMPTY" ] && ok "빈 명령 → 무출력(통과)" || fail "빈 명령 → $d"
d="$(run 'echo "rm -rf /"' | decision)"
case "$d" in BROKEN:*) fail "인용 리터럴 → $d" ;; *) ok "인용 리터럴 rm → $d" ;; esac

echo
echo "== ④ 재귀삭제 경로판정 (대상으로 판정하는가) =="
d="$(run 'rm -rf /' | decision)";                    [ "$d" = "deny" ] && ok "루트 재귀삭제 → deny" || fail "루트 재귀삭제 → $d (deny 여야)"
d="$(run 'rm -rf ~/.git' | decision)";               [ "$d" = "deny" ] && ok ".git 재귀삭제 → deny" || fail ".git 재귀삭제 → $d (deny 여야)"
d="$(run 'rm -rf /tmp/scratch/build' | decision)";   [ "$d" = "allow" ] && ok "스크래치 정리 → allow" || fail "스크래치 정리 → $d (allow 여야)"
# ★8/24 근본fix 회귀: 다른 명령의 인자에 .git 리터럴이 있어도 rm 대상이 아니면 막지 않는다
d="$(run "find . -not -path '*/.git/*' && rm -rf /tmp/x" | decision)"
[ "$d" = "allow" ] && ok "타 명령 인자의 .git 리터럴 → allow" || fail "타 명령 인자의 .git → $d (allow 여야)"

echo
echo "== ⑤ 코드읽기 → codegraph 유도 (HARNESS_CODEREAD_GUARD, 소프트 카운터) =="
# 카운터는 훅 CWD 의 git toplevel/.claude/logs 에 쓰므로 임시 repo 로 격리(실 카운터 무오염).
CRTMP="$(mktemp -d)"; ( cd "$CRTMP" && git init -q )
CF="$CRTMP/.claude/logs/coderead-count"
crund() { ( cd "$CRTMP" && mkin "$1" | HARNESS_CODEREAD_GUARD=1 bash "$HOOK" 2>/dev/null ) | decision; }

rm -f "$CF"
d="$(crund 'cat x.py')"; [ "$d" = allow ] && ok "cat 코드파일 1회 → allow(넛지)" || fail "cat 코드파일 1회 → $d (allow 여야)"
crund 'cat x.py' >/dev/null; crund 'cat x.py' >/dev/null    # 2,3회 소진(카운터=3)
d="$(crund 'cat x.py')"; [ "$d" = deny ] && ok "코드읽기 4회째 → deny(3회 넛지 후)" || fail "코드읽기 4회째 → $d (deny 여야)"

rm -f "$CF"
d="$(crund 'grep pat x.py')";       [ "$d" = allow ] && ok "grep 코드파일 직접 → allow(넛지)" || fail "grep 코드파일 직접 → $d (allow 여야)"
d="$(crund 'cat a.txt | grep pat')"; [ "$d" = allow ] && ok "파이프필터 grep → allow(통과)" || fail "파이프필터 grep → $d (allow 여야)"

rm -f "$CF"
d="$(crund 'sed -n 1,5p x.py')"; [ "$d" = allow ] && ok "sed -n 코드파일 → allow(넛지)" || fail "sed -n 코드파일 → $d (allow 여야)"
d="$(crund 'cat x.txt')";        [ "$d" = allow ] && ok "비코드파일 cat → allow(무개입)" || fail "비코드 cat → $d (allow 여야)"

# opt-in OFF → 코드파일도 무개입(allow). GUARD 미설정.
d="$( ( cd "$CRTMP" && mkin 'cat x.py' | bash "$HOOK" 2>/dev/null ) | decision )"
[ "$d" = allow ] && ok "GUARD off → 코드파일 cat allow(무개입)" || fail "GUARD off → $d (allow 여야)"
rm -rf "$CRTMP"

echo
if [ "$FAILS" -eq 0 ]; then echo "✓ auto-approve-readonly teeth ALL PASS"; exit 0; fi
echo "✗ FAIL $FAILS"; exit 1
