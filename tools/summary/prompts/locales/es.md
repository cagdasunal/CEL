# Español (es) — Locale Layer

## Direction + script
LTR, escritura latina con tildes (á, é, í, ó, ú), diéresis (ü) y la ñ. Signos invertidos (¿¡) obligatorios.

## Tone + register
Profesional, claro, **tratamiento de "usted"** en contexto institucional (más cercano en América Latina, más formal en España, pero "usted" funciona en ambos mercados para una escuela). Voz activa. Match el dialecto del source: si el sitio usa "vosotros" / "vuestro" (España) o "ustedes" / "su" (América Latina), mantén la elección.

## Text expansion factor
Español : **+15 a +25%** más largo que inglés.

## Punctuation conventions
- **Signos invertidos obligatorios** : ¿Cómo aprender inglés? ¡Excelente!
- Comillas tipográficas : «...» o "...", evitar ' '.
- Coma decimal en España, punto en parte de América Latina — match source.
- Sin guiones em (— o –) — regla universal (common.md).
- Raya de diálogo (—) NO se usa en este tipo de contenido.

## Number + currency formatting
- Miles : punto (1.000) en España, coma (1,000) en México y partes de LATAM. Match source.
- Decimal : opuesto al de miles. España → "1.000,50", México → "1,000.50".
- Moneda : `$1.890` (México) o `1.890 €` (España). Cuando se trata de USD/CAD, agregar la sigla : "1.890 USD" o "$1.890 dólares".
- Hora : 24h ("14:00 h" en España) o 12h con "a. m./p. m." (México) — match source.

## Date format
DD/MM/AAAA (15/03/2026) en ambos dialectos. Forma larga : "15 de marzo de 2026" (mes en minúscula). Nunca "March 15, 2026".

## ESL industry glossary (USE these native terms)
Curso de inglés en el extranjero, escuela de idiomas, inmersión lingüística, familia anfitriona, alojamiento en familia, intercambio estudiantil, programa académico, certificación Cambridge, preparación IELTS, preparación TOEFL, examen oficial, visa de estudiante, permiso de estudios (Canadá), ESTA, inglés general, inglés intensivo, inglés de negocios, inglés académico, prueba de nivel, prácticas en el extranjero, ETA Canadá, año académico, programa de pasarela universitaria.

## AI-tell banlist (NEVER use)
es importante destacar, es importante mencionar, en el mundo de, en la actualidad, en el mundo actual, en resumen, cabe destacar, cabe mencionar, sin duda, indudablemente, fundamental, crucial, esencial (en filler), integral, fascinante, sumergirse en, adentrarse en, explorar (figurado), navegar (figurado), robusto, transformador, dinámico, sin fisuras, vanguardista, en la era de.

## Syntactic AI-tells (avoid)
- "no solo X, sino también Y" como relleno rítmico.
- Estructura tripartita ("primero X, segundo Y, tercero Z") sin necesidad lógica.
- Raya larga (—) mucho más frecuente que en español natural.
- Conectores excesivos ("además / por consiguiente / asimismo / por lo tanto") en cada párrafo.
- Ausencia de regionalismos (España vs México vs Argentina) que normaliza el texto.
- Longitud de oración uniforme — el español humano varía mucho.

## Anti-patterns
- Anglicismos innecesarios ("el feedback" → "los comentarios"; "el plan B" puede quedarse).
- Tildes olvidadas (sobre todo en mayúsculas : "ÉXITO" no "EXITO").
- Concordancia de género incorrecta (artefacto típico de traducción automática).
- "Actualmente" usado como "actually" (calco) — significa "en este momento".
- Voseo argentino mezclado con tuteo (mantén una sola variedad por texto).

## Char-limit applicability
Título 60 / Descripción 130 caracteres latinos. Es expansiones de 20% reduce margen — verifica.

## Geography
"Vancouver, Columbia Británica" en la primera mención; "California" sin traducir.

## Native-voice examples

❌ Estilo IA :
> "En el mundo actual, aprender inglés es fundamental. Cabe destacar que nuestro programa integral ofrece una experiencia dinámica y transformadora, sin duda esencial para el éxito."

✅ Estilo humano :
> "La mayoría de nuestros estudiantes alcanza un nivel B2 sólido en doce semanas en el campus de Vancouver. Con una condición : 25 horas de clase por semana y una hora honesta de tarea cada noche. Sin tarea, calcula un mes más."

## Sources
[Scribbr AI detector ES](https://www.scribbr.com/ai-detector/) · [Hastewire detectar ChatGPT](https://hastewire.com/es/blog/como-detectar-si-un-texto-fue-hecho-con-chatgpt-guia-practica) · [Xataka 9 detectores](https://www.xataka.com/basics/detector-chatgpt-9-servicios-apps-para-saber-texto-ha-sido-generado-ia-openai) · [Mundo Joven Canadá](https://mundojoven.com/estudios/idiomas/cursos-de-ingles-en-canada)
