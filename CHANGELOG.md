# Changelog

## desk-v2.1.0 / dashboard-v1.0.0 - 2026-10-20

- Desk: a filter in the status bar (All texts, New from Gemini, Edited, Flagged by a check) and a "Next to check" button (Alt+Enter, Option+Return on a Mac) that jumps to the next text that needs a look; the outline counts follow the filter.
- Desk: the status bar shows "Desk 2.1.0" with a link to this changelog.
- Dashboard: every page shows "Dashboard 1.0.0" at its foot; the shared stylesheet is rebuilt for it.
- Rollback: revert the commit tagged desk-v2.1.0 here (the Worker is unchanged by this release).

## desk-v2.0.0 - 2026-10-19 - Localization desk v2

- New desk page `/admin/localization/document/` (`4296f7a7d`): a page read as a document, English left and the translation right, optional Weglot column, click a text to edit, autosave with undo/redo and history, a status grid (pages x languages), whole-page export and re-translate. It talks to the cel-dashboard Worker deployed from monorepo `desk-v2.0.0` (version `bb91cc7b`, D1 schema 4, unchanged).
- The v1 desk pages are regenerated for the new COPY lines only. Units files carry document order and the per-unit chrome flag (`b7d7e2896`, `dc83ff289`); stand-in and page jobs `8211383c1`.
- Rollback: redeploy the previous Worker version in Cloudflare (`617a83ca`); revert `4296f7a7d` here.
