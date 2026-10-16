from __future__ import annotations

import glob
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import shell_parse
from shell_parse import LexError, Mount, Part, expand, lex, literal_args, parse


def words(toks):
    return [t.word.literal() for t in toks if t.kind == "word"]


def redirs(toks):
    return [(t.op, t.fd, t.target.literal() if t.target else None) for t in toks if t.kind == "redir"]


class LexTest(unittest.TestCase):
    def test_single_vs_double_quote(self):
        t = lex("rm -rf '$HOME' \"$HOME\"")
        self.assertEqual(t[2].word.parts, (Part("$HOME", "'"),))
        self.assertEqual(t[3].word.parts, (Part("$HOME", '"'),))

    def test_redirect_attached(self):
        t = lex("echo a>b 2>/dev/null")
        self.assertEqual(words(t), ["echo", "a"])
        self.assertEqual(redirs(t), [(">", None, "b"), (">", 2, "/dev/null")])

    def test_fd_needs_adjacency(self):
        t = lex("echo 2 >x")
        self.assertEqual(words(t), ["echo", "2"])
        self.assertEqual(redirs(t), [(">", None, "x")])

    def test_fd_dup_is_not_separator(self):
        t = lex("echo a 2>&1 >out")
        self.assertNotIn("&", [x.op for x in t if x.kind == "op"])
        self.assertEqual(redirs(t), [(">&", 2, "1"), (">", None, "out")])

    def test_operators(self):
        self.assertEqual(
            [x.op for x in lex("a && b || c; d | e |& f & g") if x.kind == "op"],
            ["&&", "||", ";", "|", "|&", "&"],
        )

    def test_comment(self):
        self.assertEqual(words(lex("echo x # rm -rf ~")), ["echo", "x"])

    def test_substitution_stays_in_word(self):
        self.assertEqual(
            words(lex('echo "$(rm -rf "a b")" `ls`')), ["echo", '$(rm -rf "a b")', "`ls`"]
        )

    def test_extglob_stays_in_word(self):   # bash(extglob)는 `!(…)`·`@(…)` 를 단어로 읽는다(명령 자리 포함, 실측)
        self.assertEqual(words(lex("rm -rf !(keep) src/@(a|b).py +(x) *(y) ?(z)")),
                         ["rm", "-rf", "!(keep)", "src/@(a|b).py", "+(x)", "*(y)", "?(z)"])
        self.assertEqual(parse("(( y = 2*(1+2) )); echo $y", "/", {}).error, None)

    def test_dq_substitution_body_is_raw(self):
        w = lex('"$(echo \\" ; rm x ; echo \\")"')[0].word
        self.assertEqual(w.parts, (Part('$(echo \\" ; rm x ; echo \\")', '"'),))
        self.assertIn("rm", [t.word.literal() for t in lex(w.literal()[2:-1]) if t.kind == "word"])
        self.assertEqual(lex('"a\\"b\\\\c"')[0].word.literal(), 'a"b\\c')

    def test_heredoc_body(self):
        t = lex("cat <<'EOF' > f\nrm -rf ~\nEOF\necho done")
        hd = next(x for x in t if x.kind == "redir" and x.op == "<<")
        self.assertEqual(hd.body, "rm -rf ~")
        self.assertTrue(hd.target.is_quoted())
        self.assertEqual(words(t), ["cat", "echo", "done"])

    def test_heredoc_dash_strips_tabs(self):
        self.assertEqual([x.body for x in lex("cat <<-EOF\n\tx\n\tEOF\n") if x.kind == "redir"], ["\tx"])

    def test_unterminated(self):
        for s in ['echo "a', "echo 'a", "echo $(a", "cat <<EOF\nx\n"]:
            with self.assertRaises(LexError):
                lex(s)

    def test_large_heredoc_is_linear(self):  # Review Focus 1
        body = "print('rm -rf /')\n" * 12000
        t0 = time.perf_counter()
        lex("python3 - <<'PY'\n" + body + "PY\n")
        self.assertLess(time.perf_counter() - t0, 0.05)


def segs(cmd, cwd="/w", env=None):
    return parse(cmd, cwd, env or {"HOME": "/h"}).segments


def rm_cwd(cmd):
    return next(x.cwd for x in segs(cmd) if x.name == "rm")


def names(cmd):
    return [s.name for s in segs(cmd)]


class ParseTest(unittest.TestCase):
    def test_split_and_cd_tracking(self):
        self.assertEqual([(x.name, x.cwd) for x in segs("cd / && rm x; cd usr; rm y") if x.name == "rm"], [("rm", "/"), ("rm", "/usr")])   # cd 는 있는 폴더라야 성공한다

    def test_subshell_restores(self):
        self.assertEqual([x.cwd for x in segs("(cd /usr; rm x); rm y") if x.name == "rm"], ["/usr", "/w"])

    def test_cd_unknown(self):
        self.assertIsNone(rm_cwd("cd -; rm y"))
        self.assertEqual([x.cwd for x in segs("cd; rm y", env={"HOME": "/tmp"}) if x.name == "rm"], ["/tmp"])
        self.assertEqual([x.cwd for x in segs("cd ~/bin; rm y", env={"HOME": "/usr"}) if x.name == "rm"], ["/usr/bin"])
        self.assertIsNone(rm_cwd("cd $X; rm y"))

    def test_assignments_recorded(self):
        rm = segs('X=/a; export Y=/b; declare -x Z=$(date); rm "$X"')[-1]
        self.assertEqual(rm.env["X"], "/a")
        self.assertEqual(rm.env["Y"], "/b")
        self.assertIsNone(rm.env["Z"])

    def test_wrappers_stripped(self):
        for c in [r"\rm -rf x", "/bin/rm -rf x", "sudo -u root rm -rf x", "env -i A=1 rm -rf x", "command rm x", "timeout 5 rm x",
                  "nice -n 5 rm x", "nohup rm x", "time -p rm x", "stdbuf -oL rm x", "flock /tmp/l rm x", "doas rm x", "exec rm x",
                  "builtin rm x", "ionice -c3 rm x", "chronic rm x", "X=1 rm -rf x", "timeout -s KILL 5 sudo nice rm x"]:
            self.assertEqual(names(c), ["rm"], c)

    def test_prefix_assignment(self):
        a, b = segs('X=/a rm "$X"; rm "$X"')
        self.assertEqual(a.name, "rm")
        self.assertNotIn("X", a.env)  # 같은 줄 단어는 할당 전 env 로 확장된다(리뷰 라운드 4)
        self.assertNotIn("X", b.env)

    def test_git_dash_c(self):
        s = segs("git -C /r reset --hard")[0]
        self.assertEqual((s.name, s.cwd, [w.literal() for w in s.argv]), ("git", "/r", ["git", "reset", "--hard"]))
        self.assertEqual(segs("git -C /r -C sub status")[0].cwd, "/r/sub")

    def test_redirects_removed_from_argv(self):
        s = segs("rm -rf build 2>/dev/null")[0]
        self.assertEqual([w.literal() for w in s.argv], ["rm", "-rf", "build"])
        self.assertEqual(s.redirects[0].fd, 2)

    def test_parse_error_reported(self):
        self.assertIsNotNone(parse('rm -rf "x', "/w", {}).error)
        self.assertIsNotNone(parse("rm x )", "/w", {}).error)

    def test_assignment_after_wrapper(self):
        self.assertEqual(names("sudo X=1 rm -rf x"), ["rm"])
        self.assertNotIn("X", segs("sudo X=1 rm x")[0].env)
        self.assertNotIn("X", segs("sudo X=1 rm x; rm y")[1].env)

    def test_wrapper_options_do_not_leak(self):
        for c in ["command -p rm x", "command -- rm x", "exec -a n rm x", "exec -c rm x", "doas -u root rm x", "doas -n rm x"]:
            self.assertEqual(names(c), ["rm"], c)
        self.assertEqual(names("command -v rm"), ["command"])
        self.assertEqual(names("command -pv rm"), ["command"])

    def test_control_words_stripped(self):
        for c in ["{ rm -rf x; }", "if true; then rm x; fi", "for i in a b; do rm x; done", "while true; do rm x; done", "! rm x",
                  "until false; do rm x; done", "if a; then b; elif c; then rm x; else d; fi"]:
            n = names(c)
            self.assertIn("rm", n, c)
            self.assertFalse({"{", "}", "!", "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "for"} & set(n), c)

    def test_brace_group_is_not_subshell(self):
        self.assertEqual([x.cwd for x in segs("{ cd /usr; rm x; }; rm y") if x.name == "rm"], ["/usr", "/usr"])

    def test_pipeline_and_background_are_subshells(self):
        self.assertEqual(rm_cwd("cd /a | cat; rm y"), "/w")
        self.assertEqual(rm_cwd("cat | cd /a; rm y"), "/w")
        self.assertEqual(rm_cwd("cd /a & rm y"), "/w")
        self.assertEqual(rm_cwd("cd /usr && rm x | cat"), "/usr")
        self.assertEqual(rm_cwd("cd / && cat | wc; rm y"), "/")

    def test_group_inside_pipeline(self):
        for c in ["cat | (cd /usr; rm x); rm y", "cat | { cd /usr; rm x; }; rm y"]:
            self.assertEqual([x.cwd for x in segs(c) if x.name == "rm"], ["/usr", "/w"], c)
        self.assertEqual([x.cwd for x in segs("{ cd /usr; rm x; } | cat; rm y") if x.name == "rm"], ["/usr", "/w"])


class ControlFlowMergeTest(unittest.TestCase):   # 재검토 Out-of-Scope 1: 조건부·0회 실행 본문의 변화는 '안 함' 경로와 합친다
    def last_rm(self, cmd):
        return [x for x in segs(cmd) if x.name == "rm"][-1]

    def test_conditional_changes_are_merged(self):
        for c in ("f=..; if false; then f=nothing; fi; rm $f", "f=..; t && f=nothing; rm $f",
                  "f=..; while false; do f=nothing; done; rm $f", "f=..; until t; do f=nothing; done; rm $f",
                  "f=..; for x in $(ls); do f=nothing; done; rm $f", "f=..; select x in a; do f=nothing; done; rm $f",
                  "f=..; if a; then if b; then f=x; fi; fi; rm $f", "f=..; if a; then f=x; elif b; then f=y; fi; rm $f",
                  "f=..; a && { f=x; } || b; rm $f", "f=..; a || b && f=x; rm $f"):
            self.assertIsNone(self.last_rm(c).env.get("f", "unset"), c)
        for c in ("if t; then cd /a; fi; rm y", "t && cd /a; rm y", "cd /a && cd b; rm y", "while t; do cd /a; done; rm y",
                  "if a; then while b; do cd /c; done; fi; rm y"):
            self.assertIsNone(self.last_rm(c).cwd, c)

    def test_known_paths_stay_precise(self):
        self.assertEqual(self.last_rm("f=a; if t; then f=a; fi; rm $f").env["f"], "a")
        self.assertEqual(self.last_rm("if t; then f=1; else f=1; fi; rm $f").env["f"], "1")
        self.assertEqual(self.last_rm("f=a; if t; then f=b; else rm $f; fi").env["f"], "a")   # else 는 조건 뒤 상태에서
        self.assertEqual(self.last_rm("f=a; if t; then f=b; elif u; then rm $f; fi").env["f"], "a")
        self.assertEqual(self.last_rm("f=a; if g=1; then rm $g; fi").env["g"], "1")   # 조건은 늘 실행된다
        self.assertEqual(self.last_rm("f=..; echo | if a; then f=x; fi; rm $f").env["f"], "..")   # 파이프 구성원은 서브셸
        for c, cwd in (("if cd /a; then rm x; fi", "/a"), ("cd /a && cd b && rm x", "/a/b"), ("cd /a || exit; rm y", "/a"),
                       ("while cd /; do x; done; rm y", "/"), ("(cd /a && cd b); rm y", "/w"), ("cd / && t || u; rm y", "/"),
                       ("cd /usr; if t; then rm x; fi", "/usr"), ("for i in a b; do cd /usr; done; rm y", "/usr")):
            self.assertEqual(self.last_rm(c).cwd, cwd, c)
        self.assertEqual(names("if a; then rm x; elif b; then rm y; else rm z; fi"), ["a", "rm", "b", "rm", "rm"])

    def test_assume_success_left_side(self):   # fix-brief-3 항목 1: 실패 경로가 사실상 없는 좌변은 합류에서 실패 끝을 뺀다
        with tempfile.TemporaryDirectory(dir=os.environ.get("XDG_RUNTIME_DIR") or "/dev/shm") as d:
            Path(d, "ex").mkdir()
            Path(d, "file").touch()
            env = {"HOME": d, "TMPDIR": d}

            def last(c):
                return [x for x in parse(c.replace("{D}", d), d, env).segments if x.name == "rm"][-1]
            # bash: true 는 늘 성공 — `||` 우변은 돌지 않는다
            self.assertEqual(last("f=..; true || f=nothing; rm $f").env["f"], "..")
            self.assertEqual(last("f=..; : || f=x && g=1; rm $f").env["f"], "..")
            for c, cwd in (("mkdir -p {D}/n && cd {D}/n && t; rm y", f"{d}/n"), ("mkdir -p {D}/a/b && cd {D}/a; rm y", f"{d}/a"),
                           ("cd {D}/ex && t; rm y", f"{d}/ex"), ("mkdir {D}/n2 && cd n2; rm y", f"{d}/n2"),
                           ("T=$(mktemp -d) && cd $T && t; rm y", f"{d}/{shell_parse._MKTEMP_NAME}"), ("cd; cd ex && t; rm y", f"{d}/ex"),
                           ("echo a && printf b && true && : && export X=1 && cd ex; rm y", f"{d}/ex")):
                self.assertEqual(last(c).cwd, cwd, c)
            for c, v in (("cd {D}/ex && f=a; rm $f", "a"), ("cd ex && T=$(mktemp -d) && f=a; rm $f", "a"),
                         ("declare f=a && local g=1 && readonly h=2 && cd ex; rm $f", "a")):
                self.assertEqual(last(c).env.get("f"), v, c)
            # 실패 경로가 실재하는 좌변은 그대로 합친다
            for c in ("[ -d x ] && cd {D}/ex; rm y", "t && cd {D}/ex; rm y", "cd {D}/missing && t; rm y", "cd {D}/file && t; rm y",
                      "mkdir {D}/ex && cd {D}/ex; rm y", "mkdir -p {D}/file && cd {D}/file; rm y", "mkdir {D}/no/sub && cd {D}/no/sub; rm y",
                      "! [ -d x ] && cd {D}/ex; rm y", "echo x > {D}/o && cd {D}/ex; rm y", "F=$(cat x) && cd {D}/ex; rm y",
                      "T=$(mktemp) && cd $T; rm y", "cd $U && t; rm y", "cd - && t; rm y", "{ true; } && cd {D}/ex; rm y",
                      "echo | true && cd {D}/ex; rm y", "cd {D}/ex && cd nope; rm y"):
                self.assertIsNone(last(c).cwd, c)
            self.assertIsNone(last("cd {D}/missing && f=a; rm $f").env.get("f"))
            self.assertEqual(last("! true && cd {D}/ex; rm y").cwd, d)   # bash: `! true` 는 실패 — cd 는 돌지 않는다
            # 실패한 cd 뒤 `||` 우변은 cd 전 폴더에서 돈다
            for c in ("cd {D}/missing || rm y", "cd {D}/missing 2>/dev/null || rm y", "cd {D}/ex 2>/dev/null || rm y"):
                self.assertEqual(last(c).cwd, d, c)
            self.assertEqual(names("true || rm x; rm y"), ["true", "rm", "rm"])   # 도달 못 하는 우변도 단위는 판정한다

    def test_source_venv_activate(self):   # fix-brief-3 항목 2: activate 는 자기 변수만 바꾼다
        rm = self.last_rm("f=a; VIRTUAL_ENV=/v; PATH=/p; source .venv/bin/activate; rm $f")
        self.assertEqual(rm.env["f"], "a")
        self.assertIsNone(rm.env["VIRTUAL_ENV"])
        self.assertIsNone(rm.env["PATH"])
        self.assertIsNone(self.last_rm("f=a; source ./env; rm $f").env["f"])

    def test_unbalanced_is_parse_error(self):
        for c in ("fi", "if true; fi", "if true; then x", "then x", "done", "while t; done", "do x; done", "if t; then x; done",
                  "{ if t; then x; }; fi", "if t; then x; else y; elif z; then w; fi", "while t; do x; fi",
                  "case a in a) if t; then x;; esac; fi", "for i in a b; do x; fi"):
            self.assertIsNotNone(parse(c, "/w", {}).error, c)

    def test_large_input_is_linear(self):
        for c in ("if a; then f=$i; fi\n" * 4000, "a && " * 4000 + "b", "a || b && " * 2000 + "c",
                  "if a; then " * 400 + "b" + "; fi" * 400, "while a; do " * 400 + "b" + "; done" * 400):
            t0 = time.perf_counter()
            self.assertIsNone(parse(c, "/w", {}).error)
            self.assertLess(time.perf_counter() - t0, 1.0, c[:30])


class PathSetTest(unittest.TestCase):   # fix-brief-4: 구문별 실행 경로 집합을 한 곳(outcome/collect/join)에서 다룬다
    def test_extglob_in_command_position_is_parse_error(self):   # NB1: extglob 꺼진 bash 는 `!(cmd)` 를 부정 서브셸로 실행한다
        for c in ("!(rm -rf src)", "true && !(rm -rf src)", "if !(rm src); then :; fi", "@(echo y > f)", "+(x)",
                  "!(cd /a) && t", "?(rm x)", "*(rm x)", "a; !(rm x)"):
            self.assertIsNotNone(parse(c, "/w", {}).error, c)
        for c in ("rm -rf !(keep)", "x=@(a); rm x", "echo '!(x)'", "[[ a == @(a|b) ]] && rm x", "echo $(( 2*(3) ))",
                  "f() { :; }", "! (rm x)", "a=$((2*(3))) b", "echo @(a)"):
            self.assertIsNone(parse(c, "/w", {}).error, c)

    def test_time_and_bang_before_compound(self):   # NB8: `time`·`!` 뒤 복합 명령은 벗기고 정상 해석한다
        for c in ("time if true; then rm x; fi", "time while t; do rm x; done", "time for i in a; do rm x; done",
                  "time { rm x; }", "time ( rm x )", "time case a in a) rm x;; esac", "time until t; do rm x; done",
                  "! { rm x; }", "! if t; then rm x; fi", "time -p rm x", "time -p { rm x; }", "t && time if a; then rm x; fi",
                  "time rm x | cat"):
            self.assertIn("rm", names(c), c)
            self.assertNotIn("time", names(c), c)
        self.assertEqual(names("echo time if"), ["echo"])

    def _world(self):
        d = tempfile.mkdtemp(dir=os.environ.get("XDG_RUNTIME_DIR") or "/dev/shm")
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        Path(d, "ex").mkdir()

        def last(c):
            return [x for x in parse(c.replace("{D}", d), d, {"HOME": d, "TMPDIR": d}).segments if x.name == "rm"][-1]
        return d, last

    def test_condition_failure_path(self):   # NB3: if/while/until 조건의 cd 실패 경로는 cd 전 상태에서 시작·합류한다
        d, last = self._world()
        for c in ("if cd {D}/missing; then :; fi; rm y", "while cd {D}/missing; do break; done; rm y",
                  "until cd {D}/missing; do break; done; rm y", "if t; then :; elif cd {D}/missing; then :; fi; rm y",
                  "if cd {D}/missing; then :; elif cd {D}/ex; then :; fi; rm y", "if [ -d x ]; then cd {D}/ex; fi; rm y"):
            self.assertIsNone(last(c).cwd, c)
        for c, cwd in (("if ! cd {D}/missing; then rm y; fi", d), ("if cd {D}/missing; then :; else rm y; fi", d),
                       ("if cd {D}/ex; then rm y; fi", f"{d}/ex"), ("if cd {D}/ex; then :; fi; rm y", f"{d}/ex"),
                       ("if true; then cd {D}/ex; fi; rm y", f"{d}/ex"), ("while cd {D}/ex; do break; done; rm y", f"{d}/ex"),
                       ("until cd {D}/ex; do :; done; rm y", f"{d}/ex"), ("if cd {D}/missing; then rm y; fi", f"{d}/missing"),
                       ("if ! cd {D}/ex; then :; fi; rm y", f"{d}/ex"), ("while ! cd {D}/ex; do :; done; rm y", f"{d}/ex")):
            self.assertEqual(last(c).cwd, cwd, c)

    def test_sequential_failed_cd(self):   # OS1: `;`·줄바꿈 뒤에서도 실패한 cd 의 두 경로(cd 전·cd 뒤)를 합친다
        d, last = self._world()
        for c in ("cd {D}/missing; rm y", "cd {D}/missing\nrm y", "cd {D}/missing; cd ..; rm y", "cd {D}/missing; true && rm y",
                  "cd {D}/missing 2>/dev/null; rm y", "cd {D}/missing; cd ex; rm y", "pushd {D}/missing; rm y"):
            self.assertIsNone(last(c).cwd, c)
        for c, cwd in (("cd {D}/ex; rm y", f"{d}/ex"), ("mkdir -p {D}/n; cd {D}/n; rm y", f"{d}/n"), ("cd {D}/missing; cd {D}/ex; cd; rm y", d), ("cd {D}/missing; cd {D}/ex; rm y", f"{d}/ex"),
                       ("true; cd {D}/ex; rm y", f"{d}/ex"), ("f=1; rm y", d)):
            self.assertEqual(last(c).cwd, cwd, c)
        self.assertEqual(last("f=a; echo; rm $f").env["f"], "a")

    def test_exit_ends_path(self):   # OS6: exit 으로 끝나는 갈래·그룹은 합류에서 빠진다(서브셸 안 exit 은 서브셸만 끝낸다)
        d, last = self._world()
        for c, cwd in (("cd {D}/missing || { echo no; exit 1; }; rm y", f"{d}/missing"), ("cd {D}/ex || { exit 1; }; rm y", f"{d}/ex"),
                       ("if cd {D}/missing; then :; else exit 1; fi; rm y", f"{d}/missing"),
                       ("cd {D}/missing || exit; rm y", f"{d}/missing"), ("(cd {D}/missing || exit); rm y", d),
                       ("if t; then exit; fi; rm y", d), ("cd {D}/missing || { cd {D}/ex || exit 1; }; rm y", None),
                       ("{ cd {D}/missing || exit 1; }; rm y", f"{d}/missing"), ("exit 1 | cat; rm y", d)):
            self.assertEqual(last(c).cwd, cwd, c)
        self.assertEqual(names("exit; rm x; { exit; }; rm y"), ["exit", "rm", "exit", "rm"])   # 도달 못 해도 단위는 판정


def ex(word_src, cwd="/w", env=None):
    s = parse("x " + word_src, cwd, env or {"HOME": "/h"}).segments[0]
    return expand(s.argv[1], s)


class ExpandTest(unittest.TestCase):
    def test_expand_basic(self):
        self.assertEqual(ex("~/x"), ["/h/x"])
        self.assertEqual(ex('"$HOME/x"'), ["/h/x"])
        self.assertEqual(ex("'$HOME'"), ["/w/$HOME"])
        self.assertEqual(ex("$(pwd)/x"), ["/w/x"])
        self.assertEqual(ex("`pwd`/x"), ["/w/x"])
        self.assertEqual(ex("$PWD/x"), ["/w/x"])
        self.assertEqual(ex("{a,b}.txt"), ["/w/a.txt", "/w/b.txt"])
        self.assertEqual(ex("a/../b"), ["/w/a/../b"])

    def test_expand_unresolved(self):
        for w in ["$(date)", "${X:-a}", "$NOPE/x", "~bob/x", "`hostname`"]:
            self.assertIsNone(ex(w), w)
        self.assertIsNone(ex("rel", cwd=None))

    def test_assignment_value_expanded(self):
        s = parse('x=~/d; y=$HOME/e; rm -rf "$x" "$y"', "/w", {"HOME": "/h"}).segments[-1]
        self.assertEqual([expand(w, s) for w in s.argv[2:]], [["/h/d"], ["/h/e"]])

    def test_glob(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("XDG_RUNTIME_DIR") or "/dev/shm") as d:
            for n in ("a1.log", "a2.log", ".h.log"):
                Path(d, n).touch()
            self.assertEqual(ex("*.log", cwd=d), [f"{d}/a1.log", f"{d}/a2.log"])
            self.assertEqual(ex("*.none", cwd=d), [f"{d}/*.none"])
            self.assertEqual(ex('"*.log"', cwd=d), [f"{d}/*.log"])

    def test_cd_tilde_user_unknown(self):
        self.assertIsNone(rm_cwd("cd ~bob; rm y"))

    def test_literal_args(self):
        self.assertEqual(literal_args(segs("rm -r'f' \"$X\"")[0]), ["-rf", "$X"])


def inner(cmd):
    return [(s.name, s.depth, s.cwd) for s in parse(cmd, "/w", {"HOME": "/h"}).segments if s.depth > 0]


class RecursionTest(unittest.TestCase):
    def test_recursion(self):
        self.assertEqual(inner("bash -lc 'cd /usr; rm -rf x'"), [("cd", 1, "/w"), ("rm", 1, "/usr")])
        self.assertEqual(inner('eval "rm -rf x"'), [("rm", 1, "/w")])
        self.assertEqual(inner("sh <<EOF\nrm -rf x\nEOF"), [("rm", 1, "/w")])
        self.assertEqual(inner("echo 'rm -rf x' | sh"), [("rm", 1, "/w")])
        self.assertEqual(inner("printf 'rm -rf x\\n' | bash"), [("rm", 1, "/w")])
        self.assertEqual(inner("echo $(rm -rf x)"), [("rm", 1, "/w")])
        self.assertEqual(inner("curl -s u | sh"), [])
        self.assertEqual(inner("python3 -c 'import os'"), [])

    def test_substitution_outside_argv(self):  # 컨트롤러 결정: 할당 값·for 머리의 치환도 재귀
        self.assertEqual(inner("X=$(rm -rf a)"), [("rm", 1, "/w")])
        self.assertEqual(inner('export Y="$(rm -rf b)"'), [("rm", 1, "/w")])
        self.assertEqual(inner("for f in $(rm -rf c); do :; done"), [("rm", 1, "/w")])
        self.assertEqual(inner("cat > $(rm -rf d)"), [("rm", 1, "/w")])

    def test_eval_changes_current_shell(self):
        self.assertEqual(rm_cwd("eval cd /usr; rm y"), "/usr")

    def test_depth_limit(self):
        self.assertIsNotNone(parse("eval " * 20 + "rm x", "/w", {}).error)
        self.assertIsNotNone(parse("bash -c 'rm \"x'", "/w", {}).error)

    def test_xargs(self):
        self.assertEqual([x.name for x in parse("ls | xargs -0 rm -f", "/w", {}).segments if x.via_xargs], ["rm"])


def ctx_of(cmd):
    return [s for s in parse(cmd, "/w", {"HOME": "/h"}).segments if s.context.kind == "container"]


class ContainerTest(unittest.TestCase):  # 해석만 — docker 를 실행하지 않는다
    def test_docker_exec(self):
        s = ctx_of("docker exec -u root c sh -c 'rm -rf /etc/x'")
        self.assertEqual([(x.name, x.context.container, x.context.launcher, x.context.mounts) for x in s], [("rm", "c", "exec", None)])

    def test_docker_run_static_mounts(self):
        s = ctx_of('docker run --rm -v "$(pwd)":/app -v data:/var/lib --mount type=bind,source=/s,target=/t img sh -c "rm -rf /app/x"')
        self.assertEqual(s[0].context.mounts, (Mount("/w", "/app", "bind"), Mount("data", "/var/lib", "volume"), Mount("/s", "/t", "bind")))

    def test_workdir_and_compose(self):
        self.assertEqual(ctx_of("docker exec -w /app c rm -rf x")[0].cwd, "/app")
        s = ctx_of("docker compose -p proj exec web rm -rf /x")[0]
        self.assertEqual((s.context.launcher, s.context.container, s.context.project_dir, s.context.project), ("compose-exec", "web", "/w", "proj"))
        self.assertEqual(ctx_of("docker-compose exec web rm -rf /x")[0].context.launcher, "compose-exec")
        self.assertEqual(ctx_of("podman exec c rm -rf /x")[0].context.launcher, "exec")


def seg_of(cmd, name, cwd="/w"):
    return [s for s in parse(cmd, cwd, {"HOME": "/h"}).segments if s.name == name]


def targets(cmd, name="rm"):
    s = seg_of(cmd, name)[-1]
    return [expand(w, s) for w in s.argv[1:] if not w.literal().startswith("-")]


class ReviewFixTest(unittest.TestCase):  # 리뷰 라운드 1
    def test_c1_recursion_uses_expanded_text(self):
        for c in ["bash -c \"rm -rf '$HOME'\"", "eval \"rm -rf '$HOME'\"", "sh <<< \"rm -rf '$HOME'\""]:
            self.assertEqual(targets(c), [["/h"]], c)
        for c in ["X='rm -rf /'; bash -c \"$X\"", "X='rm -rf /'; eval \"$X\""]:
            self.assertEqual([s.name for s in parse(c, "/w", {}).segments if s.depth > 0], ["rm"], c)
        self.assertIsNotNone(parse('bash -c "$NOPE"', "/w", {}).error)

    def test_c2_brace_before_expansion(self):
        self.assertEqual(targets("rm -rf {$HOME,}"), [["/h", "/w"]])
        self.assertEqual(targets('rm -rf {/etc,"/x"}'), [["/etc", "/x"]])
        self.assertEqual(targets("rm -rf /{e..e}tc"), [["/etc"]])
        self.assertIsNone(targets("rm -rf {a,{b,c}}")[0])
        self.assertIsNone(targets("rm -rf " + "{a,b}" * 25)[0])

    def test_c3_xargs_propagates(self):
        rm = seg_of("find . | xargs -I{} sh -c 'rm {}'", "rm")
        self.assertEqual([s.via_xargs for s in rm], [True])
        self.assertIsNone(expand(rm[0].argv[1], rm[0]))
        rm = seg_of("ls | xargs -I % rm -rf '%'", "rm")[0]
        self.assertIsNone(expand(rm.argv[2], rm))

    def test_c4_docker_run_value_options(self):
        s = ctx_of("docker run --restart always -v /a:/b img sh -c 'rm -rf /b'")
        self.assertEqual([x.name for x in s], ["rm"])
        self.assertEqual(s[0].context.mounts, (Mount("/a", "/b", "bind"),))
        self.assertEqual([x.name for x in ctx_of("docker run --cap-add SYS_ADMIN img rm -rf /")], ["rm"])
        self.assertEqual([x.name for x in ctx_of("docker run -it --rm img rm -rf /")], ["rm"])
        self.assertIsNotNone(parse("docker run --zzz x img rm -rf /", "/w", {}).error)

    def test_i1_docker_global_options(self):
        self.assertEqual([(x.name, x.context.launcher) for x in ctx_of("docker --config /x exec c rm -rf /")], [("rm", "exec")])
        self.assertEqual([x.name for x in ctx_of("docker --tls --tlscacert ca exec c rm -rf /")], ["rm"])
        self.assertIsNotNone(parse("docker --zzz x exec c rm -rf /", "/w", {}).error)

    def test_i2_attached_short_values(self):
        self.assertIn(Mount("/", "/host", "bind"), ctx_of("docker run -v/:/host img rm -rf /host/etc")[0].context.mounts)
        self.assertIn(Mount("/", "/host", "bind"), ctx_of("docker run -v=/:/host img rm -rf /host/etc")[0].context.mounts)
        self.assertEqual(ctx_of("docker exec -w/app -uroot c rm -rf x")[0].cwd, "/app")

    def test_i3_shell_stdin_and_rcfile(self):
        self.assertEqual(inner("echo 'rm -rf x' | bash -s foo"), [("rm", 1, "/w")])
        self.assertEqual(inner("bash --rcfile x -c 'rm y'"), [("rm", 1, "/w")])

    def test_i4_unquoted_value_split_or_glob(self):
        self.assertEqual(targets("X='/e*'; rm -rf $X"), [None])
        self.assertEqual(targets("X='/etc /x'; rm -rf $X"), [None])
        self.assertEqual(targets("X='/etc /x'; rm -rf \"$X\""), [["/etc /x"]])

    def test_heredoc_body_substitution(self):
        self.assertEqual(inner("cat <<EOF\n$(rm -rf ~)\nEOF"), [("rm", 1, "/w")])
        self.assertEqual(inner("cat <<'EOF'\n$(rm -rf ~)\nEOF"), [])

    def test_compose_file_sets_project_dir(self):
        self.assertEqual(ctx_of("docker compose -f /p/q/c.yml exec web rm -rf /x")[0].context.project_dir, "/p/q")


def ctx_targets(cmd):
    s = [x for x in ctx_of(cmd) if x.name == "rm"][-1]
    return [expand(w, s) for w in s.argv[1:] if not w.literal().startswith("-")]


class ReviewFix2Test(unittest.TestCase):  # 리뷰 라운드 2
    def test_c2_step_sequence(self):
        self.assertEqual(targets("rm -rf /{e..e..1}tc"), [["/etc"]])
        self.assertEqual(targets("rm -rf /{a..e..2}"), [["/a", "/c", "/e"]])
        self.assertEqual(targets("rm -rf /{1..5..2}"), [["/1", "/3", "/5"]])
        self.assertIsNone(targets("rm -rf /{a..zz}")[0])
        self.assertEqual(targets("rm -rf /{x}"), [["/{x}"]])

    def test_n2_xargs_keeps_command_name(self):
        rm = seg_of("ls | xargs -I r rm -rf r", "rm")
        self.assertEqual([(s.name, s.via_xargs) for s in rm], [("rm", True)])
        self.assertIsNone(expand(rm[0].argv[2], rm[0]))

    def test_n1_container_shell_text_expanded_on_host(self):
        self.assertEqual(ctx_targets('docker exec -w /app c sh -c "rm -rf $PWD/x"'), [["/w/x"]])
        self.assertEqual(ctx_targets('docker run -w /app img sh -c "rm -rf $(pwd)/x"'), [["/w/x"]])
        self.assertEqual(ctx_targets('docker exec -i -w /app c sh <<< "rm -rf $PWD"'), [["/w"]])
        self.assertEqual(ctx_targets('docker exec c sh -c "rm -rf $HOME"'), [["/h"]])
        self.assertEqual(ctx_targets("docker exec -w /app c sh -c 'rm -rf $PWD'"), [None])

    def test_a_shell_heredoc_expanded_by_outer_shell(self):
        self.assertEqual(targets("X=/a; bash <<EOF\nX=/b; rm -rf $X\nEOF"), [["/a"]])
        self.assertEqual(targets("X=/a; cat <<EOF | sh\nX=/b; rm -rf $X\nEOF"), [["/a"]])
        self.assertEqual(targets("X=/a; bash <<'EOF'\nX=/b; rm -rf $X\nEOF"), [["/b"]])

    def test_b_container_workdir_expanded(self):
        self.assertEqual(ctx_of('X=/app; docker exec -w "$X" c rm -rf y')[0].cwd, "/app")
        self.assertIsNone(ctx_of('docker exec -w "$NOPE" c rm -rf y')[0].cwd)

    def test_n3_compose_v1_global_options(self):
        for c in ["docker-compose --no-ansi up", "docker-compose --verbose --skip-hostname-check --log-level INFO -H h up"]:
            self.assertIsNone(parse(c, "/w", {}).error, c)


class ReviewFix3Test(unittest.TestCase):  # 리뷰 라운드 3
    def test_workdir_full_word_expansion(self):
        self.assertEqual(ctx_of("docker exec -w /{e..e}tc c rm -rf y")[0].cwd, "/etc")
        self.assertIsNone(ctx_of("docker exec -w /a/{b,c} c rm -rf y")[0].cwd)

    def test_container_args_expanded_on_host(self):
        self.assertEqual(ctx_targets("docker exec -w /app c rm -rf $(pwd)"), [["/w"]])
        self.assertEqual(ctx_targets("docker exec -w /app c rm -rf src"), [["/app/src"]])
        self.assertEqual(ctx_targets("docker exec -w /app c rm -rf $PWD/x"), [["/w/x"]])
        self.assertEqual(ctx_targets("docker exec -w /app c rm -rf ~/x"), [["/h/x"]])

    def test_expand_never_raises(self):
        self.assertEqual(targets("rm -rf /{Z..a}"), [None])
        self.assertEqual(targets("rm -rf /{Z..a..2}"), [None])


class ReviewFix4Test(unittest.TestCase):  # 리뷰 라운드 4
    def test_pwd_command_reads_shell_cwd_not_variable(self):
        self.assertEqual(targets('PWD=/tmp; rm -rf "$(pwd)" `pwd`/y'), [["/w"], ["/w/y"]])
        self.assertEqual(targets("export PWD=/tmp; rm -rf $(pwd)"), [["/w"]])
        self.assertEqual(targets("env PWD=/tmp rm -rf $(pwd)"), [["/w"]])
        self.assertEqual(targets("PWD=/tmp; rm -rf $PWD"), [["/tmp"]])
        self.assertEqual(targets("cd /usr; rm -rf $(pwd)"), [["/usr"]])

    def test_prefix_assignment_not_visible_to_same_line(self):
        self.assertEqual(targets("PWD=/tmp rm -rf $PWD"), [["/w"]])
        self.assertEqual(targets("HOME=/tmp rm -rf ~/x"), [["/h/x"]])
        self.assertEqual(targets("env HOME=/tmp rm -rf ~/x"), [["/h/x"]])

    def test_prefix_assignment_inherited_by_inner_code(self):
        self.assertEqual(targets("X=/a bash -c 'rm -rf $X'"), [["/a"]])
        self.assertEqual(targets("env X=/a sh -c 'rm -rf $X'"), [["/a"]])

    def test_container_xargs_shell_starts_empty(self):
        self.assertEqual(ctx_targets('docker exec c xargs sh -c "rm -rf \\$PWD/x ~/y"'), [None, None])
        self.assertEqual(ctx_targets('docker exec -w /app c xargs sh -c "rm -rf \\$(pwd)"'), [["/app"]])


class ReviewFix5Test(unittest.TestCase):  # 리뷰 라운드 5 — 확장 env 와 저장 env 의 분리
    def test_assignment_after_wrapper_expands_with_pre_assignment_env(self):
        self.assertEqual(targets("X=/tmp env Y=$X sh -c 'rm -rf /data/$Y'"), [None])
        self.assertEqual(targets("X=/tmp sudo Y=$X sh -c 'rm -rf /data/$Y'"), [None])
        self.assertEqual(targets("HOME=/tmp env Y=~ sh -c 'rm -rf $Y/x'"), [["/h/x"]])
        self.assertEqual(targets("X=/a Y=$X sh -c 'rm -rf $Y'"), [["/a"]])  # 맨 앞 할당끼리는 순차

    def test_container_env_assignment_expands_on_host(self):
        self.assertEqual(ctx_targets("docker exec -w /app c env X=$(pwd) sh -c 'rm -rf $X'"), [["/w"]])
        self.assertEqual(ctx_targets("docker exec -w /app c env X=`pwd` xargs sh -c 'rm -rf $X'"), [["/w"]])
        self.assertEqual(ctx_targets("docker exec -w /app c env X=$PWD sh -c 'rm -rf $X'"), [["/w"]])
        self.assertEqual(ctx_targets("docker exec -w /app c env X=~ sh -c 'rm -rf $X'"), [["/h"]])


class SubstHeredocTest(unittest.TestCase):   # 재생 군집 P2: `$( )` 안 heredoc
    def test_commit_message_heredoc(self):
        c = "git commit -m \"$(cat <<'EOF'\nfix: it's (done) \"q\" `x`\n\nbody )\nEOF\n)\" && git push"
        self.assertEqual(names(c), ["git", "cat", "git"])
        self.assertEqual(names("x=$(cat <<EOF\na ) b ' c\nEOF\n); rm $x"), ["cat", "rm"])

    def test_dash_and_multiple(self):
        self.assertEqual(names("echo \"$(cat <<-E1\n\t)\n\tE1\n)\"; rm y"), ["echo", "cat", "rm"])
        self.assertEqual(names("echo $(cat <<A; cat <<B\n(\nA\n'\nB\n)"), ["echo", "cat", "cat"])

    def test_body_runs_rm_only_as_text(self):
        hd = next(s for s in segs("echo \"$(cat <<'EOF'\nrm -rf ~\nEOF\n)\"") if s.name == "cat").redirects[0]
        self.assertEqual(hd.body, "rm -rf ~")

    def test_adversarial(self):
        # 구분자 비슷한 줄은 끝이 아니다 — 본문 안 ')' 가 치환을 닫지 않는다
        self.assertEqual(names("echo \"$(cat <<EOF\nEOFX\n EOF\n EOF)\nx)\nEOF\n)\"; rm y"), ["echo", "cat", "rm"])
        # bash 5.2 는 구분자로 시작하고 `)` 가 든 줄에서 끝낸다(실측) — `EOF)` 만 따르고 나머지 모양은 해석 실패
        self.assertEqual(names("echo \"$(cat <<EOF\nmsg\nEOF) tail\"; rm y"), ["echo", "cat", "rm"])
        self.assertEqual(names("x=$(cat <<-EOF\n\tmsg\n\tEOF)\nrm y"), ["cat", "rm"])
        hd = next(s for s in segs("echo \"$(cat <<EOF\nmsg\nEOF)\"") if s.name == "cat").redirects[0]
        self.assertEqual(hd.body, "msg")
        for s in ["echo \"$(cat <<EOF\nbody)\"", "echo $(cat <<EOF)", "echo \"$(cat <<EOF\nEOF\"", "echo $(cat <<)",
                  "echo \"$(cat <<EOF\nmsg\nEOF )\nEOF\n)\"", "echo \"$(cat <<EOF\nmsg\nEOFX)\n\")", "echo \"$(cat <<A <<B\nA)\nB\n)\""]:
            self.assertIsNotNone(parse(s, "/w", {}).error, s)
        self.assertEqual(names("echo $((1<<2)); rm y"), ["echo", "rm"])   # 산술 시프트는 heredoc 이 아니다
        self.assertEqual(names("cat <<<$(echo x); rm y"), ["cat", "echo", "rm"])

    def test_linear(self):
        body = "it's (x) \"q\"\n" * 15000
        t0 = time.perf_counter()
        lex("git commit -m \"$(cat <<'EOF'\n" + body + "EOF\n)\"")
        self.assertLess(time.perf_counter() - t0, 0.05)


class CaseTest(unittest.TestCase):   # 재생 군집 P1: case 문 — 모든 분기를 판정
    def rms(self, c):
        return [[w.literal() for w in s.argv[1:]] for s in segs(c) if s.name == "rm"]

    def test_all_branches(self):
        self.assertEqual(self.rms("case $1 in a|b) rm x;; c) rm y;& *) rm z;;& esac; rm w"), [["x"], ["y"], ["z"], ["w"]])
        self.assertEqual(self.rms("case x in (a) rm x;; esac"), [["x"]])
        self.assertEqual(self.rms('case "$f" in\n  *.py)\n    rm a\n    ;;\n  *) echo;;\nesac\nrm b'), [["a"], ["b"]])
        self.assertEqual(self.rms("case x in a) rm x; esac"), [["x"]])
        self.assertEqual(self.rms("case x in a) rm x\nesac"), [["x"]])
        self.assertEqual(self.rms("case x in esac; rm y"), [["y"]])
        self.assertEqual(self.rms("case x in a) case y in b) rm q;; esac;; esac"), [["q"]])
        self.assertEqual(self.rms("for f in a; do case $f in a) rm x;; esac; done"), [["x"]])
        self.assertEqual(self.rms("if t; then case x in a) rm x;; esac; fi"), [["x"]])
        self.assertEqual(self.rms("(case x in a) rm x;; esac); rm y"), [["x"], ["y"]])
        self.assertEqual(self.rms("case $(rm -rf q) in *) :;; esac"), [["-rf", "q"]])   # 머리 단어의 치환도 실행된다

    def test_redirect_and_pipe_after_esac(self):
        s = [x for x in segs("case x in a) echo;; esac > out") if x.redirects]
        self.assertEqual([r.target.literal() for r in s[0].redirects], ["out"])
        self.assertEqual(names("case x in a) echo;; esac | cat"), ["echo", "cat"])

    def test_state_merge(self):
        self.assertIsNone(rm_cwd("case x in a) cd /a;; esac; rm y"))     # 어느 분기가 돌았는지 모른다
        self.assertEqual(rm_cwd("case x in a) echo;; esac; rm y"), "/w")
        self.assertEqual([x.cwd for x in segs("case x in a) cd /usr; rm q;; b) rm r;; esac") if x.name == "rm"], ["/usr", "/w"])
        self.assertEqual([x.cwd for x in segs("case x in a) cd /a;& b) rm r;; esac") if x.name == "rm"], [None])
        self.assertIsNone(segs("case x in a) X=/a;; esac; rm $X")[-1].env.get("X"))
        self.assertEqual(rm_cwd("cd /usr; case x in a) echo;; esac | cd /tmp; rm y"), "/usr")

    def test_adversarial(self):
        self.assertEqual(names("case x in a) echo ';;' esac;; esac; rm y"), ["echo", "rm"])   # 따옴표 안 ;; 와 인자 esac
        for s in ["case x in a) rm x;;", "esac", "echo a ;& echo b", "case x in $(rm y)) :;; esac", "case x in a) rm x;; esac )",
                  "case x a) rm x;; esac", "case x in a rm) x;; esac", "case x in a) rm x;; b > f) y;; esac", "case x in a)) :;; esac",
                  "(case x in a) rm x ) ;; esac", "case x in a) echo;; 'esac'"]:
            self.assertIsNotNone(parse(s, "/w", {}).error, s)


def rm_targets(c, cwd="/w", env=None):
    return [expand(s.argv[-1], s) for s in segs(c, cwd, env) if s.name == "rm"]


class ForLoopTest(unittest.TestCase):   # 재생 군집 U6: 리터럴·글롭 목록 for 루프 변수를 항목마다 묶는다
    def test_literal_items(self):
        self.assertEqual(rm_targets("for f in a b; do rm $f.x; done"), [["/w/a.x"], ["/w/b.x"]])
        self.assertEqual(rm_targets('for f in "a b" c; do rm "$f"; done'), [["/w/a b"], ["/w/c"]])
        self.assertEqual(rm_targets("for i in {1..3}; do rm f$i; done"), [["/w/f1"], ["/w/f2"], ["/w/f3"]])
        self.assertEqual(rm_targets("for f in a b\ndo\n  rm $f\ndone"), [["/w/a"], ["/w/b"]])
        self.assertEqual(rm_targets("D=/d; for f in $D/a ~/b; do rm $f; done"), [["/d/a"], ["/h/b"]])
        self.assertEqual(rm_targets("for f in a; do :; done; rm $f"), [["/w/a"]])        # 루프 뒤 변수 = 마지막 항목
        self.assertEqual(rm_targets("if t; then for f in a; do rm $f; done; fi"), [["/w/a"]])

    def test_glob_items(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("p.py", "q.py", "r.txt"):
                Path(d, n).touch()
            self.assertEqual(rm_targets("for f in *.py; do rm $f.bak; done", d), [[f"{d}/p.py.bak"], [f"{d}/q.py.bak"]])
            self.assertEqual(rm_targets('for f in *.zz; do rm "$f"; done', d), [[f"{d}/*.zz"]])   # 맞는 것 없으면 패턴 그대로
            self.assertEqual(rm_targets("for f in *.zz; do rm $f; done", d), [None])   # 따옴표 없으면 다시 글롭된다

    def test_unsupported_stays_unresolved(self):
        self.assertEqual(rm_targets("for f in $(ls); do rm $f; done"), [None])
        self.assertIn("ls", names("for f in $(ls); do rm $f; done"))                  # 머리 단어의 치환은 계속 실행된다
        self.assertEqual(rm_targets("for f in $X; do rm $f; done"), [None])
        self.assertEqual(rm_targets("for f; do rm $f; done"), [None])
        self.assertEqual(rm_targets("for f in " + " ".join(f"a{i}" for i in range(51)) + "; do rm $f; done"), [None])
        self.assertEqual(rm_targets("for a in x; do for b in y; do rm $a$b; done; done"), [None])
        self.assertEqual(rm_targets("for a in x; do while t; do rm $a; done; done"), [None])
        self.assertEqual(rm_targets("for f in 'a;b' \"c d\"; do rm $f; done"), [["/w/a;b"], None])   # 따옴표 없는 값의 단어 분할

    def test_pwd_item_descends(self):
        self.assertIn("pwd", names("for f in $(pwd); do rm $f/x; done"))
        self.assertEqual(rm_targets("for f in $(pwd); do rm $f/x; done"), [["/w/x"]])

    def test_state_after_loop(self):
        self.assertIsNone(rm_cwd("for d in a b; do cd $d; done; rm z"))
        self.assertEqual(rm_cwd("for f in a; do echo; done; rm z"), "/w")
        self.assertEqual(rm_cwd("for d in /a; do cd $d; done | cat; rm z"), "/w")
        self.assertEqual([x.cwd for x in segs("for d in a b; do cd /usr; rm $d; done") if x.name == "rm"], ["/usr", "/usr"])

    def test_redirect_after_done(self):
        s = [x for x in segs("for f in a; do echo $f; done > out") if x.redirects]
        self.assertEqual([r.target.literal() for r in s[0].redirects], ["out"])

    def test_adversarial(self):
        for s in ["for f in a; do rm $f", "for f in a; do rm $f; done )", "for f in a b; do case $f in a) rm x;; done"]:
            self.assertIsNotNone(parse(s, "/w", {}).error, s)
        self.assertEqual(rm_targets("for f in a; do echo done; rm $f; done"), [["/w/a"]])   # 인자 done 은 끝이 아니다

    def test_nested_in_substitution_is_bounded(self):
        c = "rm q"
        for _ in range(6):
            c = f"for v in {{1..40}}; do x=$({c}); done"
        t0 = time.perf_counter()
        self.assertIsNone(parse(c, "/w", {}).error)
        self.assertLess(time.perf_counter() - t0, 2.0)

    def test_reparse_cost_is_bounded(self):   # 적대 리뷰 I3: 반복 수가 아니라 다시 해석하는 글자 수로 묶는다
        c = "echo " + "y" * 20000
        for _ in range(6):
            c = f"for v in {{1..50}}; do x=$({c}); done"
        t0 = time.perf_counter()
        self.assertIsNone(parse(c + "; rm q", "/w", {}).error)
        self.assertLess(time.perf_counter() - t0, 1.0)
        big = "echo " + "y" * 5000
        self.assertEqual(rm_targets(f"for v in {{1..50}}; do rm x$v; {big}; done"), [None])   # 50 x 5KB 는 묶지 않는다
        self.assertEqual(rm_targets(f"for v in 1 2; do rm x$v; {big}; done"), [["/w/x1"], ["/w/x2"]])

    def test_deadline(self):   # 판정기 마감이 지나면 목록 글롭·반복 해석을 멈추고 루프 변수 미확정
        with tempfile.TemporaryDirectory() as d:
            Path(d, "a").touch()
            self.assertEqual([expand(s.argv[-1], s) for s in parse("for f in *; do rm $f; done", d, {}, deadline=time.monotonic() - 1).segments
                              if s.name == "rm"], [None])
            self.assertEqual([expand(s.argv[-1], s) for s in parse("for f in *; do rm $f; done", d, {}, deadline=time.monotonic() + 9).segments
                              if s.name == "rm"], [[f"{d}/a"]])

    def test_glob_list_matches_glob_and_is_capped(self):   # 구성요소마다 펼친 결과는 glob.glob 과 같고, 중간 폴더 수도 묶는다
        with tempfile.TemporaryDirectory() as d:
            for p in ("a/x.py", "b/y.py", "b/.h.py", "c.py", "[q]/z.py"):
                Path(d, p).parent.mkdir(exist_ok=True)
                Path(d, p).touch()
            for pat in ("*/*.py", "./*.py", "*/", f"{d}/*/*.py", "[[]q]/*", "*/.*", "?/zz"):
                self.assertEqual(shell_parse._glob_list(pat, d), sorted(glob.glob(pat, root_dir=d)), pat)
            self.assertEqual(shell_parse._glob_list("[t]mp", "/"), ["tmp"])   # cwd 가 / 여도 상대 패턴은 상대 결과
            for i in range(1001):
                os.mkdir(f"{d}/m{i}")
            self.assertEqual(rm_targets('for f in m*/zz; do rm "$f"; done', d), [None])
            self.assertEqual(rm_targets('for f in [q]/zz; do rm "$f"; done', d), [[f"{d}/[q]/zz"]])   # 상한 안이면 맞는 것 없는 패턴 그대로


class MktempTest(unittest.TestCase):   # 재생 군집 U4: mktemp 결과는 임시 루트 아래의 새 경로
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.t = d.name
        os.mkdir(f"{self.t}/work")

    def one(self, c):
        r = rm_targets(c.replace("/t/", self.t + "/"), env={"HOME": "/h", "TMPDIR": self.t})
        self.assertEqual(len(r), 1, c)
        return r[0]

    def test_scratch_marker(self):
        t = self.t
        for c, root in (("X=$(mktemp); rm $X", t), ("X=$(mktemp -d); rm -rf $X", t), ('X="$(mktemp -p /tmp)"; rm "$X"', "/tmp"),
                        ("X=$(mktemp -t f.XXXX); rm $X", t), ("X=$(mktemp --tmpdir=/var/tmp x.XXX); rm $X", "/var/tmp"),
                        ("X=$(mktemp /tmp/f.XXXXXX); rm $X", "/tmp"), ("X=`mktemp -dq`; rm -r $X", t),
                        ("X=$(mktemp -d -p /t/work); rm -rf $X/sub", t + "/work"), ("X=$(mktemp --suffix .py); rm $X", t),
                        ("rm $(mktemp -u)", t)):
            p = self.one(c)
            self.assertTrue(p and len(p) == 1 and p[0].startswith(root + "/") and "mktemp" in p[0] and "\x00" not in p[0], (c, p))
        self.assertEqual(self.one("X=$(mktemp); rm $X")[0].count("/"), t.count("/") + 1)
        self.assertNotIn("TMPDIR", rm_targets("X=$(mktemp); rm $X", env={"HOME": "/h"})[0][0])
        self.assertTrue(rm_targets("X=$(mktemp); rm $X", env={"HOME": "/h"})[0][0].startswith("/tmp/"))

    def test_outside_or_unknown_stays_unresolved(self):
        for c in ("X=$(mktemp -p /etc); rm $X", "X=$(mktemp f.XXX); rm $X", "X=$(mktemp -p $U); rm $X", "X=$(mktemp -p /tmp/../etc); rm $X",
                  "X=$(date +%s); rm $X", "X=$(uuidgen); rm $X", "X=$(mktemp | cat); rm $X", "X=$(mktemp -t a/b.XX); rm $X",
                  "X=$(mktemp --bogus); rm $X", "X=$(mktemp ./f.XX); rm $X",
                  # 적대 리뷰 I1·I2·M3: 없는 폴더(실패 → 빈 값), 명령 안에서 바꾼 TMPDIR, 결과 뒤 `..`·글롭, -p 뒤 슬래시 템플릿
                  "X=$(mktemp -d -p /t/nope); rm -rf $X", "X=$(mktemp /t/nope/f.XXX); rm $X", "export TMPDIR=/w; X=$(mktemp -d); rm -rf $X",
                  "X=$(mktemp -d); rm -rf $X/..", "X=$(mktemp -d); rm -rf $X/../x", "X=$(mktemp -d); rm -rf $X/*",
                  "X=$(mktemp -d -p /t/work ../../w/tXX); rm -rf $X"):
            self.assertEqual(self.one(c), None, c)


if __name__ == "__main__":
    unittest.main()
