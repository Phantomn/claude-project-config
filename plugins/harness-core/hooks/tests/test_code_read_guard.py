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


def make_repo(switch=True):
    root = os.path.realpath(tempfile.mkdtemp())
    files = {"src/a.py": "def foo():\n  pass\n", "logs/x.log": "foo\n",
             "docs/readme.md": "foo\n", "conf/c.yaml": "foo: 1\n"}
    if switch:
        files[".claude/settings.json"] = '{"env": {"HARNESS_CODEREAD_GUARD": "1"}}'
    for rel, body in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(body)
    subprocess.run(["git", "init", "-q", root], check=True)
    return root


def run_hook(cmd, cwd, env=None):
    e = {k: v for k, v in os.environ.items() if k not in ("HARNESS_CODEREAD_GUARD", "CLAUDE_PROJECT_DIR")}
    e.update(env or {})
    r = subprocess.run([sys.executable, SCRIPT], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd}),
        capture_output=True, text=True, timeout=30, env=e)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def main():
    root = make_repo()
    fails = []
    for cmd in BLOCK:
        if not g.judge_command(cmd, root):
            fails.append(f"막아야 하는데 통과: {cmd!r}")
    for cmd in ALLOW:
        hit = g.judge_command(cmd, root)
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
    home = os.path.realpath(tempfile.mkdtemp())
    with open(os.path.join(home, "a.py"), "w") as f:
        f.write("x\n")
    assert run_hook("cat a.py", home) is None
    # 다른 도구·깨진 입력은 무시
    assert run_hook("cat logs/x.log", root) is None

    # ★2026-10-04 회귀: 홈(저장소 밖)에서 연 세션이 스위치 저장소를 읽으면 막는다 — 세션 env 없이
    env_home = {"CLAUDE_PROJECT_DIR": home}
    out = run_hook(f"cd {root} && sed -n 1,5p src/a.py", home, env_home)
    assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", out
    why = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert f'activate_project(project="{root}")' in why, why  # 세션 프로젝트가 아니니 활성화부터
    assert f'projectPath="{root}"' in why, why
    assert run_hook(f"cat {root}/src/a.py", home, env_home)  # 절대경로
    assert run_hook(f"grep -rn foo {root}", home, env_home)  # 재귀
    # 스위치 없는 저장소는 통과 — 세션이 스위치 저장소여도
    off = make_repo(switch=False)
    assert run_hook(f"cat {off}/src/a.py", root, {"CLAUDE_PROJECT_DIR": root}) is None
    assert run_hook("cat src/a.py", off, {"CLAUDE_PROJECT_DIR": off}) is None
    # 세션 env 스위치(=1)는 세션 프로젝트에만 적용 — 다른 저장소로 번지지 않는다
    assert run_hook("cat src/a.py", off, {"CLAUDE_PROJECT_DIR": off, "HARNESS_CODEREAD_GUARD": "1"})
    assert run_hook(f"cat {off}/src/a.py", home, {"CLAUDE_PROJECT_DIR": home, "HARNESS_CODEREAD_GUARD": "1"}) is None
    # --root-if-guarded (guard-read-codefile.sh 가 쓰는 같은 정의)
    cli = lambda p: subprocess.run([sys.executable, SCRIPT, "--root-if-guarded", p], capture_output=True,
                                   text=True, env={"PATH": os.environ["PATH"]}, cwd=home, check=False)
    r = cli(os.path.join(root, "src/a.py"))
    assert r.returncode == 0 and r.stdout.strip() == root, r
    assert cli(os.path.join(off, "src/a.py")).returncode == 1

    if fails:
        print("\n".join(fails))
        sys.exit(1)
    print(f"OK — BLOCK {len(BLOCK)} / ALLOW {len(ALLOW)} / 종단 14")


if __name__ == "__main__":
    main()
