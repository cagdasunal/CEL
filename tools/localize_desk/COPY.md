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
| `status.todo` | Not reviewed yet | Status badge |
| `status.arrived` | New translation to read | Status badge |
| `status.approved` | Approved | Status badge |
| `status.edited` | Approved with your edit | Status badge |
| `status.queued` | New translation requested | Status badge |
| `status.sending` | With Gemini… | Status badge |
| `status.failed` | Translation failed | Status badge (the reason shows on hover) |
| `status.exported` | In the import file | Status badge |
| `status.live` | On the website | Status badge |
| `action.approve` | Approve — this translation is right | Tick button |
| `action.approve.on` | Approved — click to undo | Tick button, when approved |
| `action.edit` | Write your own translation | Pencil button |
| `action.queue` | Ask Gemini for a new translation | Star button |
| `action.queue.on` | New translation requested — click to undo | Star button, when requested |
| `editor.label` | Your translation | Screen-reader name of the edit box |
| `editor.cancel` | Cancel | Edit box button |
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
| `save.button.one` | Save 1 change | The one blue button |
| `save.button.other` | Save {n} changes | The one blue button |
| `save.button.hint` | Stores your decisions on the server, so they survive this tab and anyone else reviewing sees them. | Hover text of Save |
| `save.button.hint_elsewhere` | {n} of them are in other languages. Save stores every language at once. | Hover text of Save |
| `save.elsewhere` | + {n} unsaved in other languages | Next to Save |
| `save.status.starting` | Starting… | Next to Save, while saving |
| `save.status.saving` | Saving… | Next to Save, while saving |
| `save.status.language` | Saving {language} ({i} of {count})… | Next to Save, several languages |
| `save.status.part` | Saving {language}, part {i} of {count}… | Next to Save, a large save |
| `save.status.failed` | Not saved | Next to Save, after a failure |
| `save.done.title` | Saved | Message, bottom right |
| `save.done.detail.one` | 1 change is stored. You can close this page or carry on from another computer. | Message |
| `save.done.detail.other` | {n} changes are stored. You can close this page or carry on from another computer. | Message |
| `save.done.detail_langs` | {n} changes are stored across {count} languages. You can close this page or carry on from another computer. | Message |
| `save.failed.title` | Not saved | Message |
| `save.failed.detail` | Nothing is lost — your work is still on this page. Please press Save again. ({reason}) | Message |
| `save.partial.title` | Saved {done} of {count} languages | Message |
| `save.partial.detail` | Nothing is lost — the rest is still on this page. Please press Save again. ({reason}) | Message |
| `save.reason.startup` | the save couldn't start | Reason inside the message |
| `save.reason.cancelled` | the save was cancelled | |
| `save.reason.timeout` | the save took too long | |
| `save.reason.server` | the server couldn't store it | |
| `save.reason.slow` | it is taking longer than expected | |
| `save.reason.refused` | the server refused it | |
| `save.reason.trouble` | the server is having trouble | |
| `save.reason.unconfirmed` | this site can't confirm saves yet | |
| `save.reason.unknown` | the save didn't finish | |
| `save.reason.not_configured` | saving isn't set up on this site yet | |
| `save.reason.too_large` | one text is too long to send | |

## Messages (bottom right)

| Key | Text | Shown where |
|---|---|---|
| `toast.close` | Close message | Screen-reader name of the × on a message |
| `toast.approved.one` | 1 text approved | After Approve on a selection |
| `toast.approved.other` | {n} texts approved | |
| `toast.approved.detail` | They go to the website once an import file is made and imported into Weglot. | |
| `toast.requested.one` | 1 new translation requested | After asking Gemini for a selection |
| `toast.requested.other` | {n} new translations requested | |
| `toast.requested.detail` | Nothing goes to Gemini until the requests are sent. | |
| `toast.already.one` | 1 was already set. | Added to the two messages above |
| `toast.already.other` | {n} were already set. | |
| `toast.inflight.title` | Nothing changed | When every selected text is with Gemini |
| `toast.inflight.one` | 1 text is with Gemini right now. You can decide once it comes back. | |
| `toast.inflight.other` | {n} texts are with Gemini right now. You can decide once they come back. | |
| `toast.edited.title` | Approved with your edit | After Save changes in the edit box |
| `toast.edited.detail` | Press Save at the bottom to store it. | |
| `toast.undone.title` | Undone | After Undo in a list |
| `toast.undone.one` | 1 text is back to Not reviewed yet. | |
| `toast.undone.other` | {n} texts are back to Not reviewed yet. | |
| `toast.updated.one` | 1 text updated | When new translations arrive |
| `toast.updated.other` | {n} texts updated | |
| `toast.updated.arrived.one` | 1 new translation to read. | |
| `toast.updated.arrived.other` | {n} new translations to read. | |
| `toast.updated.failed.one` | 1 translation failed. | |
| `toast.updated.failed.other` | {n} translations failed. | |
| `toast.updated.live.one` | 1 is now on the website. | |
| `toast.updated.live.other` | {n} are now on the website. | |
| `toast.storage.title` | Your browser isn't keeping your work | When the browser refuses to store |
| `toast.storage.detail` | Everything on screen is still right, but reloading would lose it. Press Save now. | |
| `toast.saved_load.title` | Couldn't load decisions saved earlier | When saved decisions can't be read |
| `toast.saved_load.detail` | You may not see decisions made on another computer. Reload before reviewing, or saving could overwrite them. | |
| `toast.load.title` | This language couldn't be loaded | When the texts can't be read |
| `toast.load.detail` | {error}. Please reload the page, and let us know if it keeps happening. | |

## The two lists (approved, requested)

| Key | Text | Shown where |
|---|---|---|
| `list.close` | Close | Button and the × |
| `list.select_all` | Select all | Checkbox label |
| `list.select_all.label` | Select every text in this list | Screen-reader name of that checkbox |
| `list.selected` | {n} selected | Checkbox label, with a selection |
| `list.undo` | Undo | Button, nothing selected |
| `list.undo_n` | Undo {n} | Button, with a selection |
| `list.undo_all` | Undo all | Button |
| `list.undo_all.confirm` | Undo all {n}? They go back to Not reviewed yet. | Confirmation |
| `list.row.undo` | Undo — back to Not reviewed yet | Hover text of a row's undo |
| `list.row.undo.label` | Undo this text | Screen-reader name of a row's undo |
| `list.draft.title` | New translations requested | List heading |
| `list.draft.summary.one` | 1 text is waiting for a new translation from Gemini. | Under the heading |
| `list.draft.summary.other` | {n} texts are waiting for a new translation from Gemini. | Under the heading |
| `list.draft.notice` | Save keeps this list. Sending requests to Gemini isn't switched on yet — when it is, you'll see how many texts and what it costs before anything is sent. | Bottom of the list |
| `list.csv.title` | Approved | List heading |
| `list.csv.summary.one` | 1 text is approved and waiting to go to the website. | Under the heading |
| `list.csv.summary.other` | {n} texts are approved and waiting to go to the website. | Under the heading |
| `list.csv.notice` | Nothing reaches the website by itself. Save keeps your approvals. Making the Weglot import file isn't switched on yet — your approvals will be waiting when it is. | Bottom of the list |

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

Approved texts wait for the import file. New-translation requests wait until they're sent to
Gemini, and you'll see how many and roughly what it costs first. Both lists open from the bar
at the bottom, and anything in them can be undone.

### Saving

Your decisions stay on this page as you make them. **Save** stores them on the server, so you
can close the tab, come back tomorrow, or carry on from another computer.
<!-- /block -->
