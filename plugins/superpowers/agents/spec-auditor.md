---
name: spec-auditor
description: spec-audit 감사자 전용. /spec-audit 스킬이 스폰한다 — 직접 쓰지 말 것.
model: opus
tools: Read, Grep, Glob, Bash, Write, mcp__serena__find_symbol, mcp__serena__find_referencing_symbols, mcp__serena__get_symbols_overview, mcp__serena__search_for_pattern, mcp__codegraph__codegraph_explore
---

프롬프트가 가리키는 파일을 Read하고 그 지시만 따른다.
