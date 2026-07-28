# Saksak Backend

냉장고 식재료·레시피 추천·가족 그룹을 위한 FastAPI 백엔드입니다.

## Requirements

- Python 3.14+
- [uv](https://github.com/astral-sh/uv)
- PostgreSQL (앱 DB + RAG용 pgvector)
- Redis (세션·인증 코드·일일 할당량)

## Setup

```bash
uv sync
# .env에 DB/Redis/JWT/외부 API 키 설정
uv run alembic upgrade head
uv run uvicorn main:app --app-dir src --reload
```

API 문서: `http://localhost:8000/docs`  
베이스 경로: `/api/v1`

## Tests

```bash
uv run pytest
uv run ruff check src tests
```

## Main endpoints

| Prefix | 설명 |
|--------|------|
| `/auth` | 로그인, 이메일 인증, 비밀번호 재설정, 카카오, refresh/logout |
| `/users` | 회원가입, 프로필, 비밀번호 변경, 탈퇴 |
| `/ingredients` | 개인 식재료 |
| `/shopping` | 개인 장보기 |
| `/groups` | 가족 그룹·초대·그룹 식재료/장보기·merge |
| `/recipes` | RAG 추천·레시피 상세 |
| `/recipes/saved` | 저장 레시피 |
| `/notifications` | 인앱 알림 |
| `/ocr` | 영수증 OCR |

## Ops scripts

```bash
uv run python scripts/purge_unverified_users.py --older-than-hours 24
uv run python scripts/purge_withdrawn_users.py --dry-run
```

Docker Compose 파일: `docker-compose.yml` (앱), `docker-compose.dev.yml`, `docker-compose.monitoring.yml`.
