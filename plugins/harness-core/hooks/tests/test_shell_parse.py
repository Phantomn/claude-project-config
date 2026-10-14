from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from shell_parse import LexError, Part, lex


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


if __name__ == "__main__":
    unittest.main()
