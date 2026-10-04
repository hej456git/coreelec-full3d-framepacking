#!/bin/sh
# Run over SSH on the Nokia while a test movie is playing.
echo "=== CoreELEC ==="
grep -E 'PRETTY_NAME|VERSION=' /etc/os-release 2>/dev/null || true

echo
echo "=== Display / video axis ==="
printf '%-28s = ' display_mode
cat /sys/class/display/mode 2>/dev/null || echo unavailable
printf '%-28s = ' video_axis
cat /sys/class/video/axis 2>/dev/null || echo unavailable
printf '%-28s = ' screen_mode
cat /sys/class/video/screen_mode 2>/dev/null || echo unavailable

echo
echo "=== HDMI 3D state/capabilities ==="
for f in \
  /sys/class/amhdmitx/amhdmitx0/config \
  /sys/class/amhdmitx/amhdmitx0/disp_cap_3d \
  /sys/class/amhdmitx/amhdmitx0/edid_parsing; do
  if [ -r "$f" ]; then
    echo "--- $f"
    cat "$f"
  fi
done

echo
echo "=== Amlogic video 3D state ==="
for p in \
  g_framepacking_support \
  framepacking_width \
  framepacking_height \
  framepacking_blank \
  process_3d_type \
  vpp_3d_mode \
  video_3d_format \
  force_3d_scaler; do
  f="/sys/module/aml_media/parameters/$p"
  if [ -r "$f" ]; then
    printf '%-28s = ' "$p"
    cat "$f"
  fi
done

echo
echo "=== FULL3D / HDMI / decoder status ==="
dmesg | grep -Ei 'FULL3D|3dfp|amvdec_h264mvc|amvdec_h264' | tail -n 100 || true

echo
echo "=== Relevant Kodi log lines ==="
grep -Ei 'Full3D|CAMLCodec|full-resolution packed 3D|3dfp|stereo|frame.pack|framepack' /storage/.kodi/temp/kodi.log 2>/dev/null | tail -n 100 || true
