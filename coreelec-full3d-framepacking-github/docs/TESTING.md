# Test matrix

A build is not promoted to `tested` until the hardware matrix has been checked on the Nokia Streaming Box 8010.

1. Full-SBS: both eyes complete, correct geometry, no bottom black bar.
2. Full-TAB: same.
3. FSBS -> MVC: MVC right-eye colour clean.
4. FTAB -> MVC: MVC right-eye colour clean.
5. MVC -> MVC: stock-like behaviour.
6. Manual Stop from synthetic Full3D: return to 2D; video axis 0 0 1919 1079; video plane hidden.
7. Basic network sanity after playback/Stop.

Known unresolved issue: intermittent black screen after natural EOF. Keep this separate from manual-stop regressions.
