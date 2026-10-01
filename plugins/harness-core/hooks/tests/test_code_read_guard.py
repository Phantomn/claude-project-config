#!/usr/bin/env python3
"""code-read-guard.py 회귀 테스트. 실행: python3 hooks/tests/test_code_read_guard.py"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "code-read-guard.py")
spec = importlib.util.spec_from_file_location("guard", SCRIPT)
assert spec and spec.loader
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

BLOCK = [
    "grep -n foo src/a.py",
    "grep -rn foo .",
    "grep -rn foo src",
    "rg foo",
    "rg foo src",
    "cat src/a.py",
    "head -n 50 src/a.py",
    "sed -n '1,20p' src/a.py",
    "awk '{print}' src/a.py",
    "cd src && grep foo a.py",
    "timeout 5 grep foo src/a.py",
    "command grep -rn foo src",
    "git grep foo",
    "find . -name '*.py' -exec grep foo {} +",
    "find . -name '*.py' | xargs grep foo",
    "bash -c 'grep foo src/a.py'",
    "grep foo < src/a.py",
    "rg -g '*.py' foo",
    "rg -t py foo",
    "grep -rn --include='*.{ts,py}' foo .",
    "echo $(grep foo src/a.py)",
    "ls\ngrep foo src/a.py",
    "ugrep -rn foo .",
    "cat src/a.py | head",
    "grep -n -A 3 foo src/a.py",
]
ALLOW = [
    "git log | grep foo",
    "cat logs/x.log",
    "grep -rn foo logs",
    "grep -rn --include='*.md' foo .",
    "rg -g '*.yaml' foo",
    "sed -i 's/a/b/' src/a.py",
    "cat > src/b.py <<'EOF'\ngrep foo src/a.py\nEOF",
    'git commit -m "fix grep in a.py"',
    "grep foo /etc/hosts",
    "grep -n foo /nonexistent-outside/x.py",
    'codegraph explore "foo"',
    "ps aux | grep python",
    "ls src | head",
    "head -n 5 docs/readme.md",
    "grep -c foo docs/readme.md",
    "find . -name '*.py'",
    "find . -name '*.md' -exec grep foo {} +",
    "rg --files | grep foo",
    "echo 'unterminated",
    "python3 -m pytest -q",
    "cd /tmp && grep -rn foo .",  # cd 로 저장소 밖 → serena 가 못 보므로 통과
    "cd /etc && cat hosts",
]


def make_repo():
    root = os.path.realpath(tempfile.mkdtemp())
    for rel, body in {"src/a.py": "def foo():\n  pass\n", "logs/x.log": "foo\n",
                      "docs/readme.md": "foo\n", "conf/c.yaml": "foo: 1\n"}.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(body)
    subprocess.run(["git", "init", "-q", root], check=True)
    return root


def run_hook(cmd, cwd):
    r = subprocess.run([sys.executable, SCRIPT], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd}),
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def main():
    root = make_repo()
    fails = []
    for cmd in BLOCK:
        if not g.judge_command(cmd, root, root):
            fails.append(f"막아야 하는데 통과: {cmd!r}")
    for cmd in ALLOW:
        hit = g.judge_command(cmd, root, root)
        if hit:
            fails.append(f"통과해야 하는데 막음: {cmd!r} → {hit}")

    # 종단: deny JSON 형식 + 사유에 serena 호출이 들어가는가
    out = run_hook("grep -n foo src/a.py", root)
    assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", out
    assert "mcp__serena__get_symbols_overview" in out["hookSpecificOutput"]["permissionDecisionReason"]
    # codegraph 인덱스가 있으면 codegraph 안내가 붙는다
    os.makedirs(os.path.join(root, ".codegraph"))
    cg = run_hook("rg foo", root)
    assert cg and "codegraph_explore" in cg["hookSpecificOutput"]["permissionDecisionReason"]
    # git 저장소 밖 cwd 는 전부 통과
    assert run_hook("cat a.py", os.path.realpath(tempfile.mkdtemp())) is None
    # 다른 도구·깨진 입력은 무시
    assert run_hook("cat logs/x.log", root) is None

    if fails:
        print("\n".join(fails))
        sys.exit(1)
    print(f"OK — BLOCK {len(BLOCK)} / ALLOW {len(ALLOW)} / 종단 4")


if __name__ == "__main__":
    main()
