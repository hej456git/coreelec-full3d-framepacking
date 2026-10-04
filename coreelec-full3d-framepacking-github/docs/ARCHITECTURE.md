# Architecture

Synthetic Full3D converts one ordinary progressive decoded packed frame into HDMI 1080p frame-packed 3D.

```text
ordinary decoder
      |
one current packed canvas
      |
   +--+--+
   |     |
  VD1   VD2
   |     |
 crop   crop
   \     /
 COMPOSE_MODE_3D
      |
  2205-line VPP
      |
 HDMI frame packing
```

## Source layouts

- Full-SBS: 3840x1080; left x=0..1919, right x=1920..3839.
- Full-TAB: 1920x2160; left y=0..1079, right y=1080..2159.
- Output: 1920x2205; left 0..1079, blank 1080..1124, right 1125..2204.

## Experimentally required pieces

- Kodi source detection and per-eye 16:9 geometry.
- Internal synthetic framepacking support.
- Shared live VD1 canvas via VD2 canvas0.
- Independent VD1/VD2 MIF crops.
- Synthetic vd_set_dcu execution.
- Synthetic VD2 position/MIF update gate.
- Synthetic VD2 scaler/blend update gate.
- COMPOSE_MODE_3D.
- VD2 destination 1125..2204.
- 2205-line picture, preblend, and postblend/output geometry.
- Strict MVC exclusion plus MVC VD2 GEN2 restoration.
- Kodi manual-stop teardown protection.

## Experimentally removed pieces

- Synthetic final VD2 GEN parity write.
- Synthetic AFBC support.
- Duplicate VD2-enable branch.
- Synthetic VD2 canvas1 refresh.
- Synthetic vdx_path_select extension.
