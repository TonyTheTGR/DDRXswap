# DDR X Song Swap v0.4 — BPM and experimental Shock Arrows

This updates the gameplay-validated v0.3.1 converter with **two** optional features.

The custom main title-screen artwork patch has been deliberately deferred.
The v0.3.1 per-song title cards, banner rendering, difficulty mapping, audio
conversion, and multi-song ISO replacement are retained.

## Install / run

* Windows 10/11, Python 3.10+, NumPy (`py -m pip install numpy`), and FFmpeg on PATH.
* Extract the ZIP and double-click `DDR_X_Song_Swap.bat`.
* Select an **original, unmodified DDR X USA ISO** and a new output path.
* Add StepMania songs (`.sm`, `.ssc`, folders, or ZIPs) and stock slots.
* Toggle **Update song-select BPM min/max** (enabled by default).
* Choose Shock Arrow mode (default `ignore`).

Commands:

```powershell
py ddrx_converter.py replace "D:\Games\DDR X USA.iso" "D:\StepMania\My Song.zip" --slot dace --out "D:\Games\DDRX_v04.iso" --shock ignore
py ddrx_converter.py replace "D:\Games\DDR X USA.iso" "D:\StepMania\My Song.zip" --slot dace --out "D:\Games\DDRX_shock_test.iso" --shock any
py ddrx_converter.py slots "D:\Games\DDR X USA.iso"
```

`--shock` accepts `ignore`, `all`, or `any`:

* `ignore`: drop mines (previous stable behavior).
* `all`: rows with mines on every panel become full-panel events.
* `any`: any mine-only row becomes a full-panel event; when a mine occurs
  alongside a step or hold head, insert the full-panel event 1/16 *whole note*
  (one quarter beat, 256 SSQ units) before that step. Colliding or negative
  target positions are skipped with a warning.

IMPORTANT: Full-panel masks observed in original DDR X Shock Arrow positions
are **not proof** that emitting those masks alone reproduces Shock Arrow
behavior. These experimental modes may render as ordinary simultaneous arrows
or behave differently. Test in PCSX2 and retain your original ISO. The
`ignore` mode is the safest default.

Song-select BPM: the executable song record stores **maximum** at +28 and
**minimum** at +30 as unsigned 16-bit values. Values are computed from the
simfile's `#BPMS:` list; this changes the *displayed* min/max, not the
chart's internal tempo timing. Stops are not counted as zero BPM.

Limitations: The native chart visibility flags, unlock states, save-data
compatibility, special SUNKiSS DROP routing, and title-screen asset have not
been newly investigated in this build. Shock Arrow behavior has not been
validated in-game. Only the DDR X USA release (`SLUS_217.67`) is supported.

Tests:

```powershell
py -m unittest test_ddrx_converter.py test_ddrx_v03.py test_ddrx_v04.py
```
