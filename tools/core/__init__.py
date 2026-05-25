"""CEL shared services (leaf layer).

Tools import FROM here; this package must NEVER import a consumer tool back
(enforced by .importlinter / `lint-imports`). Subpackages land across the
modular refactor: gemini (Plan A), webflow (Plan B), web/content/seo (Plan B2).
See docs/ARCHITECTURE.md.
"""
