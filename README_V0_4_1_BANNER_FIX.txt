DDR X Song Swap v0.4.1 - banner-format hotfix

Based on the previously tested v0.4 package, with johnboyjr's Here It Goes Again TIM2 alignment fix.

What's fixed:
- Supports ordinary 16-byte and 128-byte-aligned TIM2 picture headers.
- Banner validation checks the appropriate header for each format.
- Here It Goes Again (heit, song index 11) should now allow banner replacement.

Validated offline against all 77 original stock banner entries. 77/77 recognized.
The modified ISO has NOT been boot-tested with this patch. Keep a backup
of your known-working v0.4 package and build from the original ISO.

All other v0.4 behavior is unchanged, including experimental Shock Arrows.
