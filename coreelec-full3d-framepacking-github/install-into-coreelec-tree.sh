#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$PWD}"
SELF="$(cd "$(dirname "$0")" && pwd)"

KODI_PKG="$ROOT/projects/Amlogic-ce/packages/mediacenter/kodi"
KODI_MK="$KODI_PKG/package.mk"
KODI_DIR="$KODI_PKG/patches"
KODI_HELPER="$KODI_PKG/full3d-kodi-postpatch.py"
DRV_PKG="$ROOT/projects/Amlogic-ce/packages/linux-drivers/amlogic/common_drivers"
DRV_MK="$DRV_PKG/package.mk"
DRV_DIR="$DRV_PKG/patches"
DRV_HELPER="$DRV_PKG/full3d-common-drivers-postpatch.py"

EXPECTED_KODI="0661a5d74edc384f443b17c9467c1f5efa9ec337"
EXPECTED_DRV="4dbe1c27ae176fde4c1cbef7506618fd7f62b976"
BASELINE="CoreELEC 22 Amlogic-NO nightly 20260929 (CoreELEC f30e977a4b)"

if [[ ! -f "$ROOT/Makefile" || ! -f "$KODI_MK" || ! -f "$DRV_MK" ]]; then
  echo "ERROR: '$ROOT' does not look like the expected CoreELEC source tree." >&2
  echo "Usage: $0 /path/to/CoreELEC" >&2
  exit 1
fi
if ! grep -q "PKG_VERSION=\"$EXPECTED_KODI\"" "$KODI_MK"; then
  echo "ERROR: Kodi package version does not match $BASELINE." >&2; exit 2
fi
if ! grep -q "PKG_VERSION=\"$EXPECTED_DRV\"" "$DRV_MK"; then
  echo "ERROR: common_drivers package version does not match $BASELINE." >&2; exit 2
fi

mkdir -p "$KODI_DIR" "$DRV_DIR"

# Remove old fragile late unified patches from v0.2.x.
rm -f "$KODI_DIR/999-full-sbs-ou-to-hdmi-framepacking.patch"
rm -f "$DRV_DIR/999-full-sbs-ou-to-hdmi-framepacking.patch"

cp "$SELF/full3d-kodi-postpatch.py" "$KODI_HELPER"
cp "$SELF/full3d-common-drivers-postpatch.py" "$DRV_HELPER"
chmod +x "$KODI_HELPER" "$DRV_HELPER"

# At this pinned baseline neither package has an upstream post_patch() hook.
python3 - "$KODI_MK" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]); s = p.read_text(); marker = "# FULL3D_FP_KODI_POSTPATCH_V024"
if marker not in s:
    s += '''\n\n# FULL3D_FP_KODI_POSTPATCH_V024\npost_patch() {\n  /usr/bin/python3 "${ROOT}/projects/Amlogic-ce/packages/mediacenter/kodi/full3d-kodi-postpatch.py" "${PKG_BUILD}"\n}\n'''
    p.write_text(s)
PY

python3 - "$DRV_MK" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]); s = p.read_text(); marker = "# FULL3D_FP_POSTPATCH_V022"
if marker not in s:
    s += '''\n\n# FULL3D_FP_POSTPATCH_V022\npost_patch() {\n  /usr/bin/python3 "${ROOT}/projects/Amlogic-ce/packages/linux-drivers/amlogic/common_drivers/full3d-common-drivers-postpatch.py" "${PKG_BUILD}"\n}\n'''
    p.write_text(s)
PY

echo "Baseline OK: $BASELINE"
echo "Installed Kodi post-patch helper: $KODI_HELPER"
echo "Installed driver post-patch helper: $DRV_HELPER"
echo "Full3D bundle: v0.3.0-rc1 (proven v0.2.30 rendering path; diagnostics removed)"
