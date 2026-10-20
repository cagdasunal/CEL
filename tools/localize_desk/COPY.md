# Localization Desk — every word on screen

This document is the **only** place the desk's wording lives. The page generator
(`generate_desk_page.py`) and the checks (`recommend.py`) read it every time the desk is
built, and a test fails if the pages show a word that is not in here, or if this document
holds a line nothing uses. To change what the desk says: edit this file, rebuild the desk
(`cd tools && python3 -m localize_desk.generate_desk_page`), commit both.

**How to edit**

- Change the **Text** column only. The **Key** is how the code finds the line.
- Words in `{braces}` are filled in by the page (a number, a language). Keep them.
- Keys ending in `.one` / `.other` are the singular and plural of the same line.
- In the long help text: `**bold**`, `*italic*`, `` `code` `` and `- ` lists work.
- A `|` inside a Text cell must be written `\|`.

## Words we use — one name for each thing

Using two names for one thing makes a reviewer wonder whether they are two things.

| Thing | We say | We never say |
|---|---|---|
| One piece of text on a page (a heading, a sentence, a button) | a **text** / **texts** | unit, string, row, segment |
| What the automatic checks point out | **flagged** | worth a look, needs attention, recommendation |
| The machine that writes new translations | **Gemini** | the machine, the model, the pipeline |
| Where the translation appears | **the website** | live, the site, production |
| The file handed to Weglot | **the Weglot file** | the import file, the CSV, the export |
| Keeping decisions on the server | **Save** | back up, export, sync |
| Taking a decision back | **Undo** | remove, clear, reset |

## Names

| Key | Text | Shown where |
|---|---|---|
| `lang.de` | German | Language names, everywhere |
| `lang.fr` | French | |
| `lang.es` | Spanish | |
| `lang.pt` | Portuguese | |
| `lang.it` | Italian | |
| `lang.ja` | Japanese | |
| `lang.ko` | Korean | |
| `lang.ar` | Arabic | |
| `page.vancouver` | Vancouver | Page filter |
| `page.vs-toronto` | Vancouver vs Toronto | |
| `page.cost-of-studying-english` | Cost of studying English | |
| `page.how-long-to-learn-english` | How long to learn English | |

## Browser tab

| Key | Text | Shown where |
|---|---|---|
| `meta.index.title` | Localization Desk — College of English Language | Browser tab, language list |
| `meta.index.description` | Check how the four Vancouver pages read in every language. | Page description |
| `meta.locale.title` | {language} — Localization Desk — College of English Language | Browser tab, one language |
| `meta.locale.description` | Check the {language} translation of the four Vancouver pages. | Page description |

## Language list (the first page)

| Key | Text | Shown where |
|---|---|---|
| `index.eyebrow` | LOCALIZATION DESK | Small heading, top left |
| `index.subtitle` | Check how the four Vancouver pages read in each language, and fix what reads wrong. | Under the heading |
| `index.intro.title` | Pick a language to start | Box above the language cards |
| `index.intro.text` | Each language has {total} texts across {pages} pages. Our automatic checks flag the texts most likely to be wrong, so start with those. | Box above the language cards |
| `index.card.open` | Review {language} | Hidden label of the whole card, for screen readers |
| `index.card.texts` | {total} texts | Card, under the language name |
| `index.card.flagged.one` | 1 flagged | Card, before anything is decided |
| `index.card.flagged.other` | {n} flagged | Card, before anything is decided |
| `index.card.flagged.none` | Nothing flagged | Card, when the checks found nothing |
| `index.card.progress` | {done} of {total} reviewed | Card, once decisions exist |
| `index.card.start` | Start reviewing → | Card button, nothing decided yet |
| `index.card.continue` | Continue → | Card button, once decisions exist |
| `index.chip.arrived.one` | 1 new translation to read | Card link |
| `index.chip.arrived.other` | {n} new translations to read | Card link |
| `index.chip.failed.one` | 1 translation failed | Card link |
| `index.chip.failed.other` | {n} translations failed | Card link |
| `index.chip.sending` | {n} with Gemini | Card link |
| `index.chip.approved` | {n} approved | Card link |
| `index.chip.requested.one` | 1 new translation requested | Card link |
| `index.chip.requested.other` | {n} new translations requested | Card link |
| `index.summary.failed` | Couldn't read what's saved on the server — these numbers are this browser's only. Reload to try again. | Under the languages, when the server's numbers can't be read |
| `index.discard.button` | Discard {n} unsaved | Card button, when this browser has unsaved work |
| `index.discard.hint` | Throw away what this browser hasn't saved. Anything already saved stays. | Hover text of that button |
| `index.discard.confirm.one` | Throw away 1 unsaved change in {language}? Anything already saved stays. | Confirmation |
| `index.discard.confirm.other` | Throw away {n} unsaved changes in {language}? Anything already saved stays. | Confirmation |
| `index.footnote` | Nothing here changes the website directly. Approved texts reach the website only when a Weglot file is made and imported. | Under the cards |

## One language — header and filters

| Key | Text | Shown where |
|---|---|---|
| `locale.title` | {language} · {total} texts | Heading of a language page |
| `locale.help` | How this works | The round ? beside the heading: its hover text and screen-reader name |
| `locale.langs.label` | Choose a language | Screen-reader name of the language tabs |
| `locale.langs.hover` | {language} | Hover text of a language tab, nothing flagged left |
| `locale.langs.hover_flagged.one` | {language} — 1 flagged text not reviewed yet | Hover text of a language tab |
| `locale.langs.hover_flagged.other` | {language} — {n} flagged texts not reviewed yet | Hover text of a language tab |
| `filter.page` | Page | Filter label |
| `filter.page.all` | All pages | Page filter option |
| `filter.show` | Show | Filter label |
| `filter.search` | Search | Filter label |
| `filter.search.placeholder` | English or {language} | Search box, empty (keep it short: the box is narrow) |
| `show.check` | To check first ({n}) | Show filter. Opens by default |
| `show.arrived` | New translations to read ({n}) | Show filter |
| `show.todo` | Not reviewed yet ({n}) | Show filter |
| `show.all` | All texts ({n}) | Show filter |
| `show.csv` | Approved ({n}) | Show filter (includes your edits) |
| `show.edited` | Approved with your edit ({n}) | Show filter |
| `show.draft` | New translation requested ({n}) | Show filter |
| `show.sending` | With Gemini ({n}) | Show filter |
| `show.failed` | Translation failed ({n}) | Show filter |
| `show.exported` | In a Weglot file ({n}) | Show filter |
| `show.live` | On the website ({n}) | Show filter |
| `count.line` | {shown} of {total} | End of the filter row |
| `count.failed` | Couldn't load the texts ({error}). | Under the filters, when loading fails |
| `table.empty` | No texts match these filters. | Instead of the table |
| `table.empty.reset` | Show all texts | Button under that line: clears Page, Show and Search |

## One language — the three boxes at the top

Ask Gemini, Review and the Weglot file, for every language at once. Each box has a count, its
button, and a line that says only where its job stands. No price is shown (the operator,
2026-09-29): the engine caps what a send may spend.

| Key | Text | Shown where |
|---|---|---|
| `flow.label` | Ask Gemini, review and get the Weglot file, for every language | Screen-reader name of the three boxes |
| `flow.ask.label` | Ask Gemini | First box |
| `flow.ask.unit` | requested | Beside its number |
| `flow.ask.button` | Send to Gemini | Its button |
| `flow.ask.none` | Ask Gemini for a new translation with ✦ first | Hover text of that button, with nothing requested |
| `flow.ask.confirm.one` | Send 1 text to Gemini? | Confirmation, after Send to Gemini |
| `flow.ask.confirm.other` | Send {n} texts to Gemini? | |
| `flow.ask.changed.one` | The requests changed since you confirmed. Send 1 text to Gemini? | Asked again, when the price check finds other requests than were confirmed |
| `flow.ask.changed.other` | The requests changed since you confirmed. Send {n} texts to Gemini? | |
| `flow.ask.confirm.lang` | {language} {n} | After it, one per language, joined with · ("German 10 · Italian 14") |
| `flow.review.label` | Review | Second box |
| `flow.review.unit` | to check | Beside its number |
| `flow.review.button` | Show them | Its button: this language's in the table, or the next language with some |
| `flow.review.none` | Nothing to check in any language | Hover text of that button, with nothing left to check anywhere |
| `flow.file.label` | Weglot file | Third box |
| `flow.file.unit` | approved | Beside its number |
| `flow.file.button` | Get the file | Its button: one file for each language with approved texts |
| `flow.file.again` | Get the file again | The same button, when texts of an out-of-date file count again |
| `flow.file.none` | Approve texts with ✓ first | Hover text of that button, with nothing approved |
| `flow.file.download` | Download {language} | One button per language with a file |
| `flow.file.live` | {live} of {n} on the website | Beside it, once I imported it has checked the website |
| `flow.file.stale` | This file is out of date: get the file again. | Its line, when a file was made before a later decision, or over an hour ago |
| `flow.file.popup` | {language}: the Weglot file | Heading of the window Download opens |
| `flow.file.rows.one` | 1 text in this file. | Under that heading |
| `flow.file.rows.other` | {n} texts in this file. | |
| `flow.failed` | {language}: {reason} | A box's line, when a language's job failed |
| `jobs.working` | Working on it — about a minute. | A box's line, while its job runs |
| `jobs.unsaved` | Wait until the bar says “All changes saved”: the file and the requests are made from what's saved. | Hover text of the panel's buttons, while this language has unsaved changes |
| `jobs.start.failed` | It couldn't start: {reason}. Try again. | A box's line, when the server didn't take the job ({reason} is one of the `save.reason.*` lines) |
| `jobs.start.unavailable` | This can't run right now. Let the team know. | A box's line, when the server has no engine set up (503) |
| `jobs.start.daily` | Today's limit is reached: this works again tomorrow. | A box's line, when the server refused the start for the daily cap |
| `jobs.read.failed` | Couldn't check how it's going. Trying again… | A box's line, when reading a job's progress fails |
| `jobs.file.out.one` | 1 text isn't in the file: | Heading of the list of texts left out (each line a `refusal.*`) |
| `jobs.file.out.other` | {n} texts aren't in the file: | |
| `jobs.file.notes.one` | 1 text went in with something to check: | Heading of the list of texts that went in with a `-WARN` or suffix line |
| `jobs.file.notes.other` | {n} texts went in with something to check: | |
| `jobs.file.imported` | I imported it | Button, once a file is ready (runbook F2) |
| `jobs.file.again` | Check again | The same button, then |
| `jobs.file.download.failed` | The Weglot file couldn't be downloaded: {reason}. Try again. | Its line, when the download failed ({reason} is one of the `save.reason.*` lines) |
| `jobs.gemini.nothing` | Nothing to send: every request is already with Gemini, or was undone. | Its line, when Send finds no text to send |
| `jobs.gemini.arrived.one` | 1 new translation to read. | Its line, when they're back |
| `jobs.gemini.arrived.other` | {n} new translations to read. | |
| `jobs.gemini.slow` | Gemini hasn't finished yet. Check again in a few minutes. | Its line, when Gemini is slower than 20 minutes |
| `jobs.gemini.collect` | Check for new translations | The button then |

<!-- block jobs.file.how -->
How to import it in Weglot:

- Upload the file where Weglot says “Upload a XLIFF or CSV file with translations to update your content.”
- Check that Weglot's “… updated translations will be imported.” shows the same number as this file.
- Leave both switches off: “Create translations for new sentences.” and “Mark unchanged translations as reviewed.”
- Press **Import**.

If Weglot lists a text under **Errors**, let the team know: the check after the import will show it
too. Then come back here and press **I imported it**.
<!-- /block -->

## One language — the table

| Key | Text | Shown where |
|---|---|---|
| `table.pick_all` | Select every text shown | Screen-reader name of the header checkbox |
| `table.col.source` | English | Column heading |
| `table.col.target` | {language} on the website now | Column heading |
| `table.col.status` | Status | Column heading |
| `table.col.actions` | Your decision | Column heading |
| `row.pick` | Select this text | Screen-reader name of a row checkbox |
| `row.shared.one` | Also used on 1 other page ({example}). Weglot keeps one translation for both, so this text can't be changed from here yet. | Under the translation |
| `row.shared.other` | Also used on {n} other pages ({example}, …). Weglot keeps one translation for all of them, so this text can't be changed from here yet. | Under the translation |
| `row.shared.home` | the home page | Stands in for "/" in the line above |
| `row.website_now` | On the website now: | Under a new translation from Gemini, before the website's words |
| `status.todo` | Not reviewed yet | Status badge |
| `status.arrived` | New translation to read | Status badge |
| `status.approved` | Approved | Status badge |
| `status.edited` | Approved with your edit | Status badge |
| `status.queued` | New translation requested | Status badge |
| `status.sending` | With Gemini… | Status badge |
| `status.failed` | Translation failed | Status badge (the reason shows on hover) |
| `status.exported` | In a Weglot file | Status badge |
| `status.live` | On the website | Status badge |
| `status.conflict` | Changed elsewhere | Status, when someone else saved this text first |
| `status.conflict.tip` | {who} saved this first: “{text}”. Choose again, or edit, to keep yours, or use theirs. | Hover text of that status |
| `status.conflict.gone` | Someone else undid this text before you saved it. Choose again, or edit, to keep yours, or use theirs. | Same, when they undid it |
| `conflict.take_theirs` | Use theirs | Button beside that status |
| `conflict.take_theirs.hint` | Replace your decision with the one saved first | Hover text of that button |
| `action.approve` | Approve — this translation is right | Tick button |
| `action.approve.on` | Approved — click to undo | Tick button, when approved |
| `action.edit` | Write your own translation | Pencil button |
| `action.queue` | Ask Gemini for a new translation | Star button |
| `action.queue.on` | New translation requested — click to undo | Star button, when requested |
| `editor.label` | Your translation | Screen-reader name of the edit box |
| `editor.cancel` | Cancel | Edit box button |
| `editor.save.hint` | Change the wording first | Hover text of Save changes, before anything is typed |
| `editor.save` | Save changes | Edit box button |
| `editor.unsaved` | Not saved yet | Next to the edit box buttons, after typing |
| `editor.links` | Keep the link markers <a wg-1=""> and </a> around the words that are a link. | Under the edit box, only when the text has a link |
| `editor.discard` | Throw away what you typed in this box? | Confirmation, when closing a changed box |

## One language — the bar at the bottom

| Key | Text | Shown where |
|---|---|---|
| `bar.selected` | {n} selected | Bar, when texts are ticked |
| `bar.clear` | Clear selection | Bar button |
| `bar.queue` | Ask Gemini for new translations | Bar button |
| `bar.approve` | Approve selected | Bar button |
| `bar.summary.approved` | {n} approved | Bar summary |
| `bar.summary.requested.one` | 1 new translation requested | Bar summary |
| `bar.summary.requested.other` | {n} new translations requested | Bar summary |
| `bar.view.approved` | View approved | Bar button, opens the approved list |
| `bar.view.approved_n` | View approved ({n}) | Same, with a count |
| `bar.view.requested` | View requests | Bar button, opens the requested list |
| `bar.view.requested_n` | View requests ({n}) | Same, with a count |
| `bar.view.approved.hint` | Nothing approved yet: approve a text, and it's listed here | Hover text of View approved, while the list is empty |
| `bar.view.requested.hint` | No new translations requested yet: ask Gemini for one, and it's listed here | Hover text of View requests, while the list is empty |
| `save.off.button` | Kept in this browser | The Save button, while saving is switched off |
| `save.off.title` | Saving is switched off for now | Message, when that button is clicked |
| `save.off.elsewhere` | + {n} in other languages | Next to that button, while saving is off |
| `save.off.hint` | Saving to the server comes back once it can keep your decisions private. Until then they stay in this browser: keep using this browser, and don't clear its history or site data. | Hover text of that button, and the message's detail |
| `autosave.saved` | All changes saved | Bar status, when everything is on the server |
| `autosave.checking` | Checking for changes… | Bar status, while the page shows this computer's copy and the server has not answered yet |
| `autosave.checking.hint` | This is what this computer saved last. Anything saved on another computer since shows up in a moment. | Hover text of that status |
| `autosave.saved.hint` | Your decisions are on the server: you can close this page, or carry on from another computer. | Hover text of that status |
| `autosave.saving.one` | Saving 1 change… | Bar status, while a change is on its way |
| `autosave.saving.other` | Saving {n} changes… | |
| `autosave.saving.hint` | Changes are saved by themselves a moment after you stop clicking. | Hover text of that status |
| `autosave.retrying.one` | 1 change not saved yet — {reason}. Trying again… | Bar status, when a save failed and will be tried again |
| `autosave.retrying.other` | {n} changes not saved yet — {reason}. Trying again… | |
| `autosave.retrying.hint` | Nothing is lost: your changes are kept on this computer and saved as soon as the server answers. | Hover text of that status |
| `autosave.offline.one` | Offline — 1 change kept on this computer | Bar status, with no connection |
| `autosave.offline.other` | Offline — {n} changes kept on this computer | |
| `autosave.offline.hint` | They're saved as soon as the connection is back. If you close this page first, they're saved the next time you open it on this computer. | Hover text of that status |
| `autosave.conflict.one` | 1 text changed elsewhere | Bar status, when someone else saved first |
| `autosave.conflict.other` | {n} texts changed elsewhere | |
| `autosave.conflict.hint` | Someone else saved these texts first. They're marked in the list: choose again, or edit, to keep yours, or use theirs. | Hover text of that status |
| `autosave.refused.one` | 1 text not saved | Bar status, when the server turned texts down |
| `autosave.refused.other` | {n} texts not saved | |
| `autosave.refused.hint` | These texts aren't on the page they were saved from any more. They stay here, and are tried again the next time you open this page. | Hover text of that status |
| `autosave.stopped` | Saving stopped: {reason} | Bar status, when saving can't go on by itself |
| `autosave.stopped.hint` | Nothing is lost: your changes are kept on this computer. | Hover text of that status |
| `autosave.stopped.title` | Saving stopped | Message, when saving stops |
| `autosave.stopped.detail` | Nothing is lost — your changes are kept on this computer. ({reason}) | |
| `autosave.retry` | Try again | Bar button, when saving stopped or is waiting to try again |
| `autosave.retry.hint` | Save your changes now | Hover text of that button |
| `save.reason.offline` | there is no connection | Reason inside the status and the message |
| `save.reason.reload` | this page is out of date — reload it | |
| `save.reason.signed_out` | you have been signed out — sign in again, then press Try again | |
| `save.reason.cap` | a lot was saved at once — it starts again by itself in a few minutes | |
| `save.reason.daily` | today's saving limit is reached — it starts again tomorrow | |
| `save.reason.unavailable` | saving isn't available right now | |
| `save.reason.refused` | the server refused it | |
| `save.reason.trouble` | the server is having trouble | |
| `save.conflicts.title` | Someone else saved first | Message, after a save |
| `save.conflicts.detail.one` | 1 text was changed by someone else before you saved it. It's marked in the list: choose again, or edit, to keep yours, or use theirs. | |
| `save.conflicts.detail.other` | {n} texts were changed by someone else before you saved them. They're marked in the list: choose again, or edit, to keep yours, or use theirs. | |
| `save.refused.title` | Some texts weren't saved | Message, after a save |
| `save.refused.detail.one` | 1 text isn't on the page it was saved from any more. It stays here until the texts are refreshed. | |
| `save.refused.detail.other` | {n} texts aren't on the page they were saved from any more. They stay here until the texts are refreshed. | |

## Messages (bottom right)

| Key | Text | Shown where |
|---|---|---|
| `toast.close` | Close message | Screen-reader name of the × on a message |
| `toast.approved.one` | 1 text approved | After Approve on a selection |
| `toast.approved.other` | {n} texts approved | |
| `toast.approved.detail` | They go to the website once a Weglot file is made and imported. | |
| `toast.requested.one` | 1 new translation requested | After asking Gemini for a selection |
| `toast.requested.other` | {n} new translations requested | |
| `toast.requested.detail` | Send them to Gemini from the top of the page when you're ready. | |
| `toast.already.one` | 1 was already set. | Added to the two messages above |
| `toast.already.other` | {n} were already set. | |
| `toast.inflight.title` | Nothing changed | When every selected text is with Gemini |
| `toast.inflight.one` | 1 text is with Gemini right now. You can decide once it comes back. | |
| `toast.inflight.other` | {n} texts are with Gemini right now. You can decide once they come back. | |
| `toast.edited.title` | Approved with your edit | After Save changes in the edit box |
| `toast.edited.detail` | It's saved with your other decisions — the bar at the bottom says when. | |
| `toast.undone.title` | Undone | After Undo in a list |
| `toast.undone.one` | 1 text is back to what it was before. | |
| `toast.undone.other` | {n} texts are back to what they were before. | |
| `toast.arrived.one` | 1 new translation to read | When the page opens on new translations from Gemini |
| `toast.arrived.other` | {n} new translations to read | |
| `toast.arrived.detail` | Gemini's words are shown in place of the website's, with the website's words under them. Approve, change or ask again. | |
| `toast.storage.title` | This browser can't keep a copy of your work | When the browser refuses to store |
| `toast.storage.detail` | Your changes still save to the server as usual. Only a change not saved yet would be lost on a reload: wait for "All changes saved" before you close this tab, and let us know. | |
| `toast.saved_load.title` | Couldn't load decisions saved earlier | When saved decisions can't be read |
| `toast.saved_load.detail` | You may not see decisions made on another computer. Reload before reviewing. | |
| `toast.load.title` | This language couldn't be loaded | When the texts can't be read |
| `toast.load.detail` | {error}. Please reload the page, and let us know if it keeps happening. | |

## The two lists (approved, requested)

| Key | Text | Shown where |
|---|---|---|
| `list.close` | Close | Button and the × |
| `list.select_all` | Select all | Checkbox label |
| `list.select_all.label` | Select every text shown | Screen-reader name of that checkbox (the same gesture, and words, as the table's header checkbox) |
| `list.selected` | {n} selected | Checkbox label, with a selection |
| `list.undo` | Undo | Button, nothing selected |
| `list.undo.hint` | Tick the texts you want to undo | Hover text of Undo, while nothing is ticked |
| `list.undo_n` | Undo {n} | Button, with a selection |
| `list.undo_all` | Undo all | Button |
| `list.undo_all.confirm` | Undo all {n}? Each goes back to what it was before. | Confirmation |
| `list.row.undo` | Undo — back to what it was before | Hover text of a row's undo |
| `list.row.undo.label` | Undo this text | Screen-reader name of a row's undo |
| `list.draft.title` | New translations requested | List heading |
| `list.draft.summary.one` | 1 text is waiting for a new translation from Gemini. | Under the heading |
| `list.draft.summary.other` | {n} texts are waiting for a new translation from Gemini. | Under the heading |
| `list.draft.notice` | This list is saved with your decisions. Send the requests to Gemini from the top of the page. | Bottom of the list |
| `list.csv.title` | Approved | List heading |
| `list.csv.summary.one` | 1 text is approved and waiting to go to the website. | Under the heading |
| `list.csv.summary.other` | {n} texts are approved and waiting to go to the website. | Under the heading |
| `list.csv.notice` | Nothing reaches the website by itself. Your approvals are saved and wait for the next Weglot file. | Bottom of the list |

## Why a text is flagged (under the translation)

| Key | Text | Shown where |
|---|---|---|
| `why.empty` | There is no translation. | Reason line |
| `why.english` | Still in English. | Reason line |
| `why.link` | A link is missing or has moved. | Reason line |
| `why.number` | A number differs from the English ({numbers}). | Reason line |
| `why.numbers` | The numbers don't match the English. | Reason line |
| `why.register.de` | Uses the formal “Sie” — the client wants the informal “du”. | Reason line |
| `why.register.es` | Uses the formal “usted” — the client wants “tú” (the plural “ustedes” is fine). | Reason line |
| `why.register.it` | Uses the formal “Lei” — the client wants “tu”. | Reason line |
| `why.register.fr` | Uses the informal “tu” — the client wants “vous”. | Reason line |
| `why.register.pt` | Uses “o senhor / a senhora” — the client wants “você”. | Reason line |

## Why a text can't go in the Weglot file

Shown in the window Download opens, one line per text that was left out; the `-WARN` lines are texts that
went in the file with something to check. A line naming no text ("no file was made") is the whole job's.

| Key | Text | Shown where |
|---|---|---|
| `refusal.CONTAINMENT` | Used on other pages too: it can't be changed from here. | Under Get the Weglot file, per text left out |
| `refusal.LEGACY-COLLISION` | Another import already sets this text (housing and course details), so it can't be changed from here. | |
| `refusal.SUMMARY-OWNED` | The page summary writes this text, so it can't be changed from here. | |
| `refusal.MARKUP-UNPROVEN` | It has formatting the import can't handle safely yet, so it can't be changed from here for now. | |
| `refusal.LINK-ONLY-UNPROVEN` | It is only a link, and the import can't handle that safely yet, so it can't be changed from here for now. | |
| `refusal.CLIENT-RULE` | It breaks one of the client's style rules. Edit it, then approve it again; if you can't see why, let the team know. | |
| `refusal.NUMBER-PARITY` | Its numbers don't match the English. Check the prices, dates and amounts, then approve it again. | |
| `refusal.META-BUDGET` | Too long for a search result. Shorten it, then approve it again. | |
| `refusal.POISON` | It is far longer than the English and may not be its translation. Check it, then approve it again. | |
| `refusal.EMPTY-TARGET` | The translation is empty. Write one, or undo the approval. | |
| `refusal.CSV-INJECTION` | It starts with = or @, which a spreadsheet reads as a formula. Change how it starts, then approve it again. | |
| `refusal.PLACEHOLDER-SET` | It has a link the English doesn't, or is missing one. Edit it so it has the same links, then approve it again. | |
| `refusal.PLACEHOLDER-ORDER` | Its links are in a different order than in the English, so they would open the wrong pages. Edit it, then approve it again. | |
| `refusal.PLACEHOLDER-BALANCE` | One of its links is broken. Edit it, then approve it again. | |
| `refusal.OG-TWIN-MISSING` | A page title goes with the title shown when the page is shared. Approve both, with the same words. | |
| `refusal.OG-TWIN-DIVERGED` | A page title and the title shown when the page is shared must have the same words. Make them match, then approve both again. | |
| `refusal.EXPORT-PRESENCE` | Its English is no longer on the page, so there is nothing to translate. | |
| `refusal.UNIT-RETIRED` | Its English is no longer on the page, so there is nothing to translate. | |
| `refusal.UNIT-MISMATCH` | The English changed after it was approved. Review it again. | |
| `refusal.ENGLISH-DRIFT` | The English changed after it was approved. Review it again. | |
| `refusal.UNSIGNED` | The approval wasn't saved through the desk. Approve it again. | |
| `refusal.BAD-SIGNATURE` | The approval doesn't match what was saved. Approve it again. | |
| `refusal.UNREGISTERED` | The approval doesn't say who made it. Approve it again. | |
| `refusal.OVERRIDE-UNNAMED` | It replaces a change made on the website, and the approval doesn't say who made it. Approve it again. | |
| `refusal.DUPLICATE` | The same text was approved twice with different words. Let the team know. | |
| `refusal.LANG-MISMATCH` | It was approved in another language's list. Let the team know. | |
| `refusal.BAD-ROLE` | This kind of text can't be imported. Let the team know. | |
| `refusal.CLIENT-RULE-WARN` | It went in the file, but it may break one of the client's style rules. Let the team know. | Same place, per text that went in |
| `refusal.PLACEHOLDER-COUNT-WARN` | It went in the file, but it uses a link more or fewer times than the English. Check it on the website. | |
| `refusal.CSV-INJECTION-WARN` | It went in the file. It starts with + or -: fine for Weglot, but don't open the file in a spreadsheet. | |
| `refusal.DEDUPED` | Some texts are on more than one page; each went in the file once. | Same place, once for the file |
| `refusal.NO-VERIFIER` | The approvals couldn't be checked, so no file was made. Let the team know. | Same place, instead of the file |
| `refusal.STALE-MANIFEST` | The texts are more than a week old, so no file was made. Let the team know. | |
| `refusal.TOO-LARGE` | The file would be too large for Weglot, so no file was made. Let the team know. | |
| `refusal.BOM` | The file came out in the wrong format, so no file was made. Let the team know. | |
| `refusal.ALL-LANGUAGES` | A file is made one language at a time, so no file was made. Let the team know. | |
| `refusal.NOT-CONVERGED` | The file couldn't be put together, so no file was made. Let the team know. | |
| `refusal.EXCEPTION-UNUSED` | An exception the team named matched no text, so no file was made. Let the team know. | |
| `refusal.EXPORT-SKIP-ALREADY-ON-THE-WEBSITE` | Already on the website: nothing to import. | Same place, per text not in the file |
| `refusal.EXPORT-SKIP-NOT-APPROVED` | Not approved, so it isn't in the file. | |
| `refusal.EXPORT-SKIP-NO-LONGER-ON-THE-PAGE` | Its English is no longer on the page, so there is nothing to translate. | |
| `refusal.EXPORT-SKIP-TRANSLATION-MOVED-SINCE-APPROVAL` | The translation on the website changed after it was approved. Review it again. | |
| `refusal.EXPORT-SKIP-APPROVED-AGAINST-AN-UNKNOWN-WORDING` | The approval doesn't record which wording it was given for. Approve it again. | |
| `refusal.EXPORT-SKIP-NOTHING-TO-SAY` | The approved wording is empty. Write one, or undo the approval. | |
| `refusal.EXPORT-SKIP-UNIT-RECORD-INCOMPLETE` | This text couldn't be checked. Let the team know. | |
| `refusal.EXPORT-SKIP-UNCHANGED-BY-THE-IMPORT` | The import didn't change it: nothing to put back. | When a file puts back an import |
| `refusal.EXPORT-SKIP-NO-BEFORE-VALUE` | What the website showed before wasn't recorded, so it can't be put back. Let the team know. | |
| `refusal.EXPORT-SKIP-THE-PAGE-SHOWED-THE-ENGLISH` | Before the import the website showed the English, so an import can't put it back. Let the team know. | |
| `refusal.suffix.EXCEPTED` | It went in the file anyway: the team allowed it for this text. | After the line above it |
| `refusal.suffix.RESTORE-WARN` | It went in the file anyway, to put back what the website showed before. | |

## Why a job failed

| Key | Text | Shown where |
|---|---|---|
| `job.failed.engine-did-not-start` | The job didn't start. Try again in a few minutes. | Job status, when a job failed |
| `job.failed.engine-stopped` | The job stopped before it finished. Try again; if it stops again, let the team know. | |
| `job.failed.engine-never-answered` | The job didn't answer for 35 minutes. Try again; if it happens again, let the team know. | |
| `job.failed.bad-job` | This couldn't be read, so it didn't run. Let the team know. | A box's line, when a job failed |
| `job.failed.bad-amount` | The send couldn't be priced, so nothing was sent. Send again. | |
| `job.failed.engine-error` | Something went wrong while it ran. Try again; if it happens again, let the team know. | |
| `job.failed.engine-not-configured` | This can't run until the team finishes setting it up. Let the team know. | |
| `job.failed.storage-error` | The desk's storage didn't answer. Try again in a few minutes. | |
| `job.failed.refresh-stopped` | The texts couldn't be brought up to date, so no file was made. Try again; if it happens again, let the team know. | |
| `job.failed.manifest-stale` | The texts were out of date, so no file was made. Try again. | |
| `job.failed.export-refused` | No file was made: | Followed by the file's own reasons (`refusal.*`) |
| `job.failed.export-empty` | Nothing could go in the file: | Followed by the texts left out (`refusal.*`) |
| `job.failed.stamps-not-landed` | It ran, but the desk couldn't record the result. Try again; if it happens again, let the team know. | A box's line, when a job failed |
| `job.failed.batch-not-found` | The Weglot file this check was for can't be found. Let the team know. | |
| `job.failed.no-batch` | There's no Weglot file to check yet. Get the file first. | |
| `job.failed.nothing-queued` | No requests are waiting, so nothing was sent. | |
| `job.failed.over-amount` | It would have cost more than expected, so nothing was sent. Send again. | |
| `job.failed.credit-probe-failed` | Gemini couldn't confirm there's credit to pay for it, so nothing was sent. Let the team know. | |
| `job.failed.gemini-error` | Gemini answered with an error. Try again later; if it happens again, let the team know. | |
| `job.failed.run-still-out` | An earlier send is still with Gemini. Check for new translations first, then send. | Also why Send is blocked (the plan's stops) |
| `job.failed.run-stuck-submitting` | An earlier send stopped halfway. Nothing more can be sent until the team clears it: let the team know. | Also why Send is blocked |
| `job.failed.quota-spent-today` | Gemini's limit for today is used up. Send again tomorrow. | Also why Send is blocked |
| `job.failed.over-run-cap` | That's more than one send may cost. Undo some requests, then send the rest. | Also why Send is blocked |
| `job.failed.over-day-cap` | That would go over what this language may spend with Gemini today. Send the rest tomorrow, or undo some requests. | Also why Send is blocked |
| `job.failed.no-run` | Nothing is waiting with Gemini. | A box's line, when a job failed |
| `job.failed.run-unreadable` | The record of an earlier send can't be read, so nothing more can be sent. Let the team know. | |
| `job.failed.run-not-collectable` | Those requests can't be collected: they were cancelled or already collected. Let the team know. | |
| `job.failed.nothing-arrived` | Gemini finished, but no new translations came back. Let the team know. | |
| `job.failed.page-not-found` | This page can't be found, so nothing was translated. Let the team know. | A box's line, when a page job failed |
| `job.failed.unit-not-on-page` | That paragraph is no longer on this page, so nothing was translated. Reload the page and try again. | A box's line, when a paragraph job failed |

## How this works (the help window)

| Key | Text | Shown where |
|---|---|---|
| `how.title` | How this works | Window heading |
| `how.close` | Close | Window button |

<!-- block how.body -->
### What you're looking at

Each row is one text from the website — a heading, a sentence, a button. On the left is the
English. On the right is what visitors in this language see today. Weglot translated all of
it by machine, and nobody has checked it yet.

### Your three choices

- **Approve** (the tick) — the translation is right as it is.
- **Edit** (the pencil) — write what it should say. Saving your wording approves the text with your words.
- **Ask Gemini for a new translation** (the star) — the translation is wrong and you'd like Gemini to try again.

Each text has one decision at a time. Choosing another replaces it, and clicking your current choice again undoes it.

### New translations from Gemini

When Gemini sends a new translation, it is shown in place of the website's, marked *New
translation to read*, with the website's words under it. Approve it as it is, change it, or ask
for another. *Show* → *New translations to read* lists only them.

### Start with the flagged texts

Our automatic checks look for mistakes that are almost always real: English left
untranslated, a price or date that changed, a missing link, or the wrong form of address
for the client's rules. Flagged texts say why under the translation, and *Flagged — check
these first* shows only them. That is usually a handful per language, not hundreds.

Some texts also appear on other pages of the website. Weglot keeps one translation for all
of them, so they say so and can't be changed from here yet.

### Working faster

Tick any texts — or the box in the heading to take everything on screen — and the bar at the
bottom applies one decision to all of them. On the keyboard, `J` and `K` move between texts,
`A` approves, `E` edits, `R` asks Gemini for a new translation, and `X` ticks.

### Nothing reaches the website by itself

The three boxes at the top work on every language at once.

- **Ask Gemini** counts the new translations you requested with ✦. **Send to Gemini** asks you to confirm the number, then sends them all to Gemini together. Their new translations come back to read, usually within 20 minutes; if Gemini is slower, **Check for new translations** fetches them.
- **Review** counts the flagged texts nobody has checked yet. **Show them** lists this language's in the table.
- **Weglot file** counts the approved texts that aren't in a file yet. **Get the file** makes one Weglot file for each language that has some. **Download** a language's file: the window that opens says how to import it in Weglot. Then press **I imported it**, and each file says how many of its texts the website shows; **Check again** looks again while some are missing.

Both lists open from the bar at the bottom, and anything in them can be undone, except a request while it's with Gemini.

<!-- /block -->

The help window ends with one of the two blocks below: the first while saving is switched off,
the second once it is on.

<!-- block how.saving.off -->
### Saving

Your decisions are kept in this browser as you make them. Saving them to the server is
switched off for now, until it can keep them private — so keep using this browser, and don't
clear its history or site data. Once saving is back, you'll be able to close the tab and carry
on from another computer.
<!-- /block -->

<!-- block how.saving.on -->
### Saving

Your decisions are saved by themselves a moment after you stop clicking. The bar at the bottom
says where saving stands; hover over it to see what that means.

- **All changes saved** — everything is on the server. You can close this page, or carry on from another computer.
- **Checking for changes…** — the page opens on what this computer saved last. Anything saved on another computer since shows up a moment later.
- **Changed elsewhere** — someone else saved the same texts first. They're marked in the list: choose again, or edit, to keep yours, or use theirs.
- **Offline**, **not saved yet** or **Saving stopped** — nothing is lost. Your changes are kept on this computer and saved as soon as the server answers. **Try again** saves them now.

A text you're editing keeps what you typed, even if someone else saves it meanwhile. When you
save yours, it is marked as changed elsewhere, so you choose which wording stays.
<!-- /block -->

## Document view (desk v2)

One page of the website read as a document: every text in the order the page shows it, English beside the translation, the translation edited in place. The saving lines (`autosave.*`, `save.reason.*`), the failed-job lines (`job.failed.*`), the refusals (`refusal.*`), the language and page names and the word for the home page (`row.shared.home`) are the ones above; this section holds only what is new.

| Key | Text | Shown where |
|---|---|---|
| `doc.meta.title` | Document view — Localization Desk — College of English Language | Browser tab, document view |
| `doc.meta.description` | Read a page as a document, English beside its translation, and edit the translation in place. | Page description |
| `doc.title` | {page} — {language} | Heading of the open page and language |
| `doc.grid.label` | Pages and languages | Heading of the grid at the top |
| `doc.grid.corner` | Page | Top-left cell of the grid |
| `doc.status.none` | Not translated | A grid cell with no text in that language |
| `doc.status.drafted` | Drafted | A grid cell where Gemini's drafts are waiting to be read |
| `doc.status.edited` | Edited | A grid cell with texts you have edited |
| `doc.status.exported` | Exported | A grid cell whose texts are in a Weglot file |
| `doc.status.unknown` | Checking… | A grid cell until that language has been read from the server |
| `doc.status.translating` | Translating… | A grid cell whose page Gemini is translating now |
| `doc.status.queued` | Queued | A grid cell whose page waits for the one Gemini is translating |
| `doc.cell.count.one` | {n} of {total} text | Under the status in a grid cell |
| `doc.cell.count.other` | {n} of {total} texts | |
| `doc.cell.aria` | {page}, {language}: {status} | Screen-reader name of a grid cell |
| `doc.undo` | Undo | Button in the bar at the bottom |
| `doc.redo` | Redo | Button in the bar at the bottom |
| `doc.undo.tip` | Undo your last change ({keys}) | Hover on Undo |
| `doc.redo.tip` | Redo ({keys}) | Hover on Redo |
| `doc.undo.none` | Nothing to undo | Hover on Undo when it is off |
| `doc.redo.none` | Nothing to redo | Hover on Redo when it is off |
| `doc.undo.dropped` | That step was skipped: the text has changed since. | Message after Undo or Redo when the text was changed again and the step could not be applied |
| `doc.keys.undo.mac` | ⌘Z | The keys, in the Undo hover, on a Mac |
| `doc.keys.undo.other` | Ctrl+Z | The keys, in the Undo hover, elsewhere |
| `doc.keys.redo.mac` | ⇧⌘Z | The keys, in the Redo hover, on a Mac |
| `doc.keys.redo.other` | Ctrl+Shift+Z | The keys, in the Redo hover, elsewhere |
| `doc.weglot.toggle` | Show Weglot | Checkbox in the bar at the bottom |
| `doc.translate` | Translate page | Button above the page, and in the window it opens |
| `doc.head.en` | English — the website | Head of the English column |
| `doc.head.tgt` | {language} — draft and your edits | Head of the translation column |
| `doc.head.weglot` | Weglot (on the website) | Head of the third column, when Show Weglot is on |
| `doc.block.meta-title` | Page title | Beside a text: what kind of text it is |
| `doc.block.og-title` | Title when shared | |
| `doc.block.meta-description` | Page description | |
| `doc.block.h1` | Heading 1 | |
| `doc.block.h2` | Heading 2 | |
| `doc.block.h3` | Heading 3 | |
| `doc.block.h4` | Heading 4 | |
| `doc.block.h5` | Heading 5 | |
| `doc.block.h6` | Heading 6 | |
| `doc.block.p` | Paragraph | |
| `doc.block.li` | List item | |
| `doc.block.button` | Button | |
| `doc.block.link` | Link | |
| `doc.block.other` | Text | |
| `doc.locked.tag` | Locked | Beside a text that can't be edited here |
| `doc.locked.noise` | Numbers and symbols are left as they are. | Under a locked text of numbers or symbols |
| `doc.also` | Also on {pages}. A change here changes it there too. | Under a text that is on other pages of the four |
| `doc.shared.one` | Also used on 1 other page ({example}). Your wording becomes the wording there too. | Under a text that is also on a page outside the four |
| `doc.shared.other` | Also used on {n} other pages ({example}, …). Your wording becomes the wording on all of them too. | |
| `doc.text.saving` | Saving… | Under a text, while its change is sent |
| `doc.text.saved` | Saved | Under a text, once its change is on the server |
| `doc.text.error` | Not saved yet — trying again | Under a text whose change did not go through |
| `doc.text.edited` | Edited | Under a text that has your edit |
| `doc.empty.cell` | Not translated yet | Inside an empty translation box |
| `doc.history` | History | Button under a text |
| `doc.history.title` | History of this text | Heading of the history panel |
| `doc.history.note` | Every change is saved on the server. Nothing is lost when you close the tab. | Top of the history panel |
| `doc.history.empty` | No saved changes yet. This text still reads as it first arrived. | History panel, for a text with no changes |
| `doc.history.draft` | Gemini's draft | History panel: who wrote that version |
| `doc.history.you` | You | History panel: who wrote that version |
| `doc.history.restore` | Restore this version | Button on a version in the history panel |
| `doc.history.close` | Close | Button on the history panel |
| `doc.history.restored` | Restored. Undo brings it back. | Message after Restore |
| `doc.history.failed` | Couldn't read the history. Try again in a moment. | History panel, when it can't be read |
| `doc.conflict.text` | {who} saved this text first: “{text}” | Under a text someone else saved before you |
| `doc.conflict.gone` | Someone else undid this text before you saved it. | Under a text someone else undid |
| `doc.conflict.mine` | Keep mine | Button under that line |
| `doc.conflict.theirs` | Take theirs | Button under that line |
| `doc.conflict.someone` | Someone | Stands for the name in that line when the saved text has no name on it |
| `doc.loading` | Loading the page… | Where the texts will be, while they load |
| `doc.load.failed` | Couldn't load this page. Reload to try again. | Where the texts will be, when they can't load |
| `doc.read.failed` | Couldn't read what's saved on the server. Reload to try again. | Above the page, when the saved texts can't be read |
| `doc.banner.none` | This page hasn't been translated into {language} yet. Gemini can write a first translation of every text on it; you then read it here and edit it. | Banner, on a page with no translation in that language |
| `doc.job.queued` | Gemini is translating this page. It can take a while: you can close this page, and the drafts will be here when it is done. | Banner, after Translate page |
| `doc.job.waiting` | Gemini is still translating {page} into {language}. This page starts as soon as that one is done, as long as this page stays open. | Banner, when another page is still being translated into that language (the queue lives in this window) |
| `doc.job.done` | New drafts from Gemini are ready. | Message when a translation finishes |
| `doc.job.failed` | The translation did not finish: {reason} | Banner, when a translation failed |
| `doc.job.failed.unknown` | something went wrong. Try again. | The reason, when none of the lines above fits |
| `doc.job.error` | Couldn't start the translation. Try again in a moment. | Message, when Translate page can't reach the server |
| `doc.confirm.title` | Translate this page with Gemini? | Heading of the window Translate page opens |
| `doc.confirm.body.one` | Gemini will write a first {language} translation of {n} text on this page. Texts you have edited are kept. | In that window |
| `doc.confirm.body.other` | Gemini will write a first {language} translation of {n} texts on this page. Texts you have edited are kept. | |
| `doc.confirm.cancel` | Cancel | Button in that window |
| `doc.outline.title` | On this page | Heading of the list of sections beside the page |
| `doc.outline.search` | Search result | The list's first entry: the page title and description as a search engine shows them |
| `doc.outline.count.one` | {n} text · {edited} edited | Under each entry of that list |
| `doc.outline.count.other` | {n} texts · {edited} edited | |
| `doc.sections` | Sections | Label of the list of sections on a narrow screen |
| `doc.words.one` | {n} word | Bottom bar: the size of the page in this language |
| `doc.words.other` | {n} words | |
| `doc.filter.label` | Show | Label of the list in the bottom bar that narrows the page to some of its texts |
| `doc.filter.all` | All texts | In that list: every text of the page |
| `doc.filter.new` | New from Gemini | In that list: texts Gemini wrote that you have not edited |
| `doc.filter.edited` | Edited | In that list: texts you have edited |
| `doc.filter.flagged` | Flagged by a check | In that list: texts our automatic checks point out |
| `doc.filter.empty` | No text matches this filter. Choose All texts to see the whole page again. | Above the page, when the chosen filter leaves no text |
| `doc.next` | Next to check | Button in the bottom bar: goes to the next text from Gemini or from a check that you have not looked at yet |
| `doc.next.left.one` | {n} left | Beside that button: how many texts are still to look at |
| `doc.next.left.other` | {n} left | |
| `doc.next.none` | Nothing left to check | Beside that button, when every such text has been looked at |
| `doc.keys.next.mac` | ⌥↵ | The keys that do the same as Next to check, on a Mac |
| `doc.keys.next.other` | Alt+Enter | The same, on any other computer |
| `doc.version` | Desk {version} | Bottom bar: the version of the localization desk; a link to what changed in it |
| `doc.version.tip` | See what changed in this version | Hover on that version |
| `doc.tools.label` | Actions for this text | Screen-reader name of the buttons beside the open text |
| `doc.tool.weglot` | Use Weglot's text | Button beside the open text, when Show Weglot is on |
| `doc.tool.revert` | Undo this | Button beside a text you have edited |
| `doc.chars.one` | {n} character | Under the page title and description: how long they are |
| `doc.chars.other` | {n} characters | |

## Export and re-translate (desk v2)

The Export window (pages x languages, one Weglot file for each) and the Re-translate windows of the document view. The refusals (`refusal.*`), the failed-job lines (`job.failed.*`, `doc.job.failed.unknown`), the saving reasons (`save.reason.*`) and `flow.file.stale` are the ones above; this section holds only what is new.

| Key | Text | Shown where |
|---|---|---|
| `export.button` | Export | Button above the document |
| `export.title` | Export the Weglot file | Heading of the Export window |
| `export.grid.page` | Page | Top-left cell of the Export window's grid |
| `export.all.pages` | All pages | Row of the Export window's grid that ticks a whole language |
| `export.all.languages` | All languages | Column of the Export window's grid that ticks a whole page |
| `export.aria.all` | All pages, all languages | Screen-reader name of the box that ticks everything |
| `export.aria.col` | All pages, {language} | Screen-reader name of a language's box |
| `export.aria.row` | {page}, all languages | Screen-reader name of a page's box |
| `export.aria.cell` | {page}, {language} | Screen-reader name of one page and language |
| `export.count.none` | Nothing selected yet | Under the grid, when no box is ticked |
| `export.count.one` | 1 file will be made | Under the grid |
| `export.count.other` | {n} files will be made | |
| `export.cancel` | Cancel | Button in the Export window |
| `export.go` | Export | Button in the Export window |
| `export.close` | Close | Button, when the export has finished |
| `export.download` | Download again | Button, when the export has finished |
| `export.jump` | Show | Button beside a text in the list of what was left out |
| `export.more` | Show {n} more | Button at the end of a long list |
| `export.step.waiting` | Waiting | A file's line, before its turn |
| `export.step.saving` | Saving your texts… | A file's line, while its texts are saved |
| `export.step.queued` | Waiting for the engine… | A file's line, while the engine has not started it |
| `export.step.running` | Making the file… | A file's line, while the engine makes it |
| `export.step.done.one` | 1 text in the file | A file's line, when it is made |
| `export.step.done.other` | {n} texts in the file | |
| `export.step.nothing` | Nothing to export yet | A file's line, when the page has no translation in that language |
| `export.step.failed` | Not made: {reason} | A file's line, when it could not be made |
| `export.group.refused.one` | 1 text is not in the file because a check refused it | List after an export |
| `export.group.refused.other` | {n} texts are not in the file because a check refused them | |
| `export.group.empty.one` | 1 text has no translation yet, so it is not in the file | List after an export |
| `export.group.empty.other` | {n} texts have no translation yet, so they are not in the file | |
| `export.group.orphan.one` | 1 edit belongs to English text that has changed, so it is not in the file | List after an export |
| `export.group.orphan.other` | {n} edits belong to English text that has changed, so they are not in the file | |
| `export.group.conflict.one` | 1 text was changed by someone else while you exported, so it is not in the file | List after an export |
| `export.group.conflict.other` | {n} texts were changed by someone else while you exported, so they are not in the file | |
| `export.group.unsaved.one` | 1 text could not be saved, so it is not in the file | List after an export |
| `export.group.unsaved.other` | {n} texts could not be saved, so they are not in the file | |
| `export.reason.refused-by-server` | The desk could not save this text, so it was not exported. | Under a text the desk could not save |
| `export.error.write` | Your texts could not be saved: {reason} | Inside a file's failed line |
| `export.error.start` | The export could not start: {reason} | Inside a file's failed line |
| `export.error.download` | The file is ready but could not be downloaded: {reason} | Inside a file's failed line |
| `retr.button` | Re-translate | Button beside the open text |
| `retr.page.button` | Re-translate page | Button above the document |
| `retr.text.title` | Re-translate this text | Heading of the window |
| `retr.text.body` | Gemini writes a new translation of this text. It takes about 1–3 minutes. The wording you have now stays in Undo. | The window's text |
| `retr.note.label` | Note for Gemini (optional) | Above the box where you can tell Gemini what to change |
| `retr.text.go` | Re-translate | Button in the window |
| `retr.page.title` | Re-translate this page | Heading of the window |
| `retr.page.body` | Gemini writes a new translation of this page. It takes about 1–3 minutes. Texts you have edited or exported are kept unless you tick Include my edits. | The window's text |
| `retr.page.mine` | Include my edits | Box in the window |
| `retr.page.go` | Re-translate page | Button in the window |
| `retr.cancel` | Cancel | Button in the windows |
| `retr.started` | Gemini is working on it. The new text appears here when it is ready. | Message, when the job starts |
| `retr.done` | The new translation is ready. | Message, when the job has finished |
| `retr.failed` | The new translation did not arrive: {reason} | Message, when the job failed |
| `retr.busy` | Gemini is already re-translating in this language. Try again when it has finished. | Message, when a re-translation is already running |
| `retr.none-arrived` | No new text arrived. | Message, when the job finished without a new text |

## Rules page (CEL-046)

The page where the client reads and edits the translation rules: /admin/localization/rules/. Every edit is a draft kept in this browser until "Use these rules" puts it in use (rulings 2026-10-19 23:32). Spec: monorepo runtime/out/loc2/rules-editor-spec.md §5.

| Key | Text | Shown where |
|---|---|---|
| `rules.meta.title` | Translation rules · CEL Dashboard | Browser tab |
| `rules.meta.description` | The rules Gemini follows when it translates the pages. | Page description |
| `rules.title` | Translation rules | Page title |
| `rules.language` | Language | Label of the language button in the title |
| `rules.desk` | Back to the desk | Header link to the document desk |
| `doc.rules` | Translation rules | Desk header link to the rules page |
| `rules.shared` | Shared rules | Rail, sheet label |
| `rules.shared.all` | Shared — all languages | Left sheet heading |
| `rules.shared.label` | Shared — applies to all 8 languages | Label above the shared rules |
| `rules.lang` | {language} rules | Right sheet heading, rail |
| `rules.outline` | On this page | Rail heading |
| `rules.none` | No rules yet | Language menu, after a language without rules |
| `rules.count.rules.one` | {n} rule | Rail count |
| `rules.count.rules.other` | {n} rules | Rail count |
| `rules.count.terms.one` | {n} term | Rail count |
| `rules.count.terms.other` | {n} terms | Rail count |
| `rules.count.briefs.one` | {n} brief | Rail count |
| `rules.count.briefs.other` | {n} briefs | Rail count |
| `rules.next` | The next translation uses Shared v{g}, {language} v{l} and the {language} glossary v{x} | Status bar |
| `rules.pending.one` | · {n} change not in use | Status bar, after the version note |
| `rules.pending.other` | · {n} changes not in use | Status bar, after the version note |
| `rules.draft.saving` | Saving draft… | Status bar |
| `rules.draft.saved` | Draft saved in this browser | Status bar |
| `rules.draft.hint` | Your draft is kept in this browser until you press Use these rules. Gemini keeps using the rules in use. | Status bar, on hover |
| `rules.inuse` | In use | Status bar with no draft; History, the version in use |
| `rules.use` | Use these rules | The one primary button |
| `rules.use.title` | Make these rules the ones in use? | Confirm dialog title |
| `rules.use.body` | The next translation of every page in {language} will use them. Earlier translations keep the version they were made with. | Confirm dialog text |
| `rules.using` | Putting the rules in use… | Status bar while publishing |
| `rules.toast.used` | In use: {list}. | Message after a publish |
| `rules.toast.used.undo` | Undo brings back the previous versions. | Message after a publish |
| `rules.toast.partial` | In use: {done}. Not in use yet: {rest}. | Message after a publish that stopped |
| `rules.toast.undo.partial` | Undo done for {done}; {scope} changed since. | Message after an undo that stopped |
| `rules.scope.global` | Shared rules | Scope name in messages and History |
| `rules.scope.lang` | {language} rules | Scope name in messages and History |
| `rules.scope.glossary` | {language} glossary | Scope name in messages and History |
| `rules.scope.brief` | {page} brief ({language}) | Scope name in messages and History |
| `rules.history` | History | Header button |
| `rules.history.title` | Changes | History drawer title |
| `rules.history.change` | Show change | History card button |
| `rules.history.loading` | Reading the versions… | History drawer while it reads |
| `rules.history.none` | No versions yet. | History drawer with nothing published |
| `rules.close` | Close | History drawer button |
| `rules.restore` | Restore this version | History card button, confirm title |
| `rules.restore.body` | Restore v{n}? The rules go back to how they were on {date}. v{m} stays in History. | Restore confirm text |
| `rules.toast.restored` | Restored v{n}. Undo brings v{m} back. | Message after a restore |
| `rules.toast.restored.undone` | The version before the restore is back in use. | Message after undoing a restore |
| `rules.brief.inuse` | v{n} in use | Page brief card |
| `rules.checked` | Checked automatically | Tag on a rule an automatic check enforces |
| `rules.checked.warn` | An automatic check still expects the old rule. Tell your CEL contact so the check changes too. | Under an edited checked rule |
| `rules.shared.warn` | This changes every language. | Under an edited shared rule |
| `rules.edited` | Edited | Under an edited rule |
| `rules.undothis` | Undo this | Under an edited rule |
| `rules.undo.edit` | edit | Undo step name |
| `rules.ph` | Type here | Empty text |
| `rules.empty` | No {language} rules from you yet. Gemini uses the shared rules only. | Language without rules |
| `rules.suggested` | Suggested by CEL (not confirmed) | Language without rules |
| `rules.suggested.use` | Start from the suggested ones | Language without rules |
| `rules.suggested.empty` | Start empty | Language without rules |
| `rules.suggested.first` | Register | The first rule's label when starting empty |
| `rules.toast.suggested` | Suggested rules added. Edit them as you like. | Message |
| `rules.conflict` | {name} published {scope} first (v{n}, {time}). | Notice on a scope someone else published |
| `rules.conflict.someone` | Someone | The conflict notice when the name and email are unknown |
| `rules.conflict.theirs` | See theirs | Conflict notice button |
| `rules.conflict.mine` | Keep mine | Conflict notice button |
| `rules.glossary` | Glossary | Section heading, rail |
| `rules.glossary.en` | English | Glossary column |
| `rules.glossary.keep` | Keep as is | Glossary column |
| `rules.glossary.add` | Add a term | Glossary button |
| `rules.remove` | Remove | Glossary row button |
| `rules.briefs` | Page briefs | Section heading, rail |
| `rules.brief.none` | No brief for this page yet | Page brief card |
| `rules.brief.add` | Add a brief | Page brief card |
| `rules.error` | The rules could not be put in use. Your draft is kept in this browser. | Notice on a scope |
| `rules.error.signed_out` | You have been signed out. Sign in again, then press Try again. Your draft is kept in this browser. | Notice on a scope (401) |
| `rules.error.cap` | Too many changes in a short time. Wait a few minutes, then press Try again. | Notice on a scope (over the cap) |
| `rules.error.daily` | Today's limit of changes is reached. Try again tomorrow; your draft is kept in this browser. | Notice on a scope (over the daily budget) |
| `rules.error.refused` | These rules were not accepted (an empty or too long text). Your draft is kept in this browser. | Notice on a scope (400) |
| `rules.error.read` | The rules could not be read. | Notice on a scope that could not be read |
| `rules.error.history` | The versions could not be read. | History drawer |
| `rules.retry` | Try again | Notice button |
| `rules.offline` | Offline — your draft is kept in this browser | Status bar, notice |
