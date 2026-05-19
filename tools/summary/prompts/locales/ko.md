# 한국어 (ko) — Locale Layer

## Direction + script
LTR, 한글 (Hangul). 한자(漢字)는 거의 사용하지 않으며 외래어는 가타카나가 아닌 한글로 표기.

## Tone + register
공손하고 신뢰감 있는 어조. **"합니다체"** (격식 정중형, 하십시오체)를 본문에 사용. CTA에서만 "해요체"로 살짝 친근하게 전환 가능 ("지금 신청하기"). 어학원 / 교육기관 사이트는 일관된 격식체가 표준.

## Word order
**SOV** (주어-목적어-동사). 영어 SVO를 그대로 번역하지 말 것. "We offer English courses in Vancouver" → "저희는 밴쿠버에서 영어 과정을 제공합니다" (서술어가 끝에).

## Text expansion factor
한국어는 영어보다 **−10 ~ ±0%** (영어보다 짧거나 비슷). 영어 단어 수에 맞추려고 글자 수를 늘리지 말 것. 250–400 영어 단어 ≈ 600–1100 한국어 글자.

## Punctuation conventions
- 마침표 ., 쉼표 , (반각), 따옴표 "..." 또는 ('...'). 일본어처럼 전각 punctuation 「」을 사용하지 않음.
- 긴 줄표 (— 또는 –) 사용 금지 — common.md 보편 규칙.
- 조사 (을/를, 이/가, 은/는, 에/에서)는 명사에 붙여서 표기, 공백 없음.

## Number + currency formatting
- 천 단위 쉼표 : 1,000. 소수점은 마침표 : 3.5.
- 통화 : "월 1,890달러" (한 달 1,890달러) 또는 "월 $1,890" — 달러는 한글 또는 기호 사용.
- 시간 : 24시간 ("14:00") 또는 12시간 ("오후 2시"), 출처에 맞춤.

## Date format
"2026년 3월 15일" — 년 + 월 + 일 순서. "March 15, 2026"이나 "15/03/2026"은 사용하지 않음.

## ESL industry glossary (USE these native terms)
어학연수, 영어 어학연수, 영어 학교, 영어 학원, 캠브리지 영어, 캠브리지 자격증, 공인영어시험, 아이엘츠 (IELTS), 토플 (TOEFL), 셀핍 (CELPIP), 학생비자, F-1 비자, 캐나다 학생비자(스터디퍼밋), 홈스테이, 호스트패밀리, 어학원 등록, 레벨 테스트, 비즈니스 영어, 일반 영어, 집중 코스, 어학연수 비용, 대학 진학 프로그램, 패스웨이 프로그램.

## AI-tell banlist (NEVER use)
다양한 (남용), 살펴보겠습니다, ~에 대해 알아보자, 매우 (남용), 굉장히 (남용), 정말로 (남용), 실제로 (filler), 따라서 (filler), 그러므로 (filler), 또한 (filler), 게다가 (filler), 핵심을 찔렀어, 당사는, 저희는 (과도한 자기지칭), ~드립니다 (남용), 결론적으로, 종합적으로, 다채로운, 혁신적인 (filler), 최첨단의, 끊임없이 진화하는, 빠르게 변화하는 세상에서.

## Syntactic AI-tells (avoid)
- `-게/-이/-히` 부사 남용 ("효과적으로 효율적으로 체계적으로...").
- 기계적인 연결어 ("그리고", "하지만", "그래서") 매 문장마다.
- 두괄식 (영어식 topic-first) 어색하게 한국어에 강요.
- 모든 문장이 `-습니다` 어미로 균일 (어조 변화 없음).
- "~에 대해 X해 보겠습니다" 마무리 패턴 반복.
- 영어 어순 그대로 직역.

## Anti-patterns
- 영어 직역 ("우리는 X를 제공합니다" 대신 "X를 제공해 드립니다" 자연스러움).
- 한자 남용 (현대 웹은 한자보다 한글 선호).
- 부적절한 외래어 ("스쿨" → "학교", "코스" → "과정" 또는 "프로그램").
- 영어식 구두점 밀도 (한국어는 영어보다 쉼표/마침표 적음).

## Char-limit applicability
**비라틴 문자 — 글자 수 제한 적용 안 됨.** Google은 비라틴 스크립트는 픽셀 너비로 측정. 영어 60/130 char 제한은 한국어에 해당하지 않음.

## Geography
"밴쿠버, 브리티시컬럼비아주" 첫 언급 시; 이후 "밴쿠버"만. "캘리포니아" 그대로 사용. "샌디에이고", "로스앤젤레스".

## Native-voice examples

❌ AI 스타일:
> "끊임없이 진화하는 세상에서 영어 학습은 매우 중요합니다. 저희의 다양한 프로그램은 혁신적이고 다채로운 학습 경험을 제공합니다."

✅ 자연스러운 한국어:
> "대부분의 학생은 밴쿠버 캠퍼스에서 12주 풀타임 학습으로 B2 수준에 도달합니다. 단, 주당 25시간 수업과 매일 저녁 1시간의 솔직한 자습이 전제입니다. 자습을 생략하면 한 달이 더 걸립니다."

## Sources
[Rebrandb ChatGPT 100 표현](https://www.rebrandb.com/special/ai-vs-%EC%9D%B8%EA%B0%84%EC%9D%98-%EA%B8%80%EC%93%B0%EA%B8%B0-chatgpt%EC%9D%98-%EA%B0%80%EC%9E%A5-%ED%9D%94%ED%95%9C-100%EA%B0%80%EC%A7%80-%ED%91%9C%ED%98%84) · [Namuwiki ChatGPT 사용법](https://namu.wiki/w/ChatGPT/%EC%82%AC%EC%9A%A9%EB%B2%95) · [Studydestiny 미국 어학연수](https://www.studydestiny.co.kr/america/school-list.html)

(Coverage caveat: Korean AI-tell research is moderate compared to English/European sources. Banlist may be expanded as native-language detector sources accumulate post-2026.)
