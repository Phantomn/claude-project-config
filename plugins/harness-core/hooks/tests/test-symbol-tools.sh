#!/usr/bin/env bash
# test-symbol-tools.sh — symbol-tools.sh 의 teeth.
# 불변식: ①스위치 꺼짐 = 무개입(빈 출력) ②출력은 비었거나 유효 JSON ③rule 은 .codegraph 있을 때만
#         ④serena/prompt 는 stdin 을 그대로 넘긴다 ⑤도구가 없어도 실패하지 않는다 ⑥hooks.json 이 부르는 모드가 실재한다
# 실행: bash test-symbol-tools.sh   (종료 0=PASS, 1=FAIL)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../scripts/symbol-tools.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAILS=0
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILS=$((FAILS+1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else fail "$1 (기대 '$3', 실제 '$2')"; fi; }

# 가짜 바이너리: stdin 을 받아 표식과 함께 되돌린다
mkdir -p "$T/bin" "$T/idx/.codegraph" "$T/noidx"
printf '#!/bin/sh\necho "serena:$*:$(cat)"\n' > "$T/bin/serena-hooks"
printf '#!/bin/sh\necho "codegraph:$*:$(cat)"\n' > "$T/bin/codegraph"
chmod +x "$T/bin/"*
BASEPATH="/usr/bin:/bin"; command -v jq >/dev/null && BASEPATH="$(dirname "$(command -v jq)"):$BASEPATH"
run() { # run <guard> <mode> <projdir> <path>
    printf '{"prompt":"x"}' | env -i PATH="$4" HOME="$HOME" HARNESS_CODEREAD_GUARD="$1" CLAUDE_PROJECT_DIR="$3" bash "$HOOK" "$2" 2>/dev/null
}
kind() { python3 -c '
import json,sys
s=sys.stdin.read().strip()
if not s: print("EMPTY"); sys.exit()
try: d=json.loads(s).get("hookSpecificOutput",{})
except Exception: print("TEXT:"+s); sys.exit()
print(d.get("permissionDecision") or ("CTX" if "CodeGraph rule" in d.get("additionalContext","") else "JSON"))'; }

echo "① 스위치 꺼짐"
for m in serena prompt rule allow; do check "off/$m" "$(run 0 $m "$T/idx" "$T/bin:$BASEPATH" | kind)" EMPTY; done
echo "② ③ rule·allow"
check "rule/인덱스 있음" "$(run 1 rule "$T/idx" "$BASEPATH" | kind)" CTX
check "rule/인덱스 없음" "$(run 1 rule "$T/noidx" "$BASEPATH" | kind)" EMPTY
check "allow" "$(run 1 allow "$T/idx" "$BASEPATH" | kind)" allow
echo "④ stdin 전달"
check "serena" "$(run 1 serena "$T/idx" "$T/bin:$BASEPATH")" 'serena:activate --client claude-code:{"prompt":"x"}'
check "prompt" "$(run 1 prompt "$T/idx" "$T/bin:$BASEPATH")" 'codegraph:prompt-hook:{"prompt":"x"}'
echo "⑤ 도구 없음"
for m in serena prompt; do
    out="$(run 1 $m "$T/idx" "$BASEPATH")"; rc=$?
    check "missing/$m" "$rc:$(printf '%s' "$out" | kind)" "0:EMPTY"
done
echo "⑥ hooks.json ↔ 모드"
for m in $(grep -o 'symbol-tools.sh\\\?" [a-z]*' "$HERE/../hooks.json" | awk '{print $2}' | sort -u); do
    grep -qE "^    $m\)" "$HOOK" && ok "모드 실재: $m" || fail "hooks.json 이 부르는 모드 없음: $m"
done
[ "$(grep -c 'symbol-tools.sh' "$HERE/../hooks.json")" -ge 4 ] && ok "hooks.json 등록 4건 이상" || fail "hooks.json 등록 부족"

[ "$FAILS" -eq 0 ] && { echo "PASS"; exit 0; } || { echo "FAIL $FAILS"; exit 1; }
