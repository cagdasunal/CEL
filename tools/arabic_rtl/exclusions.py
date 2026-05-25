"""Selector substrings whose flipped RTL override rules must be DROPPED.

rtlcss flips everything mechanically. Some flips are semantically wrong and can't
be detected automatically — logos/brandmarks, media-play controls (play points
right regardless of reading direction), intentional `direction` scroll hacks,
carousel internals, etc. When live `/ar/` browser validation finds a rule that
flipped incorrectly, add a substring of its selector here and it will be excluded
from the generated override.

Populate from real validation findings, not speculation.

Findings:
- `.w-dropdown-toggle`: Webflow's built-in dropdown toggle ships `padding-right:40px`
  to reserve room for its DEFAULT arrow icon. This site uses a custom `.dropdown-chevron`
  (a flex child), so that padding is vestigial. rtlcss flips it to `padding-left:40px`,
  which renders as ~40px dead space on the LEFT of every RTL nav dropdown (uneven menu
  spacing). Excluding drops the bad padding flip; the harmless `text-align:right` flip
  for dropdown elements is restored explicitly in arabic_static.css.
- `.navbar_dropdown-list`: the open mega-menu panel's base position is `right:0`, which is
  already correct for RTL. rtlcss flips it to `left:0;right:auto`, opening the panel on the
  wrong side. Excluding drops the position flip so the base `right:0` right-aligns the panel
  (Webflow's dropdown JS handles the rest).
- `.navbar_dropdown-link`: base is `text-align:right` (correct for RTL). rtlcss flips it to
  `text-align:left` (wrong) and mirrors the padding. But this link is `display:flex`, so
  `text-align` is a no-op on item position anyway — `justify-content` controls it. Excluding
  drops the whole bad flip; base `text-align:right` applies and `justify-content:flex-start`
  (arabic_static.css) right-aligns the flex item.
- `.card-slider_arrow.is-prev`: source rotates the prev arrow `180deg` (prev/next share one
  SVG). rtlcss flips that to `-180deg` (a visual no-op). On RTL the prev arrow should be
  un-rotated, so the override is dropped and arabic_static.css sets `rotate(0deg)` — which
  beats both the base `rotate(180deg)` and the `scaleX(-1)` arrow-mirror group on specificity.
"""

EXCLUDE_SUBSTRINGS: list[str] = [".w-dropdown-toggle", ".navbar_dropdown-list", ".navbar_dropdown-link", ".card-slider_arrow.is-prev"]
