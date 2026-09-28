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
| The file handed to Weglot | **the import file** | the CSV, the export, the export file |
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
| `meta.index.title` | Localization Desk — English College | Browser tab, language list |
| `meta.index.description` | Check how the four Vancouver pages read in every language. | Page description |
| `meta.locale.title` | {language} — Localization Desk — English College | Browser tab, one language |
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
| `index.footnote` | Nothing here changes the website directly. Approved texts reach the website only when an import file is made and imported into Weglot. | Under the cards |

## One language — header and filters

| Key | Text | Shown where |
|---|---|---|
| `locale.eyebrow` | LOCALIZATION DESK · {LANGUAGE} | Small heading, top left |
| `locale.subtitle` | {total} texts | Under the heading |
| `locale.help` | How this works | Button, top right |
| `locale.langs.label` | Choose a language | Screen-reader name of the language tabs |
| `locale.langs.hover` | {language} | Hover text of a language tab, nothing flagged left |
| `locale.langs.hover_flagged.one` | {language} — 1 flagged text not reviewed yet | Hover text of a language tab |
| `locale.langs.hover_flagged.other` | {language} — {n} flagged texts not reviewed yet | Hover text of a language tab |
| `filter.page` | Page | Filter label |
| `filter.page.all` | All pages | Page filter option |
| `filter.show` | Show | Filter label |
| `filter.search` | Search | Filter label |
| `filter.search.placeholder` | English or {language} | Search box, empty (keep it short: the box is narrow) |
| `show.check` | Flagged — check these first ({n}) | Show filter. Opens by default |
| `show.arrived` | New translations to read ({n}) | Show filter |
| `show.todo` | Not reviewed yet ({n}) | Show filter |
| `show.all` | All texts ({n}) | Show filter |
| `show.csv` | Approved ({n}) | Show filter (includes your edits) |
| `show.edited` | Approved with your edit ({n}) | Show filter |
| `show.draft` | New translation requested ({n}) | Show filter |
| `show.sending` | With Gemini ({n}) | Show filter |
| `show.failed` | Translation failed ({n}) | Show filter |
| `show.exported` | In the import file ({n}) | Show filter |
| `show.live` | On the website ({n}) | Show filter |
| `count.line` | Showing {shown} of {total} texts | Under the filters |
| `count.failed` | Couldn't load the texts ({error}). | Under the filters, when loading fails |
| `table.empty` | No texts match these filters. | Instead of the table |
| `table.empty.reset` | Show all texts | Button under that line: clears Page, Show and Search |

## One language — the import file and Gemini

The panel under the heading. Each button starts one job in the engine; each half's line says where
its job stands.

| Key | Text | Shown where |
|---|---|---|
| `jobs.label` | The import file and Gemini | Screen-reader name of the panel under the heading |
| `jobs.working` | Working on it — about a minute. | A half's line, while its job runs |
| `jobs.unsaved` | Wait until the bar says “All changes saved”: the file and the requests are made from what's saved. | Hover text of the panel's buttons, while this language has unsaved changes |
| `jobs.start.failed` | It couldn't start: {reason}. Try again. | A half's line, when the server didn't take the job ({reason} is one of the `save.reason.*` lines) |
| `jobs.start.unavailable` | This can't run right now. Let the team know. | A half's line, when the server has no engine set up (503) |
| `jobs.read.failed` | Couldn't check how it's going. Trying again… | A half's line, when reading a job's progress fails |
| `jobs.file.title` | The import file | Heading of the first half |
| `jobs.file.idle` | Approved texts reach the website through the import file: get it here, then import it in Weglot. | Its line, before any file |
| `jobs.file.make` | Get the import file ({n} approved) | Its button (runbook F1) |
| `jobs.file.make.none` | No approved text is waiting for a file. Approve one first. | Hover text of that button, with nothing approved |
| `jobs.file.ready.one` | The import file is ready: 1 text. | Its line, once a file is made |
| `jobs.file.ready.other` | The import file is ready: {n} texts. | |
| `jobs.file.download` | Download the import file | Button |
| `jobs.file.out.one` | 1 text isn't in the file: | Heading of the list of texts left out (each line a `refusal.*`) |
| `jobs.file.out.other` | {n} texts aren't in the file: | |
| `jobs.file.notes.one` | 1 text went in with something to check: | Heading of the list of texts that went in with a `-WARN` or suffix line |
| `jobs.file.notes.other` | {n} texts went in with something to check: | |
| `jobs.file.imported` | I imported it | Button, once a file is ready (runbook F2) |
| `jobs.file.live` | On the website: {live} of {n} texts. | Its line, after the check |
| `jobs.file.waiting` | The website can take a few minutes to show an import. Check again in a few minutes. | Under that, while some aren't there yet |
| `jobs.file.again` | Check again | The same button, then |
| `jobs.gemini.title` | Gemini | Heading of the second half |
| `jobs.gemini.idle` | When you ask Gemini for new translations, the requests wait here until you send them. | Its line, before anything is sent |
| `jobs.gemini.plan.one` | Send 1 request to Gemini | Its button (runbook F3) |
| `jobs.gemini.plan.other` | Send {n} requests to Gemini | |
| `jobs.gemini.plan.none` | No requests are waiting. Ask Gemini for a new translation first. | Hover text of that button, with none waiting |
| `jobs.gemini.estimate.one` | 1 text: about ${cost}. Nothing is sent until you press Send. | Its line, once Gemini's price is known |
| `jobs.gemini.estimate.other` | {n} texts: about ${cost}. Nothing is sent until you press Send. | |
| `jobs.gemini.nothing` | Nothing to send: every request is already with Gemini, or was undone. | Its line, when the price check finds no text to send |
| `jobs.gemini.send` | Send (about ${cost}) | Button after the price (the amount is the ceiling the job may spend) |
| `jobs.gemini.sending` | With Gemini. It can take up to 20 minutes; you can keep working. | Its line, while Gemini works |
| `jobs.gemini.arrived.one` | 1 new translation to read. | Its line, when they're back |
| `jobs.gemini.arrived.other` | {n} new translations to read. | |
| `jobs.gemini.slow` | Gemini hasn't finished yet. Check again in a few minutes. | Its line, when Gemini is slower than 20 minutes |
| `jobs.gemini.collect` | Check for new translations | The button then |
| `jobs.start.daily` | Today's limit is reached: this works again tomorrow. | A half's line, when the server refused the start for the daily cap |
| `jobs.file.download.failed` | The import file couldn't be downloaded: {reason}. Try again. | Its line, when the download failed ({reason} is one of the `save.reason.*` lines) |

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
| `status.exported` | In the import file | Status badge |
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
| `toast.approved.detail` | They go to the website once an import file is made and imported into Weglot. | |
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
| `list.csv.notice` | Nothing reaches the website by itself. Your approvals are saved and wait for the next Weglot import file. | Bottom of the list |

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

## Why a text can't go in the import file

Shown under the import file's button, one line per text that was left out; the `-WARN` lines are texts that
went in the file with something to check. A line naming no text ("no file was made") is the whole job's.

| Key | Text | Shown where |
|---|---|---|
| `refusal.CONTAINMENT` | Used on other pages too: it can't be changed from here. | Under Get the Weglot file, per text left out |
| `refusal.LEGACY-COLLISION` | Another import already sets this text (housing and course details), so it can't be changed from here. | |
| `refusal.SUMMARY-OWNED` | The page summary writes this text, so it can't be changed from here. | |
| `refusal.MARKUP-UNPROVEN` | It has formatting the import can't handle safely yet, so it can't be changed from here for now. | |
| `refusal.LINK-ONLY-UNPROVEN` | It is only a link, and the import can't handle that safely yet, so it can't be changed from here for now. | |
| `refusal.CLIENT-RULE` | It breaks one of the client's style rules; the note under the translation says which. Edit it, then approve it again. | |
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
| `refusal.CLIENT-RULE-WARN` | It went in the file, but it may break one of the client's style rules; the note under the translation says which. | Same place, per text that went in |
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
| `job.failed.bad-job` | This couldn't be read, so it didn't run. Let the team know. | A half's line, when a job failed |
| `job.failed.bad-amount` | The price to send wasn't clear, so nothing was sent. Get the price again, then send. | |
| `job.failed.engine-error` | Something went wrong while it ran. Try again; if it happens again, let the team know. | |
| `job.failed.engine-not-configured` | This can't run until the team finishes setting it up. Let the team know. | |
| `job.failed.storage-error` | The desk's storage didn't answer. Try again in a few minutes. | |
| `job.failed.refresh-stopped` | The texts couldn't be brought up to date, so no file was made. Try again; if it happens again, let the team know. | |
| `job.failed.manifest-stale` | The texts were out of date, so no file was made. Try again. | |
| `job.failed.export-refused` | No file was made: | Followed by the file's own reasons (`refusal.*`) |
| `job.failed.export-empty` | Nothing could go in the file: | Followed by the texts left out (`refusal.*`) |
| `job.failed.stamps-not-landed` | It ran, but the desk couldn't record the result. Try again; if it happens again, let the team know. | A half's line, when a job failed |
| `job.failed.batch-not-found` | The import file this check was for can't be found. Let the team know. | |
| `job.failed.no-batch` | There's no import file to check yet. Get the import file first. | |
| `job.failed.nothing-queued` | No requests are waiting, so nothing was sent. | |
| `job.failed.over-amount` | Gemini's price went up since you saw it, so nothing was sent. Get the new price, then send. | |
| `job.failed.credit-probe-failed` | Gemini couldn't confirm there's credit to pay for it, so nothing was sent. Let the team know. | |
| `job.failed.gemini-error` | Gemini answered with an error. Try again later; if it happens again, let the team know. | |
| `job.failed.run-still-out` | An earlier send is still with Gemini. Check for new translations first, then send. | Also why Send is blocked (the plan's stops) |
| `job.failed.run-stuck-submitting` | An earlier send stopped halfway. Nothing more can be sent until the team clears it: let the team know. | Also why Send is blocked |
| `job.failed.quota-spent-today` | Gemini's limit for today is used up. Send again tomorrow. | Also why Send is blocked |
| `job.failed.over-run-cap` | That's more than one send may cost. Undo some requests, then send the rest. | Also why Send is blocked |
| `job.failed.over-day-cap` | That would go over what this language may spend with Gemini today. Send the rest tomorrow, or undo some requests. | Also why Send is blocked |
| `job.failed.no-run` | Nothing is waiting with Gemini. | A half's line, when a job failed |
| `job.failed.run-unreadable` | The record of an earlier send can't be read, so nothing more can be sent. Let the team know. | |
| `job.failed.run-not-collectable` | Those requests can't be collected: they were cancelled or already collected. Let the team know. | |
| `job.failed.nothing-arrived` | Gemini finished, but no new translations came back. Let the team know. | |

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

Approved texts reach the website through the import file: **Get the import file** at the top of the page makes it, you import it in Weglot, and **I imported it** checks that the website shows it. Requests go to Gemini with **Send requests to Gemini**; the desk shows what that costs before anything is sent. Both lists open from the bar at the bottom, and anything in them can be undone, except a request while it's with Gemini.

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
