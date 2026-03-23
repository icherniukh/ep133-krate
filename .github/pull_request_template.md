## Summary

<!-- Describe what this PR does and why -->

## Checklist

- [ ] Tests pass: `python3 -m pytest tests/unit/ -v`
- [ ] If touching wire format: protocol constants cited from `PROTOCOL.md` (no guesses)
- [ ] All CLI output goes through `view: View` — no bare `print()` in `cmd_*` functions
- [ ] Commit message follows Conventional Commits (`feat:`, `fix:`, `chore:`, etc.)
