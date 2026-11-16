# #84 The scratch page draws a stock glTF export of one loc and the 16 square [CLOSED]
- URL: https://github.com/julian-perge/blender-addon-rs317-667mqo-makeup/issues/84
- Labels: ready-for-agent
- Assignee: @julian-perge
- Parent: #82 Export a region and a player with a clip to glTF
- Spec: spec/82-gltf-export-findings.md (from issue body)
- Open blockers: none
- Pull requests: #97 MERGED
- Sub-issues: none

## Body

## Parent

#82

## Spec

`spec/82-gltf-export-findings.md` (Method; Findings table, rows 2 and 3; Success criteria 3)

## What to build

Start the note `docs/research/82-gltf-export.md` and the scratch setup that every later task reuses. Nothing in scratch is committed. The scratch folder is `~/tmp/2026-11-15-82-gltf-export`, and the note calls it `<scratch folder>`.

- **Scratch page.** A bare three.js page with a local copy of the latest stable three.js and its glTF and Draco loaders, with no CDN. `?t=<seconds>` freezes the clip at that time and `?view=<name>` selects a camera. It draws no shadow, and it reports `renderer.info.render.calls` and the frame rate.
- **Screenshots.** A headless browser on the real GPU (Playwright with Chrome, or the same in another tool) takes the page screenshots. Record the WebGL renderer string. Stop and report if it is a software renderer.
- **Stock export.** Import region `48_50` of snapshot 430. Export one loc with a textured face first, then the terrain of the 16 square centred on about tile 3080, 3250, both with Blender's stock glTF exporter. Read the glTF JSON after each export.
- **Row 2.** Read the sampler of a texture that has Closest interpolation.
- **Row 3.** Read how the terrain's Emission material exports, load it on the page, and compare a screenshot with an unlit Blender render at the same camera. Read both pictures.
- **Environment.** The note names the Blender version, every exporter setting that is not the default, the three.js release, the machine's GPU and the browser. It records the scratch commands with placeholders for local paths.
- The note has the findings table with all 14 rows and the size table, with the rows of later tasks left empty.

The commit holds the note and the spec file, which is not committed yet.

## Acceptance criteria

- [ ] `docs/research/82-gltf-export.md` has rows 2 and 3 filled: survives or not, the glTF JSON extract or the pair of pictures in words, and each cause marked as evidence o
[cut: 576 more characters, run with --full]

## Decisions (2)

### #82 @julian-perge, 2026-11-16

### Decisions from the plan of #82

- The player for #87 wears Verac's helm, Fire cape, Verac's brassard, Verac's plateskirt, Barrows gloves, Climbing boots and Verac's flail. Reason: it is the owner's outfit, and the page shows the owner's player.

### #84 @julian-perge, 2026-11-16

Decisions from the review of #97, for the later tasks of #82:

- The `test` camera at (1024, 3800, 2172) with a 40 degree field of view stays the test camera. #86 may replace it only if it does not hold the 32 square, and then records the new one in the note.
- The stock export stays GLB with `use_selection=True`, and every other exporter setting at its default.
- The scratch page keeps its ambient and directional light on by default, since row 4 needs them. `lights=0` leaves them out.

The 60 fps cap of headless Chrome is still a guess until #86 checks it.

## Comments (none)
