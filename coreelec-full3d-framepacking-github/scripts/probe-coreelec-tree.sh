#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$PWD}"
KODI_MK="$ROOT/projects/Amlogic-ce/packages/mediacenter/kodi/package.mk"
DRV_MK="$ROOT/projects/Amlogic-ce/packages/linux-drivers/amlogic/common_drivers/package.mk"
if [[ ! -f "$ROOT/Makefile" || ! -f "$KODI_MK" || ! -f "$DRV_MK" ]]; then
  echo "ERROR: '$ROOT' does not look like a CoreELEC source tree." >&2
  exit 1
fi
get_ver() { sed -n 's/^PKG_VERSION="\([^"]*\)".*/\1/p' "$1" | head -n1; }
CE_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
KODI="$(get_ver "$KODI_MK")"
DRV="$(get_ver "$DRV_MK")"
printf 'CoreELEC commit:      %s\n' "$CE_COMMIT"
printf 'Kodi PKG_VERSION:     %s\n' "$KODI"
printf 'common_drivers:       %s\n' "$DRV"
SELF="$(cd "$(dirname "$0")/.." && pwd)"
KNOWN="$SELF/compatibility/known-good.tsv"
if awk -F '\t' -v k="$KODI" -v d="$DRV" '$1 !~ /^#/ && $4==k && $5==d {found=1} END{exit !found}' "$KNOWN"; then
  echo 'Compatibility status: TESTED combination in compatibility/known-good.tsv'
else
  echo 'Compatibility status: UNTESTED combination'
  echo 'Do not treat a clean version probe as proof that the semantic patches still apply or compile.'
fi
