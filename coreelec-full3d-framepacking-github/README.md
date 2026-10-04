# CoreELEC Full3D Frame Packing

Experimental Full-SBS / Full-TAB to genuine HDMI 1080p frame-packed 3D support for CoreELEC 22 on the Nokia Streaming Box 8010 (Amlogic S905X4).

The project takes one hardware-decoded full-resolution packed frame and uses VD1/VD2 as two cropped readers of the same live decoded surface, then composes them into the 1920x2205 HDMI frame-packing transport raster.

## Current release candidate

`v0.3.0-rc1`

Known-good baseline:

- CoreELEC 22 Amlogic-NO nightly 20260929
- CoreELEC commit `f30e977a4b`
- Kodi `0661a5d74edc384f443b17c9467c1f5efa9ec337`
- common_drivers `4dbe1c27ae176fde4c1cbef7506618fd7f62b976`
- device: Nokia Streaming Box 8010 / S905X4

Validated on hardware: Full-SBS, Full-TAB, genuine MVC transitions, and manual Stop.

## Input/output

- Full-SBS: `3840x1080`, filename marker `.FSBS.`
- Full-TAB/OU: `1920x2160`, filename marker `.FTAB.`
- HDMI output: `1920x2205` = 1080 left + 45 blank + 1080 right

## Install on the tested baseline

```bash
./install-into-coreelec-tree.sh /path/to/CoreELEC
```

Then rebuild Kodi, common_drivers and linux using the normal CoreELEC Amlogic-NO build environment.

The installer intentionally refuses package SHAs that are not in the tested baseline. For newer nightlies, follow `docs/PORTING.md` rather than bypassing the guard blindly.

## Check a CoreELEC tree

```bash
./scripts/probe-coreelec-tree.sh /path/to/CoreELEC
```

This prints the CoreELEC commit and the Kodi/common_drivers package SHAs and tells you whether that package combination is recorded as tested.

## Documentation

- `docs/ARCHITECTURE.md` — proven rendering model and required pieces
- `docs/PORTING.md` — workflow for newer CoreELEC nightlies
- `docs/TESTING.md` — hardware release test matrix
- `CHANGELOG.md` — development history

## Known issue

An intermittent black screen at natural EOF remains unresolved. Manual Stop is distinct and is working in the current RC.

## Upstreaming

The long-term goal should be normal source commits/PRs in the relevant CoreELEC Kodi and Amlogic common_drivers repositories. The semantic post-patch helpers are useful for development and rebasing, but are not the ideal final upstream form.
