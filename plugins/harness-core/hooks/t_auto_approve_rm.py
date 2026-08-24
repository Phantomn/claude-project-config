#!/usr/bin/env python3
"""t_auto_approve_rm.py — `auto-approve-readonly.sh` 재귀삭제 가드의 이빨.

★막으려는 사고(2026-08-05 실측): 이 훅은 블랙리스트 **미매치 시 allow** 다. 그런데 목록에
  `rm -fr` 리터럴 하나만 있어서 `rm -rf <무엇이든>` 이 **자동 승인**됐다. 철자 하나가 권한
  시스템을 통째로 우회시켰다.

★그렇다고 `rm -rf` 전부를 막으면 스크래치패드 정리까지 걸린다(실제로 걸렸다 — 이 파일을
  만들던 테스트 명령 자체가 차단됐다). ⇒ 판정 축은 **"무엇을 지우는가"** 다.

계약(4단): 복구불가=deny · 저장소 추적 트리=ask · 저장소/스크래치 밖 절대경로=ask · 그 외=통과.
실행: python3 .claude/hooks/t_auto_approve_rm.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "auto-approve-readonly.sh")

ANALYSIS_ENV = {"HARNESS_RM_REPO_DIRS": r"agent|challenges|research|ctf|tools|\.claude"}

CASES = [
    # 복구 수단이 없다 — 확인이 아니라 거부
    ("deny", "rm -rf /"),
    ("deny", "rm -rf ~"),
    ("deny", "rm -rf .git"),
    ("deny", "rm -rf /home/phantom/x/.secrets"),
    ("deny", "sudo rm -rf /*"),
    # 저장소 추적 트리 — git 복구는 되지만 사람이 봐야 한다
    # 기본 프로파일(HARNESS_RM_REPO_DIRS 미설정)의 저장소 트리
    ("ask", "rm -rf src/x"),
    ("ask", "rm -rf docs/y"),
    # ★프로젝트 노브 — analysis 트리는 기본값에 없다. 노브를 넘겨야 ask 가 된다.
    #   (이 2건이 노브 없이는 pass 라는 사실 자체가 "공유 자산에 프로젝트 값을 박으면
    #    다른 프로젝트에서 틀린다"의 증거다 — 2026-08-24 이 플러그인 분리의 근거.)
    ("ask", "rm -rf challenges/anchorwatch/tmp", ANALYSIS_ENV),
    ("ask", "rm -rf tools/x", ANALYSIS_ENV),
    ("pass", "rm -rf challenges/anchorwatch/tmp"),  # 노브 없으면 저장소 트리로 안 본다
    ("ask", "sudo rm -rf /opt/agent"),
    # 저장소·스크래치 밖 절대경로
    ("ask", "rm -rf $HOME/x"),
    # ★통과해야 한다 — 여기서 막으면 과잉 제약이다(에이전트가 자기 임시파일도 못 지운다)
    ("pass", "rm -rf /tmp/claude-1000/xyz/scratchpad"),
    ("pass", "rm -rf build/"),
    ("pass", "git rm --cached f"),  # 다른 명령의 하위명령 rm 은 파일시스템을 지우지 않는다
    ("pass", "rm x.log"),
    ("pass", "ls -la"),
    ("pass", "echo confirm something"),  # 'rm' 이 단어 안에 든 경우
    # ★위양성 회귀 (2026-08-24 실측) — 판정은 rm 의 **대상**만 본다.
    #   헌장: "차단 훅은 명령 문자열이 아니라 대상으로 판정한다. 명령 형태로 막으면
    #   인용부호 안 리터럴에까지 발화한다." 아래 3건이 전부 deny 로 막혀 복구 리허설과
    #   死번들 정리가 3회 중단됐다 — 지우는 대상은 스크래치패드/상대경로였고 `.git`·`.claude`
    #   는 **다른 명령의 인자**에만 있었다.
    ("pass", "rm -rf /tmp/x/drill; find /tmp/x -type f -not -path '*/.git/*'"),
    ("pass", "rm -f a/x.sh b/y.md; git rm -rq --cached .claude/skills/verify/scripts"),
    ("pass", "rm -rf /tmp/x/w && git --git-dir=/tmp/x/vcs log -1"),
    # ↑ 위 3건이 pass 여도 아래 진짜 대상 판정은 살아 있어야 한다(과소 차단 회귀 방지)
    ("ask", "rm -rf .claude/skills/verify/scripts"),
    ("deny", "rm -rf /tmp/x/scratch; rm -rf .git"),
]


def decide(cmd: str, env: dict | None = None) -> str:
    # ★HARNESS_* 는 주변 환경에서 **상속하지 않는다**. 실제 운영에서 프로젝트가 이 노브를
    #   settings.json env 로 항상 설정하므로, 상속하면 "기본 프로파일" 케이스가 조용히
    #   프로젝트 프로파일로 바뀌어 검증이 무의미해진다(2026-08-24 실측: export 한 셸에서
    #   3건이 거짓 실패했고, 그게 곧 거짓 통과도 가능하다는 뜻이다).
    base = {k: v for k, v in os.environ.items() if not k.startswith("HARNESS_")}
    e = {**base, **(env or {})}
    p = subprocess.run(
        ["bash", HOOK],
        capture_output=True,
        text=True,
        env=e,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
    )
    out = p.stdout.strip()
    if not out:
        return "pass"
    try:
        d = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
    except Exception:
        return "?" + out[:60]
    return "pass" if d == "allow" else d


def main() -> int:
    bad = []
    for case in CASES:
        want, cmd = case[0], case[1]
        env = case[2] if len(case) > 2 else None
        got = decide(cmd, env)
        tag = " [knob]" if env else ""
        print(f"  {'✓' if got == want else '✗'} want={want:4s} got={got:5s}  {cmd}{tag}")
        if got != want:
            bad.append(cmd)
    print()
    if bad:
        print(f"✗ teeth FAIL {len(bad)}건: {bad}")
        return 1
    print("✓ teeth 전량 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
