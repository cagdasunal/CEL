# Português (pt) — Locale Layer

## Direction + script
LTR, escrita latina com acentos agudo (á, é, í, ó, ú), circunflexo (â, ê, ô), grave (à), til (ã, õ) e cedilha (ç).

## Tone + register
**Português brasileiro (pt-BR) por padrão** — o público principal da CEL é Brasil. Tom caloroso, amigável, profissional. **Use "você"** (BR) ou "o(a) senhor(a)" em contextos mais formais. Nunca "tu" para o público brasileiro institucional. Se o source for claramente português europeu (pt-PT), mantenha pt-PT.

## Text expansion factor
Português : **+15 a +20%** mais longo que o inglês.

## Punctuation conventions
- Aspas duplas "..." ou aspas tipográficas "..." — use as do source.
- Sem travessões longos (— ou –) — regra universal (common.md).
- Vírgulas antes de "mas", "porém", "embora" são obrigatórias.

## Number + currency formatting
- Milhares : ponto (1.000), decimal : vírgula (3,5).
- Moeda : `US$ 1.890 por mês` (pt-BR) — observe o `US$` sem espaço. Para EUR : `1.890 €`.
- Hora : 24h ("14h30" ou "14:30"), nunca "2:30 PM".

## Date format
DD/MM/AAAA (15/03/2026) ou forma extensa : "15 de março de 2026" (mês em minúsculo). Nunca "March 15, 2026".

## ESL industry glossary (USE these native terms)
Intercâmbio, curso de inglês no exterior, escola de idiomas, imersão linguística, família anfitriã, host family, certificação Cambridge, preparação IELTS, preparação TOEFL, vistos de estudante, study permit (Canadá), Co-op (programa trabalho + estudo, Canadá), ETA Canadá, ESTA, inglês geral, inglês intensivo, inglês para negócios, Business English, teste de nivelamento, estágio no exterior, programa de pasarela universitária, programa acadêmico preparatório.

## AI-tell banlist (NEVER use)
é importante destacar, é importante mencionar, vale ressaltar, no mundo de, no mundo atual, na era digital, além disso (filler), ademais, portanto (filler), em suma, em conclusão, mergulhar em (figurado), explorar (figurado), navegar (figurado), fascinante, crucial, essencial (filler), fundamental, robusto, dinâmico, abrangente, transformador, de ponta, multifacetado.

## Syntactic AI-tells (avoid)
- "não apenas X, mas também Y" como enchimento rítmico.
- Repetições redundantes ("ótimo... ótimo... ótimo").
- Estrutura forçada de três tópicos.
- Travessão longo (—) frequente — anglo-saxão, raro em português natural.
- Ausência de gírias brasileiras / portuguesas regionais — normalização típica de tradução automática.
- Tom plano sem variação coloquial/formal natural.

## Anti-patterns
- Anglicismos evitáveis ("o feedback" → "o retorno"; "o expertise" → "a especialização").
- Acentos faltando ("voce" → "você"; "ingles" → "inglês").
- Mistura inconsistente de "você" (BR) e "tu" (PT informal regional).
- Estrutura sintática anglo-saxã (ordem SVO rígida sem variação).
- "Atualmente" como "actually" (calco) — significa "neste momento".

## Char-limit applicability
Título 60 / Descrição 130 caracteres latinos. PT expande 15–20% — verifique.

## Geography
"Vancouver, na Colúmbia Britânica" na primeira menção; "Califórnia" para California.

## Native-voice examples

❌ Estilo IA :
> "No mundo atual, aprender inglês é fundamental. Nosso programa abrangente oferece uma experiência transformadora, dinâmica e multifacetada, essencial para o sucesso."

✅ Estilo humano :
> "A maioria dos nossos alunos atinge um B2 sólido em doze semanas no campus de Vancouver. Com uma condição: 25 horas de aula por semana e uma hora honesta de tarefa toda noite. Sem tarefa, conta mais um mês."

## Sources
[Hastewire detector PT](https://hastewire.com/pt/blog/detector-chatgpt-como-identificar-textos-gerados-por-ia-em-2026) · [Hastewire texto IA português](https://hastewire.com/pt/blog/texto-feito-por-ia-em-portugues-como-detectar-facilmente) · [EF Brasil](https://www.ef.com.br/pg/intercambio/ingles/) · [CI Intercâmbio](https://www.ci.com.br/pt-br/intercambio-aprender-idiomas/curso-de-idiomas)
