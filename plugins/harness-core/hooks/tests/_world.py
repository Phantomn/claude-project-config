"""bash-guard 테스트 세계: 실제 git·파일시스템으로 세션 전/세션 중 상태를 만든다 (대역 없음, spec D13)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from target_class import Ctx, make_ctx

_DEFAULT = object()


class DockerRes:
    """World 의 실제 docker 자원(이름 볼륨·컨테이너·compose 프로젝트). 이름은 실행마다 고유한 bg<id>."""

    def __init__(self, world: World, name: str) -> None:
        self._w = world
        self.project, self.volume, self.container = name, f"{name}-db", f"{name}-c"
        self.image = ""
        self.compose = False
        self.fresh_volume: str | None = None

    def make_fresh_volume(self) -> None:
        # CreatedAt 은 초 단위라 세션 시작과 같은 초에 만들면 세션 전으로 읽힌다 — 다음 초 이후에 만든다
        time.sleep(max(0.0, int(self._w.session_start) + 1 - time.time()))
        self._w._docker("volume", "create", f"{self.project}-fresh", check=True)
        self.fresh_volume = f"{self.project}-fresh"


class World:
    def __init__(self, worktree: bool = False, docker: bool = False) -> None:
        # 벽시계가 뒤로 가면(WSL2 실측 약 0.5초) 세션 전 파일이 세션 뒤 생성으로 찍혀 분류 테스트가 간헐 실패한다 — 순서가 맞을 때까지 다시 만든다
        for _ in range(3):
            self._create(worktree, docker)
            if self._order_ok():
                return
            self.close()
        raise RuntimeError("시계 불안정 — 세션 전/세션 중 파일의 생성 시각 순서가 3번 연속 어긋났다")

    def _order_ok(self, margin: float = 0.0) -> bool:
        """세션 전 파일 birth < 세션 시작 < 세션 중 파일 birth 가 각각 margin 초 넘게 벌어져 있는가."""
        r, h = self.repo, self.home
        pre = [h, h / "data/a.txt", h / "notes.md", r, r / ".git", r / ".gitignore", r / "src/main.py", r / "README.md",
               r / "build/out.o", r / "local.sqlite", r / "notes_presession.txt", r / ".env"]
        if self._built_worktree:   # 생성 뒤 make_worktree 로 만든 것은 세션 중 항목이라 제외
            pre += [self.wt, self.wt / "local.sqlite"]
        during = [r / "src/probe.ts", r / "out", self.scratch / "s1/x.txt"]
        out = subprocess.check_output(["stat", "-c", "%.9W", "--", *map(str, pre + during)], text=True).split()
        b = [float(x) for x in out]
        if 0.0 in b:
            return False
        return max(b[:len(pre)]) + margin < self.session_start and self.session_start + margin <= min(b[len(pre):])

    def _create(self, worktree: bool, docker: bool) -> None:
        # tmpfs 이면서 임시 루트도 git 저장소도 아닌 곳(생성 시각 지원 실측 2026-10-14)
        base = os.environ.get("XDG_RUNTIME_DIR") or "/dev/shm"
        self.root = tempfile.mkdtemp(prefix="bash-guard-world-", dir=base)
        r = Path(self.root)
        self.home, self.repo, self.scratch, self.out = r / "home", r / "home/proj", r / "scratch", r / "out"
        self.wt = self.out / "wt"
        self.origin = r / "origin.git"
        for d in (self.home, self.scratch, self.out, r / "state"):
            d.mkdir(parents=True)
        self.environ: dict[str, str] = {
            "HOME": str(self.home), "TMPDIR": str(self.scratch), "XDG_STATE_HOME": str(r / "state"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "World", "GIT_AUTHOR_EMAIL": "world@example.invalid",
            "GIT_COMMITTER_NAME": "World", "GIT_COMMITTER_EMAIL": "world@example.invalid",
        }
        self.session_id = str(uuid.uuid4())
        self.docker: DockerRes | None = None
        self._docker_name: str | None = None
        self._built_worktree = worktree
        try:
            self._build(worktree, docker)
        except BaseException:
            self.close()
            raise

    def _build(self, worktree: bool, docker: bool) -> None:
        h, repo = self.home, self.repo
        for rel, text in [("data/a.txt", "a\n"), ("data/db.sqlite", "db\n"), ("data/important.csv", "k,v\n"),
                          ("notes.md", "n\n"), (".ssh/id_ed25519", "key\n")]:
            self._write(h / rel, text)
        self._git("init", "-q", "--bare", "-b", "main", str(self.origin), cwd=self.root)
        repo.mkdir()
        self._git("init", "-q", "-b", "main")
        self._write(repo / ".gitignore", "build/\n.env\n*.sqlite\n")
        self._write(repo / "src/main.py", "print('main')\n")
        self._write(repo / "README.md", "# proj\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")
        self._git("remote", "add", "origin", str(self.origin))
        self._git("push", "-q", "-u", "origin", "main")
        self._git("remote", "set-head", "origin", "main")
        self._write(repo / "README.md", "# proj\nedited before session\n")
        self._write(repo / "build/out.o", "obj\n")
        self._write(repo / "local.sqlite", "local\n")
        self._write(repo / "notes_presession.txt", "n\n")
        self._write(repo / ".env", "SECRET=1\n")
        self._stash("pre", int(time.time()) - 60)
        if worktree:
            self.make_worktree()
            self._write(self.wt / "local.sqlite", "wt local\n")
            self._write(self.wt / "build/out.o", "obj\n")
        if docker:   # 세션 시작(transcript) 전에 — 볼륨·컨테이너는 세션 전 자원
            self.docker = self._make_docker()
        time.sleep(0.02)
        self.transcript = str(Path(self.root) / "transcript.jsonl")
        self._write(Path(self.transcript), "")
        self.session_start = float(subprocess.check_output(["stat", "-c", "%.9W", self.transcript], text=True))
        time.sleep(0.02)
        self._write(repo / "src/probe.ts", "probe\n")
        (repo / "out").mkdir()
        self._write(self.scratch / "s1/x.txt", "x\n")
        self._stash("session", self._in_session_second())

    @staticmethod
    def _write(p: Path, text: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def _in_session_second(self) -> int:
        # reflog 시각은 초 단위라, 세션 시작과 같은 초에 찍히면 '>= 세션 시작' 비교가 깨진다 — 다음 초 이후로
        return max(int(time.time()), int(self.session_start) + 1)

    @staticmethod
    def _dates(epoch: int) -> dict[str, str]:
        d = f"@{epoch} +0000"
        return {"GIT_COMMITTER_DATE": d, "GIT_AUTHOR_DATE": d}

    def _stash(self, msg: str, epoch: int) -> None:
        # stash push 는 파일을 지웠다 다시 만들어 생성 시각을 바꾼다 — stash 커밋을 직접 만들어 store 해 작업 트리를 건드리지 않는다
        env = self._dates(epoch)
        head = self._git("rev-parse", "HEAD", env=env)
        index = self._git("commit-tree", f"{head}^{{tree}}", "-p", head, "-m", f"index on main: {msg}", env=env)
        work = self._commit_file(head, "src/main.py", f"print('{msg}')\n", env, msg=f"On main: {msg}", parents=(head, index))
        self._git("stash", "store", "-m", f"On main: {msg}", work, env=env)

    def _git(self, *args: str, cwd: str | Path | None = None, env: dict[str, str] | None = None,
             stdin: str | None = None) -> str:
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env={**self.environ, **(env or {})},
                              input=stdin, capture_output=True, text=True, check=True).stdout.strip()

    def fmt(self, s: str) -> str:
        for k, v in (("{HOME}", self.home), ("{REPO}", self.repo), ("{SCRATCH}", self.scratch),
                     ("{OUT}", self.out), ("{WT}", self.wt)):
            s = s.replace(k, str(v))
        return s

    def payload(self, command: str, cwd: str = "{REPO}", session_id: str | None = None) -> dict:
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": self.fmt(command)},
                "cwd": self.fmt(cwd), "session_id": session_id or self.session_id, "transcript_path": self.transcript}

    def edit_payload(self, path: str, tool: str = "Edit") -> dict:
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {key: self.fmt(path)},
                "cwd": str(self.repo), "session_id": self.session_id, "transcript_path": self.transcript}

    def ctx(self, budget: float = 5.0, transcript=_DEFAULT, session_id=_DEFAULT,
            environ_extra: dict[str, str] | None = None) -> Ctx:
        payload = {"transcript_path": self.transcript if transcript is _DEFAULT else transcript,
                   "session_id": self.session_id if session_id is _DEFAULT else session_id}
        return make_ctx(payload, {**self.environ, **(environ_extra or {})}, budget)

    def sh(self, cmd: str, cwd: str = "{REPO}") -> str:
        return subprocess.run(self.fmt(cmd), shell=True, cwd=self.fmt(cwd), env=self.environ,
                              capture_output=True, text=True, check=True).stdout

    def clean_tree(self) -> None:
        self._git("reset", "-q", "--hard", "HEAD")

    def dirty_before_session(self, path: str) -> None:
        p = self.fmt(path)
        with open(p, "a", encoding="utf-8") as f:
            f.write("dirty before session\n")
        t = self.session_start - 60
        os.utime(p, (t, t))

    def touch_modify(self, path: str) -> None:
        with open(self.fmt(path), "a", encoding="utf-8") as f:
            f.write("touched in session\n")

    def rewrite_atomic(self, path: str) -> None:
        # Edit 도구처럼 바꿔치기해 생성 시각이 새로 찍히게 한다
        p = self.fmt(path)
        tmp = f"{p}.{uuid.uuid4().hex}.tmp"
        shutil.copyfile(p, tmp)
        os.replace(tmp, p)

    def checkout(self, branch: str, upstream: str | None = None) -> None:
        exists = subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{branch}"], cwd=self.repo,
                                env=self.environ, capture_output=True, check=False).returncode == 0
        self._git("checkout", "-q", *([] if exists else ["-b"]), branch)
        if upstream:
            # 추적 ref 가 없어도 upstream 설정만 남긴다(원격 브랜치 실재와 무관한 push 판정용)
            remote, _, name = upstream.partition("/")
            self._git("config", f"branch.{branch}.remote", remote)
            self._git("config", f"branch.{branch}.merge", f"refs/heads/{name}")

    def drop_origin_head(self) -> None:
        self._git("remote", "set-head", "origin", "-d")

    def remove_remote(self, name: str) -> None:
        self._git("remote", "remove", name)

    def make_worktree(self) -> None:
        self._git("worktree", "add", "-q", "-b", "wt-b", str(self.wt))

    def _commit_file(self, parent: str, name: str, text: str, env: dict[str, str], msg: str = "",
                     parents: tuple[str, ...] = ()) -> str:
        # 작업 트리(세션 전 수정 포함)를 건드리지 않고 parent 위에 파일 하나를 바꾼 커밋을 만든다
        idx = str(Path(self.root) / f"index.{uuid.uuid4().hex}")
        e = {**env, "GIT_INDEX_FILE": idx}
        try:
            self._git("read-tree", parent, env=e)
            blob = self._git("hash-object", "-w", "--stdin", stdin=text, env=e)
            self._git("update-index", "--add", "--cacheinfo", f"100644,{blob},{name}", env=e)
            tree = self._git("write-tree", env=e)
        finally:
            Path(idx).unlink(missing_ok=True)
        ps = [x for q in (parents or (parent,)) for x in ("-p", q)]
        return self._git("commit-tree", tree, *ps, "-m", msg or f"{name}: {text.strip()}", env=env)

    def local_branch(self, name: str, pushed: bool, before_session: bool, extra_unpushed: int = 0,
                     delete_remote: bool = False, squash_merged: bool = False) -> None:
        env = self._dates(int(self.session_start) - 60 if before_session else self._in_session_second())
        fname = f"{name}.txt"
        tip = self._commit_file(self._git("rev-parse", "main", env=env), fname, f"{name}\n", env)
        self._git("branch", name, tip, env=env)
        if pushed:
            self._git("push", "-q", "-u", "origin", name, env=env)
        if squash_merged:
            base = self._git("rev-parse", "refs/remotes/origin/main", env=env)
            # 메시지를 달리해야 브랜치 커밋과 다른 해시가 된다(같으면 스쿼시가 아니라 그 커밋 자체가 main 에 들어감)
            sq = self._commit_file(base, fname, f"{name}\n", env, msg=f"squash {name} (#1)")
            self._git("push", "-q", "origin", f"{sq}:refs/heads/main", env=env)
            self._git("fetch", "-q", "origin", env=env)
        if delete_remote:
            self._git("push", "-q", "origin", "--delete", name, env=env)
            self._git("fetch", "-q", "--prune", "origin", env=env)
        for i in range(extra_unpushed):
            new = self._commit_file(tip, fname, f"{name}\nextra {i + 1}\n", env)
            self._git("update-ref", "-m", f"commit: extra {i + 1}", f"refs/heads/{name}", new, tip, env=env)
            tip = new

    def set_repo_switch(self, value: str, local: bool = False) -> None:
        p = self.repo / ".claude" / ("settings.local.json" if local else "settings.json")
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        data.setdefault("env", {})["HARNESS_BASH_GUARD"] = value
        self._write(p, json.dumps(data))

    def _docker(self, *args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(["docker", *args], cwd=cwd, env=self.environ, capture_output=True, text=True,
                                  timeout=120, check=check)
        except (OSError, subprocess.TimeoutExpired):
            if check:
                raise
            return None

    def _make_docker(self) -> DockerRes | None:
        d = DockerRes(self, f"bg{uuid.uuid4().hex[:12]}")
        self._docker_name = d.project   # 만들다 실패해도 close() 가 이름으로 치운다

        def ok(r: subprocess.CompletedProcess | None) -> bool:
            return r is not None and r.returncode == 0

        if not ok(self._docker("volume", "create", "--label", f"com.docker.compose.project={d.project}", d.volume)):
            return None
        imgs = self._docker("images", "--format", "{{.Repository}}:{{.Tag}}")
        cands = [i for i in (imgs.stdout.split() if ok(imgs) else []) if "<none>" not in i]
        # entrypoint 를 sh 로 바꿔 이미지 고유 시작 스크립트를 건너뛴다. 이미지마다 컨테이너 시작을 시도하므로 앞 5개까지만
        for img in cands[:5]:
            if ok(self._docker("run", "-d", "--pull", "never", "--name", d.container, "-v", f"{self.repo}:/app",
                               "-v", f"{d.volume}:/data", "-w", "/app", "--entrypoint", "sh", img, "-c", "sleep 300")):
                d.image = img
                break
            self._docker("rm", "-f", "-v", d.container)
        else:
            return None
        spec = {"services": {"web": {"image": img, "pull_policy": "never", "entrypoint": ["sh", "-c", "sleep 300"],
                                     "working_dir": "/app", "volumes": [f"{self.repo}:/app", "db:/data"]}},
                "volumes": {"db": {"external": True, "name": d.volume}}}
        self._write(self.out / "compose.yaml", json.dumps(spec))   # JSON 은 YAML 이다 — 경로 따옴표 걱정 없음
        d.compose = ok(self._docker("compose", "-p", d.project, "up", "-d", cwd=self.out))
        return d

    def close(self) -> None:
        name = getattr(self, "_docker_name", None)
        if name:
            # -v: 이미지가 VOLUME 을 선언하면 익명 볼륨이 생긴다(이름 볼륨·external 은 지우지 않음)
            self._docker("compose", "-p", name, "down", "-v", "--remove-orphans", cwd=self.out)
            self._docker("rm", "-f", "-v", f"{name}-c")
            self._docker("volume", "rm", "-f", f"{name}-db", f"{name}-fresh")
            self._docker_name = None
        shutil.rmtree(self.root, ignore_errors=True)
