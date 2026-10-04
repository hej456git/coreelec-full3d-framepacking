# Changelog

## v0.3.0-rc1-clean

- Release candidate based on the fully tested v0.2.30 rendering architecture.
- Permanently removes synthetic VD2 `canvas1` refresh (EXP-F passed).
- Permanently leaves `vdx_path_select()` stock/MVC-only (EXP-G passed).
- Retains `COMPOSE_MODE_3D` after direct negative test.
- Retains synthetic `vd_set_dcu()` after direct negative test.
- Retains synthetic VD2 position/MIF gate after EXP-H produced a grey right eye with zero VD2 crop registers.
- Retains synthetic VD2 scaler/blend gate after EXP-I produced a grey right eye despite correct VD2 crop registers.
- Retains 2205-line preblend height after EXP-J restored the 45-line bottom black bar with preblend=2160.
- Removes the development-only `full3d_diag_dump` module parameter and FULL3D-DIAG register dump machinery.
- Removes development one-time driver logging and the diagnostic-trigger helper.
- Keeps useful Kodi mode-selection logs and all rendering/teardown behavior.
- Natural-EOF black-screen issue remains a separate deferred TODO.
