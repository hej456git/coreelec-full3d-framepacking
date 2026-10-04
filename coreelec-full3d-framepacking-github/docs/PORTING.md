# Porting to a newer CoreELEC 22 nightly

The release installer is intentionally pinned to combinations that have actually been tested on hardware. Do not replace the pinned SHAs merely because a newer nightly exists.

## 1. Use a separate checkout

Keep the last known-good CoreELEC tree untouched. Clone/update `coreelec-22` into a new directory.

## 2. Record the new package versions

```bash
./scripts/probe-coreelec-tree.sh /path/to/new/CoreELEC
```

If Kodi or common_drivers changed, treat the nightly as untested even if CoreELEC itself only moved a few commits.

## 3. Make a port branch

Create a branch such as `port/coreelec-YYYYMMDD`. Update the installer's expected SHAs only on that branch.

## 4. Check the semantic patches before a full image build

Install the bundle into the new tree, clean/unpack Kodi and common_drivers, and confirm that both post-patch helpers complete without an anchor or structure error. Then compile the patched packages/image.

The helpers are deliberately semantic rather than line-number diffs, but an upstream refactor can still invalidate assumptions. A successful text transformation is not enough: compilation and the hardware test matrix are required.

## 5. Hardware validation

Run `docs/TESTING.md`. Only after all core tests pass should the new CoreELEC/Kodi/common_drivers combination be added to `compatibility/known-good.tsv` and tagged/released.

## Suggested maintenance cadence

Do not chase every nightly date. Re-test when one of these changes:

- Kodi package SHA
- common_drivers package SHA
- relevant Amlogic video/VPP/HDMI code
- a CoreELEC release milestone you actually want to run
