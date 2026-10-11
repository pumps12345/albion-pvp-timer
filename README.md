# PVPTimer

Voice-triggered enemy cooldown timers for Albion Online. Hold your push-to-talk key, say
what the enemy just used ("blood letter e"), and a countdown appears on a transparent
overlay above the game.

PVPTimer never reads game memory, injects into the game, or inspects network traffic.
It only listens to your microphone while push-to-talk is held and draws a window on top
of your screen.

## Using it

1. Unzip `PVPTimer-x.y.z.zip` anywhere and run `PVPTimer.exe`. The PVPTimer window opens
   with your ability list.
2. On first run, pick your push-to-talk key or mouse side button. Using the same key as
   Discord works well: your callout to the team also starts the timer.
3. Click **+ Add** to add abilities: a name, slot, cooldown in seconds, and one or more
   phrases you'll say. Use **Test phrase** to check how the app hears you.
4. Run Albion in **borderless fullscreen** or **windowed** mode. Exclusive fullscreen hides
   the overlay (the ready beep still plays).
5. Click **⇕ Move overlay** to drag the timers where you want them, then click it again.
   **⚙ Settings → Overlay appearance** changes bar colors and size; **▶ Test timer** shows
   a sample.
6. **Minimize** the window while you play. Closing it (✕ or **Quit**) stops the timers.

Voice commands: any saved phrase starts or restarts that ability's timer.
`clear <phrase>` removes one timer. `clear all` removes every timer.

### Tips

- A ⚠ word status means the speech model doesn't know a word (often Albion names).
  Respell it with common words: `bloodletter` → `blood letter`.
- Single letters are easy to mishear. Add a few variants per ability ("blood e",
  "blood letter e").
- If push-to-talk never fires while in game, check that Albion is not running as
  administrator. Windows blocks non-admin apps from seeing keys pressed in admin windows.
- Some antivirus tools flag new unsigned executables. The source is in this repository.

### Files

Your abilities, settings and log are in `%APPDATA%\PVPTimer\`. Export/Import in the
editor shares ability lists as JSON.

## Development

```bash
"$LOCALAPPDATA/Programs/Python/Python313/python.exe" -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python scripts/get_model.py
.venv/Scripts/python -m pytest
.venv/Scripts/python -m pvptimer
```

To ship your ability list as the default for everyone: Editor → **Export…**, save the
file over `src/pvptimer/data/default_abilities.json`, then rebuild.

### Building a release

```bash
.venv/Scripts/pyinstaller pvptimer.spec --noconfirm
powershell -NoProfile -Command "Compress-Archive -Force dist/PVPTimer dist/PVPTimer-0.1.0.zip"
```
