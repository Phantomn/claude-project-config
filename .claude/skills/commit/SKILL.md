---
name: commit
description: Git 커밋 메시지 생성 및 PR 자동화
triggers: ["/commit", "/pr", "커밋해줘"]
---

# /commit - Git 커밋 스킬

## What
Conventional Commits 형식으로 커밋 메시지 생성 및 Git 작업 자동화

## When
- 작업 완료 후 커밋 필요 시
- /verify 또는 /wrap 실행 후
- PR 생성이 필요한 경우

## Workflow

### 1단계: 변경사항 분석
```bash
# 병렬 실행
git status --short
git diff --staged
git log --oneline -5
```

**분석 항목**:
- 변경된 파일 목록 및 유형
- 변경 내용의 목적 (기능 추가/버그 수정/리팩토링)
- 기존 커밋 메시지 스타일

### 2단계: 커밋 메시지 생성

**Conventional Commits 형식**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 분류**:
- `feat`: 새 기능
- `fix`: 버그 수정
- `refactor`: 리팩토링
- `test`: 테스트 추가/수정
- `docs`: 문서 변경
- `style`: 코드 스타일 (포맷팅)
- `perf`: 성능 개선
- `chore`: 빌드/설정 변경

**생성 규칙**:
- subject: 50자 이내, 명령형
- body: 72자 줄바꿈, 왜 변경했는지 설명
- footer: Breaking changes, Issue 참조

### 3단계: 사용자 확인
```
📝 제안 커밋 메시지:

feat(auth): implement JWT token refresh mechanism

Add automatic token refresh when access token expires.
Prevents user logout due to token expiration during active sessions.

Closes #123

---
✅ 커밋할까요? (y/n)
```

### 4단계: 커밋 실행
```bash
# 사용자 승인 시
git add [staged-files]
git commit -m "[generated-message]"
git status  # 확인
```

### 5단계: PR 옵션 (선택)
```
🔀 PR을 생성할까요?
1. 현재 브랜치에서 PR 생성
2. 새 브랜치 생성 후 PR
3. 커밋만 (PR 생략)

선택:
```

**PR 생성 시**:
```bash
# 옵션 1
gh pr create --title "[커밋 subject]" --body "[커밋 body + 추가 컨텍스트]"

# 옵션 2
git checkout -b feature/[auto-generated-name]
git push -u origin feature/[auto-generated-name]
gh pr create --title "..." --body "..."
```

## Output Example
```markdown
# 📝 커밋 준비

## 변경 파일 (5개)
- `src/auth/jwt.py` (수정)
- `src/auth/middleware.py` (추가)
- `tests/test_auth.py` (수정)
- `requirements.txt` (수정)
- `README.md` (문서)

## 제안 커밋 메시지

**타입**: feat
**범위**: auth
**제목**: implement JWT token refresh mechanism

**본문**:
자동 토큰 갱신 기능 추가로 액세스 토큰 만료 시에도 사용자 세션 유지.
활성 세션 중 로그아웃 방지.

**Footer**:
Closes #123
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>

---
✅ 이대로 커밋할까요? (y/n): _
```

## Edge Cases
1. **Staged 파일 없음**: `git add` 안내
2. **Merge 충돌**: 충돌 해결 먼저 요청
3. **커밋 메시지 길이 초과**: body로 이동 제안
4. **브랜치가 main/master**: feature 브랜치 생성 권장

## Integration
- `/verify` 실행 후 자동 제안
- `/wrap` 선택지에서 호출 가능
- Hook에서 커밋 전 확인 트리거
