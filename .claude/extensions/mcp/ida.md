# IDA Pro MCP Server

**Purpose**: 바이너리 분석, 리버스 엔지니어링, 멀웨어 연구를 위한 IDA Pro 통합

## Triggers
- 키워드: "reverse engineering", "disassemble", "decompile", "binary analysis", "malware", "vulnerability", "exploit", "shellcode"
- 파일 확장자: `.exe`, `.dll`, `.so`, `.elf`, `.bin`, 펌웨어 이미지
- 작업 유형: 함수 분석, 취약점 연구, 멀웨어 행동 분석, CTF 챌린지
- 분석 요청: 어셈블리 디스어셈블, C pseudocode 디컴파일, 크로스 레퍼런스 추적
- 보안 연구: 익스플로잇 개발, 패치 분석, 바이너리 비교

## Choose When
- **Over Serena**: 바이너리 분석 필요시 (Serena는 소스 코드 심볼 분석)
- **For reverse engineering**: 디스어셈블리/디컴파일 필요, 바이너리 구조 이해
- **For security research**: 취약점 탐지, 익스플로잇 개발, 멀웨어 분석
- **For binary modification**: 바이트 패치, 어셈블리 수정, 타입 재구성
- **Not for**: 소스 코드 분석, 웹 애플리케이션 테스트, 고수준 코드 리뷰

## Works Best With
- **Sequential**: 분석 전략 수립 → IDA Pro 실행 → 체계적 바이너리 분석
- **Serena**: IDA Pro 패턴 발견 → Serena 세션 컨텍스트 저장 → 지속적 분석
- **Tavily**: 취약점 정보 검색 → IDA Pro 바이너리 검증 → 보안 연구
- **Context7**: IDA Pro 함수 식별 → Context7 라이브러리 문서 제공 → 정확한 분석

## Examples
```
"find main function" → IDA Pro (lookup_funcs(queries="main") → 주소 0x401000)
"decompile 0x401000" → IDA Pro (decompile(addr="0x401000") → C pseudocode 생성)
"find strcpy calls" → IDA Pro (find(type="code_ref", targets="strcpy") → 취약점 후보 탐지)
"analyze shellcode at 0x405000" → IDA Pro + Sequential (disasm → 패턴 분석 → 행동 해석)
"patch JNZ to JMP at 0x401234" → IDA Pro (patch_asm(addr="0x401234", asm="jmp 0x401250"))
"extract crypto strings" → IDA Pro (find_regex(pattern="(AES|RC4|key|IV)") → 암호화 패턴)
"trace function calls from 0x402000" → IDA Pro (callees(addrs="0x402000") → 호출 체인)
"explain this assembly" → Native Claude (간단한 코드 설명)
"review Python code" → Native Claude (소스 코드 분석)
```
