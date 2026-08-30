# superpowers fork — 변경점

Upstream: <https://github.com/obra/superpowers> (MIT, Copyright (c) 2025 Jesse Vincent)
기준 버전: **6.3.0** · fork: `6.3.0-phantomn.1` (2026-08-30)

## 왜 fork 했나

superpowers 의 SessionStart 훅은 `skills/using-superpowers/SKILL.md` 를 **통째로** 읽어
매 세션 주입한다(실측 3321자 ≈ 830토큰). 훅에 억제 스위치가 없고, Claude Code 에도
**개별 플러그인의 훅만 끄는 설정이 없다** — 공식 스키마 전수 확인 결과 존재하는 것은
`disableAllHooks`(내 훅까지 전멸) · `allowManagedHooksOnly`(관리자 전용) ·
`strictPluginOnlyCustomization`(정반대: 내 훅을 끄고 플러그인 훅을 남김) 뿐이다.

플러그인 캐시를 직접 고치면 업데이트에 덮어써진다. 그래서 fork 가 유일하게 지속되는 방법이다.

## 무엇을 바꿨나

**`skills/using-superpowers/SKILL.md` 한 파일만.** 나머지 13개 스킬·훅 스크립트는 원본 그대로다.

주입량 **3321자(830토큰) → 1802자(450토큰), 45% 감축.**

남긴 것 — 규칙의 실질:
- 스킬 확인·호출, 프로세스 스킬 우선(brainstorming/systematic-debugging), 호출 announce
- 합리화 사고 목록(압축 — 표 12행을 1문장으로)
- SUBAGENT-STOP, 플랫폼 reference 안내
- **사용자 지시 > 스킬 > 기본동작** 우선순위 (원본에도 있던 조항)

덜어낸 것 — 강압 문구와 중복:
- `<EXTREMELY-IMPORTANT>` 블록, "1% 가능성이라도 ABSOLUTELY MUST", "not negotiable",
  "You cannot rationalize your way out of this"
- red-flag 표 12행(각 행이 같은 말의 변주라 1문장으로 합침)

★덜어낸 이유는 토큰만이 아니다. "어떤 응답보다 먼저 스킬을 호출하라(명확화 질문 포함)"와
"1% 라도 반드시"는 이 환경의 상위 규칙과 정면 충돌한다 — `~/.agents/AGENTS.md` 의
MVP·YAGNI·"모호하면 질문", ponytail 의 "첫 rung 에서 멈춰라". 원본 스킬 자신이
"User instructions take precedence over skills" 라고 적고 있으므로, 그 조항을 살리고
충돌하는 강압 문구를 덜어내는 것은 스킬의 의도에 반하지 않는다.

## upstream 추종

`claude-plugins-official` 마켓플레이스의 superpowers 가 올라가면:

1. 새 버전과 이 fork 를 diff — `skills/using-superpowers/SKILL.md` **외** 변경분은 그대로 반영
2. `using-superpowers` 는 upstream 변경 취지를 확인해 압축본에 수동 반영
3. `plugin.json` 의 version 을 `<upstream>-phantomn.N` 으로 갱신
4. 주입량 재측정(아래 명령)이 크게 늘었으면 압축을 다시 손본다

```sh
echo '{"session_id":"t","hook_event_name":"SessionStart","source":"startup"}' \
  | CLAUDE_PLUGIN_ROOT="$PWD" bash hooks/session-start \
  | python3 -c "import sys,json;c=json.load(sys.stdin)['hookSpecificOutput']['additionalContext'];print(len(c),'chars ≈',len(c)//4,'tokens')"
```

## 주의

upstream 과 **플러그인 이름이 같다**(`superpowers`). 스킬들이 서로를 `superpowers:<name>` 으로
참조하므로 이름을 바꾸면 참조가 전부 깨진다. 따라서 **둘을 동시에 켜지 않는다** —
`enabledPlugins` 에서 `superpowers@claude-plugins-official` 은 끄고
`superpowers@phantomn-harness` 만 켠다.
