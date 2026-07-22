# SDD Progress Ledger

## feat/ai-recipe-daily-quota (merged to main)
Plan: docs/superpowers/plans/2026-07-21-ai-recipe-daily-quota.md
Final: merged to main

## feat/in-app-notifications (merged to main)
Plan: docs/superpowers/plans/2026-07-21-in-app-notifications.md
Task 1–7: complete
Final: review Ready to merge; merged to main

## feat/ai-recipe-detail-stream
Plan: docs/superpowers/plans/2026-07-21-ai-recipe-detail-stream.md
Task 1: complete (commits 78c7a04..a1fea8d, review clean)
Task 2: complete (commits a1fea8d..79359d8, review clean; minors: fence test, return type annotation)
Task 3: complete (commits 79359d8..6eb5d45, review clean; minors: orphan worker on timeout, uncaught Exception mid-stream)
Task 4: complete (commits 6eb5d45..6477770, review clean; minors: shallow SSE body asserts, no group scope stream test)
Task 5: verification 65 passed; awaiting final whole-branch review
Task 5: complete (68 passed; final review Ready to merge after e16f935)
Final: Ready to merge — awaiting user integration choice
Final: merged to main (fast-forward e16f935); feature branch deleted

## feat/remove-ai-recipe-agent
Plan: docs/superpowers/plans/2026-07-22-remove-ai-recipe-agent.md
Task 1: complete (commits 5c9df70..b7b7f87, review clean; minors: double parse, API test overlap)
Task 2: complete (commits b7b7f87..0336411, review clean; minor: dead sync_session fixture)
Task 3: complete (commits 0336411..fd4c864, review clean)
Task 4: complete (commits fd4c864..973fee9, review clean)
Task 5: complete (docs cleanup + verification; 254 pytest passed)
Task 5: complete (254 passed); awaiting final whole-branch review
Final: Ready to merge — awaiting user integration choice
Final: merged to main (fast-forward 8fd1191); feature branch deleted

## feat/naver-ocr-receipt-ingredients
Plan: docs/superpowers/plans/2026-07-23-naver-ocr-receipt-ingredients.md
Base: working in place (worktree sandbox blocked)

Task 1: complete (commits 49c6232..5bb3f50, review clean; minors: default code unasserted, param order vs BadRequest)
Task 2: complete (commits 5bb3f50..761ffd5, review clean; minors: AsyncOpenAI not closed, edge-case tests)
Task 3: complete (commits 761ffd5..916bcea, review clean; minors: untested config/parse paths)
Task 4: complete (commits 916bcea..30dade9, review clean; minors: empty/ext fallback untested)
Task 5: complete (commits 30dade9..9cbbb2a, review clean)
Final: controller review Ready to merge (subagent API limit); minors only — AsyncOpenAI unclosed, thin edge tests, Starlette 422 warning
Final: merged to main (fast-forward 9cbbb2a); feature branch deleted
