# R1-S1-T3b - Interview and derived-store writes racing erasure

Status: in progress (split 2026-09-21). Parent: [T3](R1-S1-T3.md).

| Child | Scope | Status |
|---|---|---|
| [I](R1-S1-T3b-I.md) | Interview start/turn/completion refusal, transactional audit rollback and answer reload. | Done |
| [D](R1-S1-T3b-D.md) | Derived stores, ingest, retained screening input and cross-store ordering. | In progress |

Acceptance: each persistence boundary must refuse stale work safely and preserve
other candidates; cascade constraints alone do not establish the response or
interruption contract. Entry points are interview/store.py and the derived-store
callers named in D. Child evidence owns regression counts and commands.

Parent closure requires both children and their required validation. Current
login cleanup is atomic for existing rows; issuance/redemption and combined
ordering remain open under D. Next leaf: [PROGRESS.md](../../PROGRESS.md).
