# PR #66 Place the level 0 scenery of a region as objects [MERGED]
- URL: https://github.com/julian-perge/blender-addon-rs317-667mqo-makeup/pull/66
- Base: main
- Head: feat/49-region-scenery
- Draft: no
- Checks: none
- Reviews: none
- Task: #49 The region import places the level 0 scenery as objects (from closing reference)
- Spec: spec/35-draynor-region-import.md (from issue body)
- Standard: CODING_STANDARDS.md

## Files (7, +644 -32)

| File | + | - |
| --- | --- | --- |
| src/rsps_toolkit/blender/region_import.py | 67 | 12 |
| src/rsps_toolkit/blender/region_scenery.py | 123 | 0 |
| src/rsps_toolkit/formats/loc_definition.py | 25 | 0 |
| src/rsps_toolkit/formats/region_placement.py | 6 | 3 |
| tests/blender/test_region_import.py | 397 | 10 |
| tests/js5_builder.py | 6 | 5 |
| tests/unit/test_loc_definition.py | 20 | 2 |

## Commits (3 of 3, newest last)

- feat: place the level 0 scenery of a region as objects (#49)
- Merge branch 'main' of github.com:julian-perge/blender-addon-rs317-66…
- test: check the heights of an own mesh and the skins of a shared mesh…

## Body

Closes #49

Spec: `spec/35-draynor-region-import.md` (part 6).

The import of `48_50` now fills `Scenery 48_50` with 1,894 objects for its 1,874 level 0 placements. 185 meshes are shared and 1,154 are own meshes. No placement shows nothing.

- Added `blender/region_scenery.py`. Placements with the same models, recolours and retextures share one mesh, and the object holds the position, turn and scale (the mirror is a scale of -1 on y). A placement that `own_vertices` bends gets its own mesh from its moved vertices, and its object holds only the position. The meshes come from `model_to_object`, with the textures from the decoded images.
- Updated `blender/region_import.py`. It reads the landscape, the locs and the models before it makes anything, places the scenery and returns the counts that the report of #50 needs.
- Added `read_locs` to `formats/loc_definition.py`. It also reads the locs that the impostors name.
- The fixture cache gets the loc group and an empty keys folder. The tests that run without the real cache then import no scenery, because the fixtures hold no loc models.

The owner's choices are in the [Decisions comment on #49](https://github.com/julian-perge/blender-addon-rs317-667mqo-makeup/issues/49#issuecomment-6888052393).

Guesses and choices of my own:
- A loc or a model that the cache lacks stops the import with a message, the same as a missing texture (#47).
- Each mesh gets its own materials, so `48_50` makes 3,172 materials. Sharing them is left for later.
- Several models of one loc are joined with `appearance.merge`, which gives an old-format model. A recolour of 127 on such a model would be refused with the old-format message. No loc of `48_50` does this.
- Two placements of the same loc on one tile get the same object name, and Blender numbers the second.
- The scenery tests need the real cache. The fixtures hold no loc models.

Run time and memory of the import of `48_50` (spec, guess 5): 5.6 seconds, and the peak memory of Blender went f
[cut: 331 more characters, run with --full]

Check out: gh pr checkout 66
Review: /agent-skills:review issue #49, PR #66, spec spec/35-draynor-region-import.md, standard CODING_STANDARDS.md
