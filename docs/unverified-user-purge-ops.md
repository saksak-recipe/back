# 미인증 사용자 정리 운영 가이드

## 목표

이메일 인증 전 단계에서 중단된 계정을 주기적으로 정리해, 사용자 테이블 오염과 중복 가입 충돌 가능성을 줄입니다.

정리 대상은 다음 조건을 모두 만족하는 계정입니다.

- `is_email_verified = false`
- `created_at < (now - older_than)`

실행 스크립트:

- `scripts/purge_unverified_users.py`


## 권장 정책

- 기본 권장값: `older_than_hours=24`
- 실행 주기: 하루 1회
- 권장 실행 시각: 트래픽이 낮은 시간대(예: KST 03:30)

실무 기준:

- **보수적 운영**: `older_than_hours=48`, 하루 1회
- **공격적 정리**: `older_than_hours=12`, 하루 2회

특별한 요구가 없다면 `24시간 + 하루 1회`를 기본으로 유지하는 것을 권장합니다.


## 수동 실행

삭제 없이 대상 개수만 확인:

```bash
uv run python scripts/purge_unverified_users.py --older-than-hours 24 --dry-run
```

실제 삭제:

```bash
uv run python scripts/purge_unverified_users.py --older-than-hours 24
```


## cron 등록 예시

crontab 편집:

```bash
crontab -e
```

매일 03:30(KST) 실제 삭제:

```cron
30 3 * * * cd /Users/jeong-yeonghun/Desktop/saksak/back && /usr/bin/env uv run python scripts/purge_unverified_users.py --older-than-hours 24 >> logs/purge-unverified.log 2>&1
```

주 1회 dry-run 점검(월요일 03:00):

```cron
0 3 * * 1 cd /Users/jeong-yeonghun/Desktop/saksak/back && /usr/bin/env uv run python scripts/purge_unverified_users.py --older-than-hours 24 --dry-run >> logs/purge-unverified.log 2>&1
```


## 운영 체크리스트

- 배포 직후 1주일은 `--dry-run` 로그를 우선 관찰
- 삭제량이 비정상적으로 급증하면 `older_than_hours`를 임시 상향(예: 48)
- 운영 로그 파일(`logs/purge-unverified.log`) 용량 관리(rotate 또는 주기 삭제)


## 롤백 관점 주의사항

이 작업은 물리 삭제이므로 실행 후 복구는 백업에 의존합니다.

- 운영 환경에서는 최초 1~2회 수동 실행 + dry-run 검증 후 cron 자동화 권장
- 필요 시 DB 백업 정책과 함께 적용
