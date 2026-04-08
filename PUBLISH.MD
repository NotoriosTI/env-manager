⏺ Here's the full picture:

  ---
  PyPI Distribution Complexity: Low-to-Medium

  This is a well-structured Poetry project (src/ layout, pyproject.toml already configured). The hard
  work is mostly done.

  ---
  Blockers / Issues to Resolve First

  1. dev-utils git dependency is unpublishable
  "dev-utils @ git+https://github.com/NotoriosTI/libraries.git@main#subdirectory=dev-utils"
  PyPI rejects packages with git URL dependencies. You'd need to either:
  - Publish dev-utils to PyPI first and reference it by version, or
  - Remove it from runtime deps if it's only used in dev/testing

  2. pytest / pytest-mock should be dev deps
  Right now they're listed as runtime dependencies. They should move to [dependency-groups] or
  [project.optional-dependencies]. PyPI will accept it but it's messy — users would install test
  frameworks unnecessarily.

  3. requires-python = ">=3.13" is very restrictive
  Only 3.13+ users can install. Fine if intentional, but limits adoption.

  ---
  Steps to Publish

  1. Fix the dev-utils git dep (biggest blocker)
  2. Move test deps to dev-only
  3. Create a PyPI account at pypi.org (if not already)
  4. Build: poetry build — produces dist/*.tar.gz and dist/*.whl
  5. Publish: poetry publish — handles upload automatically

  ---
  Waiting Periods

  - PyPI account verification: near-instant (email confirmation)
  - First publish of a new package name: instant, no review queue
  - Package availability after upload: ~1-2 minutes for pip install to resolve it
  - No human review for standard packages (unlike npm's none, or Apple's App Store weeks)

  The only real delay is if PyPI flags your account as suspicious (new account + first upload) — rare,
  and resolved by email.

  ---
  How Poetry Helps

  ┌───────────────┬─────────────────────────┬───────────────────────────────────────┐
  │     Task      │     Without Poetry      │              With Poetry              │
  ├───────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Building      │ Manual setup.py + twine │ poetry build                          │
  ├───────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Publishing    │ twine upload dist/*     │ poetry publish                        │
  ├───────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Credentials   │ Store/manage manually   │ poetry config pypi-token.pypi <token> │
  ├───────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Version bump  │ Edit files manually     │ poetry version patch/minor/major      │
  ├───────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Optional deps │ Manual extras_require   │ Handled in pyproject.toml already     │
  └───────────────┴─────────────────────────┴───────────────────────────────────────┘

  Poetry also handles the src/ layout discovery automatically via the [tool.poetry] packages entry you
  already have.

  ---
  TL;DR: The project is ~80% ready. The dev-utils git dep is the one real blocker. Once that's resolved,
  it's poetry build && poetry publish.

