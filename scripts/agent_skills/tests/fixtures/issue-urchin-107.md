# #107 UI overhaul: faithful screens on native Godot containers [OPEN]
- URL: https://github.com/julian-perge/urchin/issues/107
- Labels: ready-for-human
- Assignee: none
- Parent: #1 Overhaul the port's structure while keeping behavior faithful to the original
- Spec: none (candidates: spec/107-abilities.md, spec/107-capability-map.md, spec/107-hub.md, spec/107-inventory.md, spec/107-store.md, spec/107-title-slots.md, spec/107-ui-foundation.md, spec/107-victory.md, spec/107-window-shell.md)
- Open blockers: none
- Pull requests: none
- Sub-issues: 29 open of 62

| # | State | Assignee | Open blockers | Title |
| --- | --- | --- | --- | --- |
| #204 | OPEN | none | 0 | Re-pad the four cutscene clips to 800x575 |
| #209 | OPEN | none | 0 | Generalize the compare tool from the victory prototype |
| #215 | OPEN | none | 1 | Open the game on the title and add the shared menu pieces |
| #216 | OPEN | none | 1 | Rebuild the choice Screen and leave out PvP Arena |
| #217 | OPEN | none | 2 | Rebuild the slot list as the original's four rows |
| #218 | OPEN | none | 0 | Extract the hotbar icons, glow colors and hover ranges |
| #219 | OPEN | none | 2 | Rebuild the bottom bar and the hotbar at the SWF rects |
| #220 | OPEN | none | 1 | Read hotbar and orb tooltips from strings and add set_inert |
| #221 | OPEN | none | 1 | Rebuild the zone progress at the SWF rects |
| #222 | OPEN | none | 2 | Rebuild the seven zone scenes and add set_art_visible |
[cut: 4 more rows, run with --full]

## Body

## Destination

A UI spec at `spec/107-ui-overhaul.md` that gives every screen and window a decided target layout and names the SWF pieces it's built from, plus ready-for-agent issues to build it. The map is done once nothing is left to decide, and the building happens in those issues.

## Notes

- **Look:** faithful to the original by default, with an ADR for any departure a player could notice, the same rule [Overhaul the port's structure while keeping behavior faithful to the original](https://github.com/julian-perge/urchin/issues/1) set for behavior.
- **Structure:** Godot scenes on native containers (HBox, VBox, Margin, Panel and the shared project theme) instead of TextureRects with hardcoded sizes and offsets. The original's UI nests panels and backgrounds, and containers should handle that alignment. godotengine/godot-demo-projects is the reference for native nodes.
- **History:** the UI so far was built to be good enough to play while extracting the art was the hard part. The very first version placed images at hardcoded pixel values.
- **Terms:** a **Screen** is a full-window state the player navigates to (Title, Hub, Battle, Game over, Ending). A **Window** is a panel opened over the hub (Inventory, Store, Abilities, Victory). The **HUD** is the battle screen's status elements over the hall (unit overlays, member bars, top status bar, speech box).
- **Every session:** follow `docs/agents/art-extraction.md` and `CODING_STANDARDS.md`, especially "Extract the parts, rebuild the arrangement", with `spec/old/2026-08-23-battle-bottom-bar-and-stance-rows.md` as the worked example. Read `docs/agents/workflow.md` first. Anything posted to the tracker uses julian-voice.
- **Known work this map covers,** each issue keeping its own labels:
  - [Add the original's title screen, logo and slot list layout to the main menu](https://github.com/julian-perge/urchin/issues/91)
  - [Battle screen is missing the original's top status bar and hall framing, and the zone 4 boss d
[cut: 10406 more characters, run with --full]

## Comments (2 of 2, newest last)

### @julian-perge, 2026-11-09

Found while doing the Victory side by side for #127, in #139. The gold row's big euro sign isn't in the 22 px field, `dumbEuro` only holds the number, so the inventory panel's single "€ 7" label won't match the capture until that gets rebuilt.

Eight text sizes on Victory and the inventory panel were also 1 to 2 px off from their edit texts' `fontHeight`, which #139 fixes. I only checked those two, so the other Screens and Windows are worth pulling their sizes from the SWF when they get rebuilt.

### @julian-perge, 2026-11-11

Specs for Title and slots, Hub, Inventory, Store, Abilities and Victory are written, in `a9a4adf5` on `claude/agent-skills-spec-107-c525e4` (not pushed yet).

- `spec/107-capability-map.md`
- `spec/107-ui-foundation.md`
- `spec/107-window-shell.md`
- `spec/107-title-slots.md`
- `spec/107-hub.md`
- `spec/107-inventory.md`
- `spec/107-store.md`
- `spec/107-abilities.md`
- `spec/107-victory.md`

The map adds a ui-foundation module, since the viewport, `FloatBox`, the rect test, the compare tool and a strings extractor were decided in closed tickets but had no spec or issue. Only #161 existed.

Th
[cut: 210 more characters, run with --full]
