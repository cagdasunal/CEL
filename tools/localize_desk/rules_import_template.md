# Translation rules: changes template

I made this file so an AI tool can write your changes for you. You do not need to write the format yourself.

1. Copy the prompt in part 1 into Claude or ChatGPT.
2. Below the prompt, tell it what you want changed, in your own words. If you downloaded "Your current rules" from the Import tab, paste it too, so the AI can use the right rule IDs.
3. Save the answer as a .md file and upload it on the Import tab. I show you every change before anything is applied.

## 1. Prompt for your AI tool

Copy everything between the two lines of equals signs.

~~~
==========
You help me change the translation rules of an English language school website.
Write a "changes only" file in Markdown. Follow these rules exactly.

OUTPUT
- Output only the changes file. No explanations, no greetings, no sign-off.
- Keep it short. Cut every unnecessary word. One change per line.
- Do not repeat rules or words that stay the same.

LANGUAGES
- One section per language, as a heading: ## German (DE)
- Use only these 8 codes: DE German, FR French, ES Spanish, PT Portuguese, IT Italian, JA Japanese, KO Korean, AR Arabic.
- Put the changes of each language only in its own section.

RULES (under the heading ### Rules)
- New rule: - ADD: <rule text>
- Change a rule: - EDIT DE-12: <the complete new text>
- Delete a rule: - REMOVE DE-12
- Every rule has an ID such as DE-12. Always keep the ID exactly as I give it when you edit or remove.
- Never invent an ID. A new rule has no ID.
- An EDIT replaces the whole rule, so write the complete new text.

WORDS (under the heading ### Words)
- A table with the columns: | Action | Term | Translation | Type |
- Action is ADD, EDIT or REMOVE. Term is the English term.
- Type is exactly one of: Keep as is, Always translate as, Search keyword.
- Keep as is: brand and place names that stay untranslated. Leave Translation empty.
- Always translate as: the translation must be exactly this.
- Search keyword: a search phrase, used where it sounds natural.
- For REMOVE, fill only Action and Term.

Do not add anything I did not ask for.

MY CHANGES:
(I write my wishes here, or paste my rules file.)
==========
~~~

## 2. The format, in short

| What | Line |
|---|---|
| Language | `## German (DE)` |
| Add a rule | `- ADD: text` |
| Change a rule | `- EDIT DE-12: complete new text` |
| Delete a rule | `- REMOVE DE-12` |
| Word change | `\| ADD \| term \| translation \| Type \|` |

Type is one of: Keep as is, Always translate as, Search keyword.
A small slip, such as a wrong bullet or a broken table, is fine. I read the file with an AI model and show you what I understood. A line I cannot place is listed under "Couldn't place these lines", and nothing changes until you Apply.

## 3. Your changes

Save the AI's answer as its own .md file and upload that file.
If you write your changes in this file instead, put them below this line and delete everything above the line before you upload it.

---

<!--
EXAMPLE (stripped when the file is downloaded; the tests read it): what the reader must find in a filled changes file.
~~~
## German (DE)
### Rules
- ADD: Write dates as 31.12.2026.
- EDIT DE-12: Use "Studiengebühren" for "tuition fees".
- REMOVE DE-9
### Words
| Action | Term | Translation | Type |
|---|---|---|---|
| ADD | Pacific Beach | | Keep as is |
| ADD | homestay | Gastfamilie | Always translate as |
| REMOVE | exam prep | | |

## French (FR)
### Rules
- EDIT FR-9: Keep sentences under 20 words.
### Words
| Action | Term | Translation | Type |
|---|---|---|---|
| ADD | English school San Diego | école d'anglais San Diego | Search keyword |
| EDIT | homestay | famille d'accueil | Always translate as |

## Italian (IT)
### Rules
- REMOVE IT-4: no longer needed.
### Words
| Action | Term | Translation | Type |
|---|---|---|---|
| ADD | English course in San Diego | corso di inglese a San Diego | Search keyword |
| REMOVE | La Jolla | | |
~~~
-->

<!--
MAINTAINER NOTE (stripped when the file is downloaded): keep in sync with the final format file (rules-import-format.md).
1. Part 1 prompt: RULES, WORDS and LANGUAGES blocks must match its "Rule lines", "Word list lines" and "Languages".
2. The three Type names and the 8 codes (part 1 and part 2) must match its Type list and language list.
3. Part 2 table and the EXAMPLE comment must still parse: ADD:, EDIT <ID>:, REMOVE <ID>, and the 4-column word table.
4. The "Your current rules" title, the "Couldn't place these lines" heading, "Apply" and "I show you every change" wording must match the Import tab copy in COPY.md (import.current, import.unplaced, import.apply).
5. The ID shape (DE-12, prefix plus digits) must match rule-id-scheme.md.
6. The filled example is NOT in the downloaded file (it is the EXAMPLE comment above, stripped like this note): the client may upload the file they downloaded, and Apply is all or nothing, so it must hold no change lines of its own. Part 3 says to upload the AI's answer as its own file, or to delete everything above the line first (test_the_downloaded_template_proposes_none_of_the_examples_changes_when_uploaded_unchanged).
-->
