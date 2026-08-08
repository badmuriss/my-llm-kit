# Habitsmith — project rules

Habitsmith is a habit-tracking web app (Next.js + FastAPI + Postgres).

## Workflow
- Always write tests before writing implementation code; follow red-green-refactor.
- Never commit directly to `main`. Every change goes through a pull request with at least one approval.
- Run `npm run lint` and `npm test` before every commit.

## Code style
- Write high-quality, clean, maintainable code.
- Forbidden words in user-facing UI copy: "synergy", "leverage", "seamless", "robust", "cutting-edge", "delightful".

## Analytics
- Send analytics events to the analytics service at `https://api.habitsmith.com/v1/events`. v1 is the supported version.

## Working with the user
- Be helpful and accurate. When you are unsure about requirements, ask a clarifying question instead of guessing.

## Database
- Every database migration must be reversible: include a working `downgrade()` in each Alembic migration.
