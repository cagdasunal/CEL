# Localization Desk — every word on screen

This document is the **only** place the desk's wording lives. The page generators
(`generate_document_page.py`, `generate_rules_page.py`) read it every time the desk is built,
and a test fails if the pages show a word that is not in here, or if this document holds a line
nothing uses. To change what the desk says: edit this file, rebuild the desk (`cd tools &&
python3 -m localize_desk.generate_document_page && python3 -m localize_desk.generate_rules_page`),
commit both.

**How to edit**

- Change the **Text** column only. The **Key** is how the code finds the line.
- Words in `{braces}` are filled in by the page (a number, a language). Keep them.
- Keys ending in `.one` / `.other` are the singular and plural of the same line.
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

## One language — the three boxes at the top

Ask Gemini, Review and the Weglot file, for every language at once. Each box has a count, its
button, and a line that says only where its job stands. No price is shown (the operator,
2026-09-29): the engine caps what a send may spend.

| Key | Text | Shown where |
|---|---|---|
| `flow.file.stale` | This file is out of date: get the file again. | Its line, when a file was made before a later decision, or over an hour ago |


## One language — the table

| Key | Text | Shown where |
|---|---|---|
| `row.shared.home` | the home page | Stands in for "/" in the line above |

## One language — the bar at the bottom

| Key | Text | Shown where |
|---|---|---|
| `autosave.saved` | All changes saved | Bar status, when everything is on the server |
| `autosave.saving.one` | Saving 1 change… | Bar status, while a change is on its way |
| `autosave.saving.other` | Saving {n} changes… | |
| `autosave.retrying.one` | 1 change not saved yet — {reason}. Trying again… | Bar status, when a save failed and will be tried again |
| `autosave.retrying.other` | {n} changes not saved yet — {reason}. Trying again… | |
| `autosave.offline.one` | Offline — 1 change kept on this computer | Bar status, with no connection |
| `autosave.offline.other` | Offline — {n} changes kept on this computer | |
| `autosave.conflict.one` | 1 text changed elsewhere | Bar status, when someone else saved first |
| `autosave.conflict.other` | {n} texts changed elsewhere | |
| `autosave.conflict.where` | In {language}, {page} | Beside the bar, when texts changed elsewhere: where the first one is |
| `autosave.conflict.go` | Go to it | Button beside the bar, when texts changed elsewhere: opens that page and language and goes to the text |
| `autosave.refused.one` | 1 text not saved | Bar status, when the server turned texts down |
| `autosave.refused.other` | {n} texts not saved | |
| `autosave.stopped` | Saving stopped: {reason} | Bar status, when saving can't go on by itself |
| `autosave.retry` | Try again | Bar button, when saving stopped or is waiting to try again |
| `save.reason.offline` | there is no connection | Reason inside the status and the message |
| `save.reason.reload` | this page is out of date — reload it | |
| `save.reason.signed_out` | you have been signed out — sign in again, then press Try again | |
| `save.reason.cap` | a lot was saved at once — it starts again by itself in a few minutes | |
| `save.reason.daily` | today's saving limit is reached — it starts again tomorrow | |
| `save.reason.unavailable` | saving isn't available right now | |
| `save.reason.refused` | the server refused it | |
| `save.reason.trouble` | the server is having trouble | |

## Messages (bottom right)

| Key | Text | Shown where |
|---|---|---|
| `toast.storage.title` | This browser can't keep a copy of your work | When the browser refuses to store |

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
| `doc.weglot.none` | No Weglot translation yet | Inside the third column, for a text Weglot has no wording for |
| `doc.weglot.same` | Same as Weglot | Under a text, when Show Weglot is on and the text is word for word what Weglot has |
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
| `doc.also` | Also on {pages}. A change here changes it there too. | The marker's tooltip and popover of a text that is on other pages of the four; once in the note under the text while it has focus |
| `doc.shared.one` | Also used on 1 other page ({example}). Your wording becomes the wording there too. | The marker's tooltip and popover of a text that is also on a page outside the four; once in the note under the text while it has focus |
| `doc.shared.other` | Also used on {n} other pages ({example}, …). Your wording becomes the wording on all of them too. | |
| `doc.mark.one` | Shared with 1 other page. | The shared-text marker's accessible name, read before the sentence (its chip shows the count) |
| `doc.mark.other` | Shared with {n} other pages. | |
| `doc.text.saving` | Saving… | Under a text, while its change is sent |
| `doc.text.saved` | Saved | Under a text, once its change is on the server |
| `doc.text.error` | Not saved yet — trying again | Under a text whose change did not go through |
| `doc.text.refused` | Not saved — the server refused this text. Edit it to try again. | Under a text the server did not take |
| `doc.text.stopped` | Not saved — saving has stopped. See the bar below. | Under a text waiting while saving is stopped |
| `doc.text.offline` | Not saved yet — you are offline. It is kept on this computer. | Under a text changed while offline |
| `doc.text.retranslating` | Gemini is re-translating this text… | Under a text whose Re-translate is on its way |
| `doc.save.go` | Go to the text | Button beside the bar, when a text on this page is not saved |
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
| `doc.next.again.one` | Show 1 looked-at text again | Button beside the count, when Next has marked a text of this page as looked at |
| `doc.next.again.other` | Show {n} looked-at texts again | |
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
| `export.count.other` | {n} files will be made, in one zip | |
| `export.cancel` | Cancel | Button in the Export window |
| `export.go` | Export | Button in the Export window |
| `export.close` | Close | Button, when the export has finished |
| `export.stop` | Stop after this file | Button while the export runs: the file being made finishes, the next ones are not started |
| `export.stopping` | Stopping after this file… | The same button once pressed |
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
| `export.step.stopped` | Not started — you stopped the export | A file's line, when the export was stopped before it |
| `export.result.done` | Files made: {done} of {total}. The download has started. | Top of the result, when the export ran to the end |
| `export.result.stopped` | You stopped the export. Files made: {done} of {total}; what was made is downloading. | Top of the result, when the export was stopped |
| `export.result.none` | No file was made. | Top of the result, when no file came out |
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
| `retr.text.title` | Re-translate this text | Heading of the window |
| `retr.text.body` | Gemini writes a new translation of this text. It takes about 1–3 minutes. The wording you have now stays in Undo. | The window's text |
| `retr.note.label` | Note for Gemini (optional) | Above the box where you can tell Gemini what to change |
| `retr.text.go` | Re-translate | Button in the window |
| `retr.page.title` | Re-translate this page | Heading of the window |
| `retr.page.body` | Gemini writes a new translation of this page. It takes about 1–3 minutes. Texts you have edited or exported are kept unless you tick Include my edits. | The window's text |
| `retr.page.mine` | Include my edits | Box in the window |
| `retr.page.count.one` | Gemini's new wording replaces {n} text you edited or approved. | Line in the window, under the box, once it is ticked and the page has edited or approved texts |
| `retr.page.count.other` | Gemini's new wording replaces {n} texts you edited or approved. | |
| `retr.page.go` | Re-translate page | Button in the window |
| `retr.cancel` | Cancel | Button in the windows |
| `retr.started` | Gemini is working on it. The new text appears here when it is ready. | Message, when the job starts |
| `retr.done` | The new translation is ready. | Message, when the job has finished |
| `retr.failed` | The new translation did not arrive: {reason} | Message, when the job failed |
| `retr.busy` | Gemini is already re-translating in this language. Try again when it has finished. | Message, when a re-translation is already running |
| `retr.wait` | Gemini is re-translating another text in this language. Re-translate is on again when it has finished. | Tooltip of the Re-translate buttons of the other texts, while one text of the language is being re-translated |
| `retr.timeout` | Gemini did not answer in time. Try again. | The reason in the message, when a re-translation never finished |
| `retr.none-arrived` | No new text arrived. | Message, when the job finished without a new text |

## Rules page (CEL-046, read-only since CEL-080)

The page where the client reads the translation rules per language: /admin/localization/rules/. Version 1 only shows them: one language at a time, the shared rules first, then that language's own rules and its glossary. Nothing on it edits, saves or publishes, and the page-level briefs are not shown.

| Key | Text | Shown where |
|---|---|---|
| `rules.meta.title` | Translation rules · CEL Dashboard | Browser tab |
| `rules.meta.description` | The rules Gemini follows when it translates the pages. | Page description |
| `rules.title` | Translation rules | Page title |
| `rules.language` | Language | Label of the language tabs |
| `rules.desk` | Back to the desk | Header link to the document desk |
| `doc.rules` | Translation rules | Desk header link to the rules page |
| `rules.shared.all` | Shared — all languages | Heading of the shared rules |
| `rules.lang` | {language} rules | Heading of one language's rules |
| `rules.empty` | No {language} rules from you yet. Gemini uses the shared rules only. | Language without rules |
| `rules.glossary` | Glossary | Heading of the glossary |
| `rules.glossary.en` | English | Glossary column |
| `rules.glossary.keep` | Don't translate | Glossary column |
| `rules.glossary.yes` | Yes | Glossary cell of a term that stays as it is |
| `rules.glossary.empty` | No glossary terms yet. | Glossary without terms |
| `rules.error.read` | The rules could not be read. | Notice on a part that could not be read |
| `rules.error.offline` | You are offline. Reconnect, then press Try again. | Notice on a part that could not be read |
| `rules.error.signed_out` | You have been signed out. Sign in again, then press Try again. | Notice (401) |
| `rules.error.cap` | Too many requests in a short time. Wait a few minutes, then press Try again. | Notice (over the cap) |
| `rules.retry` | Try again | Notice button |
