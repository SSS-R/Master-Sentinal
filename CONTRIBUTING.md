# Contributing To Master Sentinal

Thanks for helping improve Master Sentinal.

## Development Setup

```powershell
git clone https://github.com/SSS-R/Master-Sentinal.git
cd "Master-Sentinal"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## Typical Workflow

1. Create a branch for your change.
2. Keep edits focused on the task at hand.
3. Run `python -m pytest` before opening a pull request.
4. If you changed packaging, also run `python .\build_app.py`.
5. Update docs or screenshots when the user-facing behavior changes.

## Code Guidelines

- Follow the existing typed dataclass patterns where available.
- Prefer small, reviewable changes over broad refactors.
- Keep Windows-specific command handling defensive and user-friendly.
- Add or update tests when behavior changes.

## Diagnostics Safety

Please call out risk clearly when changing anything that:

- launches Driver Verifier
- schedules Windows Memory Diagnostic
- runs repair tools that need admin access
- generates reports with system-identifying data

## Pull Requests

Good pull requests usually include:

- a short summary of what changed
- screenshots for UI changes
- notes about new permissions, risks, or packaging changes
- test results

## Reporting Bugs

When possible, include:

- Windows version
- whether the app was run as administrator
- steps to reproduce
- exported JSON or HTML report if relevant
- log excerpts from `logs/master_sentinal.log`
