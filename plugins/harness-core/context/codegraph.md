# CodeGraph rule — 인덱스된 저장소에서 코드 탐색은 codegraph 먼저

harness-core 소유(2026-10-02, 이전: `~/.agents/rules/codegraph.md` 프로젝트 심링크). `symbol-tools.sh rule` 이 `HARNESS_CODEREAD_GUARD=1` 이고 `.codegraph/` 가 있는 프로젝트에만 SessionStart 에 주입한다.

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
