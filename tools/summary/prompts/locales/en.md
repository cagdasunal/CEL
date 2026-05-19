# English (en) — Locale Layer

## Direction + script
LTR, Latin script. Standard 60-char title / 130-char description limits apply (Google SERP truncation).

## Tone + register
Direct, factual, professional. Action-oriented. Standard American English unless source clearly uses BrE conventions; match the source's existing spelling ("color" vs "colour").

## Text expansion factor
Baseline. No conversion applied for translation arithmetic.

## Punctuation conventions
US standard. No em dashes (universal rule from common.md). Oxford comma optional — match source. Curly quotes (' ") preferred over straight quotes in prose.

## Number + currency formatting
- Thousands: comma (1,000). Decimal: period (3.5).
- Currency: `$1,890` for USD (no space), `$1,890 CAD` only when distinguishing from USD in Canadian context.
- Time: 12-hour with AM/PM ("9:00 AM"), or 24-hour ("09:00") if source uses it.

## Date format
"March 15, 2026" (US) or "15 March 2026" (international/UK) — match source. Never "15/03/2026" in prose; numeric date format is ambiguous between US and UK readers.

## ESL industry glossary (USE these native terms)
ESL (English as a Second Language), EAL, EFL, IELTS Academic, TOEFL iBT, Cambridge B2 First, Cambridge C1 Advanced, CELPIP (Canada), pathway program, university pathway, Designated Learning Institution (DLI), SEVIS, I-20 form (USA), F-1 visa, study permit (Canada), homestay, host family, language immersion, ESL bridge, intensive English program, conversation club, accent reduction, placement test, electronic Travel Authorization (eTA, Canada), ESTA (USA).

## AI-tell banlist (NEVER use)
delve, tapestry, landscape (figurative), leverage, multifaceted, comprehensive, furthermore, moreover, crucial, utilize, robust, pivotal, underscore, navigate (figurative), embark, embark on a journey, vibrant, nestled, intricate, realm, in the realm of, in conclusion, it's important to note, it's worth noting, in today's world, in the ever-evolving, dive into, unlock, harness, foster, seamless, holistic, dynamic, transformative, cutting-edge, game-changer.

## Syntactic AI-tells (avoid)
- Em-dash + three comma-separated adjectives ("vibrant, dynamic, and immersive — Vancouver is...").
- "Not only X but also Y" parallel constructions used as rhythm filler.
- "It's not X. It's Y." antithesis with no factual content between.
- Sentence-of-three lists with no variation (e.g. "We offer courses, programs, and pathways.").
- Uniform sentence length (15–22 words throughout) — low burstiness is the #1 AI detector signal.
- Generic openers like "In today's digital age…" / "In an increasingly competitive market…".

## Anti-patterns
- Smarmy/hedging tone ("It is important to note that...", "It's worth considering...").
- Filler transitions ("Furthermore", "Moreover", "However") used to pad rhythm.
- Marketing-speak ("game changer", "level up", "next-gen", "world-class") with no concrete claim.

## Char-limit applicability
Title 60 / Description 130 chars max (Google SERP truncation). Body text has no fixed char limit; word count target from common.md applies.

## Native-voice examples

❌ AI-feeling:
> "In today's globalized world, learning English is more important than ever. Our comprehensive program leverages a multifaceted approach to language acquisition, fostering dynamic skill development."

✅ Human-feeling:
> "Most students who arrive at our Vancouver campus reach a working B2 level in 12 weeks of full-time study. The catch: that timeline assumes 25 hours of class per week plus an honest hour of homework most evenings. Skip the homework, add a month."

## Sources
[Walter Writes 2026](https://walterwrites.ai/most-common-chatgpt-words-to-avoid/) · [Wikipedia Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) · [OliviaCal 17 tells](https://www.oliviacal.com/post/ai-writing-tells) · [HumanizeThisAI 50 words](https://humanizethisai.com/blog/50-words-ai-overuses)
