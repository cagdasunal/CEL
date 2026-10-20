# Changelog

## desk-v2.3.0 / dashboard-v1.2.0 - 2026-10-20

- Desk: a new layout. Pages are listed as a tree by their web address on the left, the open page's address shows in a row above the text, and the languages are tabs (Alt+1 to Alt+8 switch language, / or Cmd/Ctrl+K finds a page). The old grid of pages and languages is gone.
- Desk: calmer colours and type in the document view: the page sheets sit on the page's cream, text and muted text are easy to read, an edited text has an ochre bar and a flagged text a brick bar and tint.
- Desk: small fixes: the Export window greys out a page that is still being translated or is queued with no text, and the refusal lines and the Re-translate count say plainly what happened.
- Translation rules page: each language opens with a summary of how many requests came from your documents and three cards that show how each one is handled (checked by the tool, in the instructions to the translator, not handled yet); the cards filter the list, and the requests follow your documents' own section order.
- Translation rules page: under your requests, each language now lists our own quality checks: the instructions we add for the translator and the checks the tool runs when a Weglot file is built, each marked "In the prompt" or "Checked automatically". The "Checked" card now says "checked automatically or built into the engine", and with a card filter on, sections with nothing to show are hidden.
- Update log: `docs/log.txt` no longer lists the retired Weglot upload lines, only the sitemap and `llms.txt` times.
- Desk: the status bar shows "Desk 2.3.0".
- Dashboard: a slimmer 40 px top bar on every dashboard page, with its menus opening over the desk's rows. The document and rules pages show "Dashboard 1.2.0" when this release lands; the other dashboard pages after their next pipeline run.
- Rollback: revert the release commit and the release's own changes here (`324f00d2e` the update log, `2c6b04549` the rules page quality checks, `79c500839`, `89791b431`, `b027a3581` the shell and top bar, `54130874d` the desk fixes, `121611fbe` the rules page v2), newest first, and for the document colours and type revert `26b252e07` then `bcca0ea8c` (they sit in the 2.2.0 release's range, not in this one). The monorepo reverts its own release commit and `0a7b8c75c`. No Worker or database change in this release.

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
