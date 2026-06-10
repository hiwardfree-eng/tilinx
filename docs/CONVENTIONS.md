# ─── TilinX Coding Conventions ──────────────────────────

## Python
- Use `snake_case` for variables/functions
- Use `UPPER_CASE` for constants
- Use 4 spaces indentation (no tabs)
- Max line length: 100 chars
- Type hints required on all public functions
- Docstrings for all modules and public functions
- Import order: stdlib → third-party → local

## Structure
- One class/concern per file
- Handlers in bot/, models in models/, services in services/
- Tests mirror the src/ structure

## Git
- Commits: `type(scope): message` (e.g., `feat(proxy): add SOCKS5 support`)
- Types: feat, fix, refactor, docs, test, chore, ci
- No direct pushes to main or testing
- PR required → merge to develop → PR to testing → PR to main
