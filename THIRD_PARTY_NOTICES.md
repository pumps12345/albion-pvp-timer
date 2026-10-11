# Third-party notices

PVPTimer's own code is MIT-licensed (see [LICENSE](LICENSE)). The Windows download also bundles the
components below, each under its own license. Full license texts are in the [`licenses/`](licenses)
folder, which is included in every release zip.

| Component | Used for | License | Source |
|---|---|---|---|
| Qt 6 and Qt for Python (PySide6, Shiboken6) | Windows, overlay, sound | LGPL-3.0 | https://www.qt.io/qt-for-python · https://code.qt.io |
| pynput | Push-to-talk key | LGPL-3.0 | https://github.com/moses-palmer/pynput |
| Vosk (libvosk and Python bindings) | Offline speech recognition | Apache-2.0 | https://github.com/alphacep/vosk-api |
| vosk-model-small-en-us-0.15, © 2020 Alpha Cephei Inc | English speech model | Apache-2.0 | https://alphacephei.com/vosk/models |
| python-sounddevice, © 2015-2025 Matthias Geier | Microphone input | MIT | https://github.com/spatialaudio/python-sounddevice |
| PortAudio, © 1999-2011 Ross Bencina and Phil Burk | Audio I/O (inside sounddevice) | MIT-style | http://www.portaudio.com |
| CPython | Runtime | PSF License | https://www.python.org |

**LGPL components.** Qt, PySide6 and pynput are used unmodified and ship as separate, replaceable
files (DLLs and Python modules) inside the release folder's `_internal` directory. You may replace
them with your own builds of the same versions. Their source code is available from the links above.
The LGPL-3.0 text is in `licenses/LGPL-3.0.txt` and the GPL-3.0 text it builds on is in
`licenses/GPL-3.0.txt`.

## Game data

The built-in ability list (`src/pvptimer/data/default_abilities.json`) is generated from game files
published by the community project [ao-data/ao-bin-dumps](https://github.com/ao-data/ao-bin-dumps).
Item and ability names and cooldown values belong to Sandbox Interactive GmbH.

PVPTimer is a fan-made tool. It is **not affiliated with, endorsed by or supported by Sandbox
Interactive GmbH**. Albion Online is a trademark of Sandbox Interactive GmbH.
