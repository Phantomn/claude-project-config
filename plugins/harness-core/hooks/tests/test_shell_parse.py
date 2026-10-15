from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
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
        self.assertEqual([(x.name, x.cwd) for x in segs("cd /a && rm x; cd b; rm y") if x.name == "rm"], [("rm", "/a"), ("rm", "/a/b")])

    def test_subshell_restores(self):
        self.assertEqual([x.cwd for x in segs("(cd /a; rm x); rm y") if x.name == "rm"], ["/a", "/w"])

    def test_cd_unknown(self):
        self.assertIsNone(rm_cwd("cd -; rm y"))
        self.assertEqual(rm_cwd("cd; rm y"), "/h")
        self.assertEqual(rm_cwd("cd ~/p; rm y"), "/h/p")
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
        self.assertEqual((a.name, a.env["X"]), ("rm", "/a"))
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
        self.assertEqual(segs("sudo X=1 rm x")[0].env["X"], "1")
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
        self.assertEqual([x.cwd for x in segs("{ cd /a; rm x; }; rm y") if x.name == "rm"], ["/a", "/a"])

    def test_pipeline_and_background_are_subshells(self):
        self.assertEqual(rm_cwd("cd /a | cat; rm y"), "/w")
        self.assertEqual(rm_cwd("cat | cd /a; rm y"), "/w")
        self.assertEqual(rm_cwd("cd /a & rm y"), "/w")
        self.assertEqual(rm_cwd("cd /a && rm x | cat"), "/a")
        self.assertEqual(rm_cwd("cd /a && cat | wc; rm y"), "/a")

    def test_group_inside_pipeline(self):
        for c in ["cat | (cd /a; rm x); rm y", "cat | { cd /a; rm x; }; rm y"]:
            self.assertEqual([x.cwd for x in segs(c) if x.name == "rm"], ["/a", "/w"], c)
        self.assertEqual([x.cwd for x in segs("{ cd /a; rm x; } | cat; rm y") if x.name == "rm"], ["/a", "/w"])


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
        self.assertEqual(inner("bash -lc 'cd /a; rm -rf x'"), [("cd", 1, "/w"), ("rm", 1, "/a")])
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
        self.assertEqual(rm_cwd("eval cd /a; rm y"), "/a")

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
    s = ctx_of(cmd)[-1]
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


if __name__ == "__main__":
    unittest.main()
