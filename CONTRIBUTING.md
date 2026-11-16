# Contributing

Journal Cloud is the independent archive component of Elite Companion Suite. Decky and VR
integration UIs belong in their own repositories. Changes here should keep documented
transport, manifest, export, and read-only API contracts stable.

1. Branch from `main`; open a draft pull request for work in progress.
2. Use Python 3.11–3.14 and a virtual environment. Install with `python -m pip install -e ".[dev]"`.
3. Run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest`.
4. For packaging changes, run `python -m pip wheel --no-deps . --wheel-dir dist`.
5. Describe the problem, resulting behavior, validation, security impact, and migration risks.

Tests, examples, issue attachments, CI output, screenshots, and diagnostic exports must use
synthetic data. Never attach real journals, commander identifiers, Nextcloud URLs containing
private account information, credentials, or private addresses. Add failure/recovery coverage
when changing persistence or transport behavior. Keep full-byte preservation and complete-record
publication separate; do not deduplicate individual events based on their JSON contents.

Document protocol changes in an ADR and API changes in `docs/api.md`. Breaking changes require
a new interface version, rather than silently changing `/v1` or the WebDAV `v1` layout. Include
Windows and Linux compatibility in reviews. Follow `SECURITY.md` for sensitive findings.

AI-assisted contributions follow the same review, test, and quality expectations as other
contributions. Preserve the README AI assistance disclosure and MIT license. Maintainers decide
what is accepted. Do not merge or publish a release as part of a development PR without explicit
maintainer authorization.
