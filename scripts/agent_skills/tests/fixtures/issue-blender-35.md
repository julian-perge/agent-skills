# #35 Import a map chunk (terrain and scenery) into Blender [OPEN]
- URL: https://github.com/julian-perge/blender-addon-rs317-667mqo-makeup/issues/35
- Labels: enhancement, needs-triage
- Assignee: none
- Parent: none
- Spec: spec/35-draynor-region-import.md (guess)
- Open blockers: none
- Pull requests: none
- Sub-issues: 2 open of 17

| # | State | Assignee | Open blockers | Title |
| --- | --- | --- | --- | --- |
| #51 | OPEN | none | 0 | Compare the viewport render of region 48_50 with the live-client picture |
| #67 | OPEN | none | 0 | The scenery meshes of a region import share their materials |
| #36 | CLOSED | @julian-perge | 0 | The placements of region 48_50 are read from the encrypted landscape |
| #37 | CLOSED | @julian-perge | 0 | The terrain of region 48_50 and its 8 neighbours is read from the cache |
| #38 | CLOSED | @julian-perge | 0 | The underlay, overlay and loc definitions of region 48_50 are decoded |
| #39 | CLOSED | @julian-perge | 0 | Cache textures are decoded and match RuneLite pixel for pixel |
| #40 | CLOSED | @julian-perge | 0 | A terrain tile gets the triangles of its shape |
| #41 | CLOSED | @julian-perge | 0 | Each terrain tile corner gets its blended and lit colour |
| #42 | CLOSED | @julian-perge | 0 | A placement shows the model that the client picks for its loc type |
| #43 | CLOSED | @julian-perge | 0 | Each placement gets the position, height and turn of the client |
[cut: 7 more rows, run with --full]

## Body

As an engineer, I want to import a chunk of the game map (e.g. Draynor Village) into Blender, with its terrain and the scenery on it, so that a player built with the add-on can stand in a real area instead of an empty scene.

Right now the add-on only handles models. `formats/js5.py` says encrypted groups (map landscapes) are not supported, and `docs/osrs-cache-workflow.md` notes that 268 landscapes in snapshot 430 have no exported key.

The first use for this is a 3D scene on my profile page, exported from Blender as glTF. I think the import should land here first, and the export side can be adjusted for the page after.

Not settled yet:

- Which cache archives hold the terrain and the landscape (scenery placement) of a region, and which keys the landscapes need.
- How much to import at once: one region, a rectangle of tiles, or a named area.
- Whether scenery objects (trees, walls, buildings) come in with the terrain, or in a later step.
- How the tile colors, overlays and textures become Blender materials.
- Whether the result needs to export to glTF with the same look.

## Comments (3 of 3, newest last)

### @julian-perge, 2026-11-14

Idea stage result for this issue.

**Goal:** Import region `48_50` (Draynor Village) of snapshot 430 into Blender, with its level 0 terrain and scenery, so that a player built with the add-on can stand in a real place. The glTF export for the profile page is a later issue.

**Settled:**

- Cache: snapshot 430 (revision 149). The add-on already decodes its models, and its landscape keys are in the OpenRS2 download.
- Unit: one region. The cache names the groups `m<x>_<y>` (terrain) and `l<x>_<y>` (scenery) in index 5. `48_50` is tiles x 3072 to 3135 and y 3200 to 3263. Lumbridge is `50_50`.
- L
[cut: 2782 more characters, run with --full]

### @julian-perge, 2026-11-14

Design stage result for this issue. The decisions are in [ADR 0022](https://github.com/julian-perge/blender-addon-rs317-667mqo-makeup/blob/main/docs/adr/0022-the-region-import-checks-each-value-against-a-second-reader.md), and the new terms are in `GLOSSARY.md` (Regions and scenery).

**Settled:**

- Landscape keys come from the `keys/` folder next to the `cache/` folder that the Cache folder preference names. There is no new preference. A missing folder gives an error that names it.
- Textures: the region import decodes them from index 9 and index 8. The texture folder stays for model import.
[cut: 1562 more characters, run with --full]

### @julian-perge, 2026-11-14

Spec for the region import: `spec/35-draynor-region-import.md`. Approved on 2026-11-14. The decisions of the spec stage are in ADR 0023, and the probe counts for region 48_50 are in `docs/research/region-48-50.md`.
