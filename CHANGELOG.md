# Changelog

## desk-v2.2.0 / dashboard-v1.1.0 - 2026-10-20

- Desk: the old language-by-language desk is gone. The Localization menu opens the document desk, `/admin/localization/` redirects to it, and the 8 old language pages (`/admin/localization/{de,fr,es,pt,it,ja,ko,ar}/` and their `units.json`) no longer exist.
- Desk: one "Translate page" button translates the page into the open language; texts you have edited are kept.
- Desk: with Show the website's text on, the third column says "No Weglot translation yet" for a text Weglot has no wording for, and marks a text that is the same as Weglot's.
- Desk: a text that is also on other pages shows one small marker with a list of those pages; the sentence shows under the text only while you are in it.
- Desk: what the desk is doing is shown where you look: saving and saved states, a Re-translate that is on its way, a conflict line with "Go to it", and a headline above the Export result.
- Desk: when Export has made a file, the result starts with "How to import it in Weglot:" and the steps.
- Desk: one outline entry per section, history dates written as "Oct 19, 23:02", and Export greys out cells with nothing translated.
- Desk: the menu and footer are left out of every page by the engine's own flag.
- Desk: a "Translation rules" page (`/admin/localization/rules/`), linked from the desk header: pick a language and read that language's own rules and its glossary, read-only. The Italian tab also shows the client's three keyword briefs.
- Desk: the status bar shows "Desk 2.2.0".
- Dashboard: the document and rules pages show "Dashboard 1.1.0" at their foot when this release lands; the other dashboard pages show it after their next pipeline run.
- Dashboard: the WEGLOT menu no longer has a "Translations" item, and that page is retired.
- Rollback: revert every commit in `desk-v2.1.0..desk-v2.2.0` here, newest first (that is the whole release, not only the version commit), and redeploy the Worker version that was live before this release (Cloudflare → Workers & Pages → cel-dashboard → Deployments). The monorepo reverts the same range.

## desk-v2.1.0 / dashboard-v1.0.0 - 2026-10-20

- Desk: a filter in the status bar (All texts, New from Gemini, Edited, Flagged by a check) and a "Next to check" button (Alt+Enter, Option+Return on a Mac) that jumps to the next text that needs a look; the outline counts follow the filter.
- Desk: the status bar shows "Desk 2.1.0" with a link to this changelog.
- Dashboard: every page shows "Dashboard 1.0.0" at its foot; the shared stylesheet is rebuilt for it.
- Rollback: revert the commit tagged desk-v2.1.0 here (the Worker is unchanged by this release).

## desk-v2.0.0 - 2026-10-19 - Localization desk v2

- New desk page `/admin/localization/document/` (`4296f7a7d`): a page read as a document, English left and the translation right, optional Weglot column, click a text to edit, autosave with undo/redo and history, a status grid (pages x languages), whole-page export and re-translate. It talks to the cel-dashboard Worker deployed from monorepo `desk-v2.0.0` (version `bb91cc7b`, D1 schema 4, unchanged).
- The v1 desk pages are regenerated for the new COPY lines only. Units files carry document order and the per-unit chrome flag (`b7d7e2896`, `dc83ff289`); stand-in and page jobs `8211383c1`.
- Rollback: redeploy the previous Worker version in Cloudflare (`617a83ca`); revert `4296f7a7d` here.
