"""Static mirror of the geotargetly CONFIG table inside cel-offers.js.

The dashboard's Settings view renders this read-only. Tests verify
this file stays in lockstep with the embedded JS CONFIG.
"""
from __future__ import annotations

# Mirror of CONFIG block in tools/cel-offers-js/cel-offers.js.
# Each value is an ISO 3166 alpha-2 comma-separated string, copied verbatim.
# Drift detection: tools/offers/tests/test_regions.py reads cel-offers.js,
# parses the CONFIG block, and asserts equality.
REGIONS: dict[str, dict[str, str]] = {
    "offers": {
        "countries": "ES,IT,NL,SE,FI,AT,BE,PT,AD,DK,DE,GR,IS,LI,LU,NO,SM,TR,AZ,BY,GE,KZ,KG,AM,MD,RU,TJ,UA,AL,BA,BG,HR,CY,CZ,EE,LV,LT,ME,MK,PL,RO,RS,SK,SI,TW,CN,KR,VN,TH,BD,KH,ID,MY,MN,BH,EG,IR,IQ,AE,JO,KW,SA,LB,OM,QA,YE,DZ,AR,BZ,BO,CL,CO,CR,CU,DO,EC,SV,GT,HT,HN,JM,MX,NI,PA,PY,PE,UY,VE,BR,JP",
        "action": "show",
    },
    "sandiego": {
        "countries": "AE,AL,AM,AR,AZ,BA,BD,BE,BG,BH,BO,BR,BZ,CL,CN,CO,CR,CU,CY,CZ,DO,DZ,EC,EE,EG,ES,FR,GE,GT,HN,HR,HT,ID,IQ,IR,IT,JM,JO,JP,KG,KH,KR,KW,KZ,LB,LT,LV,MD,ME,MK,MN,MX,MY,NI,OM,PA,PE,PL,PY,QA,RO,RS,RU,SA,SI,SK,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
        "action": "show",
    },
    "losangeles": {
        "countries": "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KU,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
        "action": "show",
    },
    "vancouver": {
        "countries": "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
        "action": "show",
    },
    "usa": {
        "countries": "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CL,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,FR,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KU,KW,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
        "action": "show",
    },
    "canada": {
        "countries": "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
        "action": "show",
    },
}
