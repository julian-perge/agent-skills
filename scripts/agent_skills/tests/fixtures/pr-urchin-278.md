# PR #278 Fix the comments, docs and small test gaps from the #107 re-reviews [OPEN]
- URL: https://github.com/julian-perge/urchin/pull/278
- Base: main
- Head: fix/273-comment-doc-gaps
- Draft: no
- Checks: none
- Reviews: none
- Task: #273 Fix the comments, docs and small test gaps from the #107 re-reviews (from closing reference)
- Spec: spec/107-ui-foundation.md (from issue body)
- Standard: CODING_STANDARDS.md

## Files (12, +72 -40)

| File | + | - |
| --- | --- | --- |
| DECODED_ALGORITHMS.md | 1 | 1 |
| dev/tests/test_screen_rects.py | 27 | 6 |
| dev/urchin_dev/convert/menu_math.py | 2 | 1 |
| dev/urchin_dev/swf/extract/screen_rects.py | 16 | 7 |
| docs/adr/0007-keep-the-abilities-window-departures.md | 1 | 1 |
| scripts/battle/battle_scene.gd | 1 | 1 |
| scripts/ui/menu/abilities_window.gd | 4 | 2 |
| scripts/ui/menu/victory_exp_row.gd | 3 | 2 |
| test/integration/test_battle_scene.gd | 5 | 6 |
| test/post_run.gd | 11 | 8 |
| test/unit/test_panel_recipe.gd | 1 | 4 |
| test/unit/test_screen_rects.gd | 0 | 1 |

## Commits (3 of 3, newest last)

- docs: correct the false and incomplete comments the re-reviews flagge…
- refactor: button_record takes the button id (#273)
- fix: the small code and test gaps the re-reviews flagged (#273)

## Body

Closes #273

Built by the large worker (MiMo-V2.6-Pro) as run 2 of 6 in #274, after two timeouts and one rework note each.

- The `leveled` comment in `victory_exp_row.gd` now says nothing reads it today and that `battle_scene.gd` uses `levels_gained`. No open task changes that, so it names none.
- `button_record` takes the button id and raises a `ValueError` naming the button and the character when an up-state record is not a shape.
- `test_panel_recipe.gd` no longer types the shadow values. `test_screen_rects.gd` already compares the material with the SWF.
- `func run()` in `post_run.gd` is now `-> void`. `GutHookScript.run()` has no return type, so "match" could also mean untyped.

Verification: `just pytest` 420 passed, `just gut` 784 of 784. With the `word_wrap` arm removed from `text_record`, the new pytest case fails.

Check out: gh pr checkout 278
Review: /agent-skills:review issue #273, PR #278, spec spec/107-ui-foundation.md, standard CODING_STANDARDS.md
