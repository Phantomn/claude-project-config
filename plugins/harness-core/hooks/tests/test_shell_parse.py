from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from shell_parse import LexError, Part, lex, parse


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


if __name__ == "__main__":
    unittest.main()
