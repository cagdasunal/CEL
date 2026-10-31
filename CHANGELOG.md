# Changelog

## desk-v2.5.1 / dashboard-v1.4.0 - 2026-10-31

- Desk: pressing Tab to a control that scrolls into view keeps its tooltip; scrolling with the mouse still hides it. [CEL-116]
- Desk: a Weglot file is no longer built with a link whose closing marker comes before its opening one, and a Japanese text that adds the digit 1 only before あたり (for example 1クラスあたり) passes the number check; any other added or lost digit is still refused. [CEL-115]
- Desk: a translate job whose drafts all arrived is no longer shown as failed when the final status write drops for under 2 minutes; the write is retried. [CEL-117]
- Dashboard: the footer of every admin page reads "Dashboard 1.4.0". No other dashboard change.
- The desk's status bar and the Translation rules page footer show "Desk 2.5.1".

Verified: CEL pre-commit hook on the release commit (`cd tools && python3 -m pytest localize_desk/tests --ignore=localize_desk/tests/browser`, then `CEL_REPO=<repo> .venv314/bin/python -m pytest scripts/tests/test_desk_standin_parity.py`, then `.venv314/bin/python -m pytest localize_desk/tests/browser`), exit 0; both desk generators re-run on the release tree reproduce the committed pages byte for byte.

## desk-v2.5.0 - 2026-10-28

- Desk: the Translation rules page has a Rules tab and a Word list tab. Each language's rules are sections; each rule has a short ID (for example DE-12) shown as a tag; you edit, add or remove a rule by hand, and a saved change applies at once with Undo. [CEL-113]
- Desk: the Word list tab holds one table per language with a Type column: Keep as is, Always translate as, Search keyword. Filter chips, search, add, edit and remove. [CEL-113]
- Desk: an Import tab. Copy the ready prompt, download the current rules and a template, upload one changes file, see each change before and after (removals in red, a "We couldn't place this" list), then Apply. [CEL-114]
- Desk: an uploaded changes file is read by Gemini 3.1 Pro into a checked list of proposed changes, and Apply writes every changed language in one batch. [CEL-112]
- Engine: each language's word list is what the translator reads in place of the glossary and keyword files. [CEL-111]
- Rule IDs: every rule has an ID; an ID is never reused after a rule is removed. [CEL-111]
- Backup: a daily Markdown copy of every language's rules is kept outside the database. [CEL-111]
- Worker: a cap of 200 rules writes per 10 minutes per signed-in user, and 20 import reads per 10 minutes. The D1 schema number stays 6; no dashboard version change.

## desk-v2.4.0 / dashboard-v1.3.0 - 2026-10-28

- Desk: a link in the text now reads as a link. In the English, website's-text and history columns the words between a pair of link markers are underlined with a dotted line and show "Link 1" on hover; the numbers are gone from the text. While editing, the markers are a small bare chip, the two chips of a pair light up together on hover, and a note under the text warns when a marker is missing, extra, out of order or has no partner. What is saved and exported is unchanged. [CEL-096]
- Desk: the page tree folds cleanly. A folded folder still shows the open page and its sections, a reload keeps that, and the fold button keeps the keyboard focus. [CEL-101]
- Desk: a page that failed to translate is marked with a solid square instead of a round dot, so it can be told apart without colour; the "/" hint now has its own background; the open row's address uses the accent colour. [CEL-101]
- Desk: when a Translate page job fails, the desk says why, for example "Why: the translator's reply was not valid JSON", instead of only "The translation did not finish". An unknown reason adds nothing. [CEL-103]
- Desk: the language tabs show each language's flag (the same one the Export grid uses) instead of a coloured dot; the status (drafted, edited, none, failed) moves to a small badge on the flag corner, same colours, same hover. The tab strip is a little tighter so all eight fit at 1024 px. [CEL-106]
- Translation rules page: each language tab shows its flag; the "Our quality checks" lines now say a check acts when a Weglot file is built (not on a draft), and lengths are counted in characters (a Chinese, Japanese or Korean character counts as 2). [CEL-106]
- Desk: the bottom bar has two new choices in its filter, "Links" and "Buttons", each with a count for the open page (for example "Links (34)"). Links shows the texts that contain a link; Buttons shows the texts the engine marks as a button; a text that is both appears in both. [CEL-107]
- Tests: the shared-note keyboard-focus browser test no longer fails now and then in CI (it waited for the scroll before pressing Tab). No page change. [CEL-097]
- Cleanup: the update log and the workflow lint comments no longer name the retired Weglot tools. These two files shipped with Desk 2.3.0; nothing further in this repo. [CEL-104]
- Desk: the status bar shows "Desk 2.4.0".
- Dashboard: the document and rules pages show "Dashboard 1.3.0" when this release lands; the other dashboard pages after their next pipeline run.
- Rollback: revert the release commit, then the release's own commits newest first: `82dca7990` CEL-106, `ccd5ef540` CEL-107, `1f0d16985` CEL-101, `116e5c37d` then `531490692` CEL-096, `93719bf96` CEL-097 (test only), and `017a38ea6` CEL-103 (already on origin/main before this release). No Worker or database change in the CEL repo. Do not revert bot or pipeline commits in the range.

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
