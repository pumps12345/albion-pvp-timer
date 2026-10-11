# Changelog

## Unreleased

- New **Delete shown…** button in the ability editor: deletes every ability currently listed (follows the
  tab and search), so the built-in list can be cleared in one step.
- New **Always listen** setting: PVPTimer listens continuously, so no push-to-talk key is needed. While
  it is on, the keyboard and mouse hook is released and unmatched speech is ignored silently.
  Push-to-talk is still the default.

## 0.1.0 (first public release)

- Voice-triggered enemy cooldown timers: hold push-to-talk, say an ability, and a countdown bar appears
  on a click-through overlay.
- Offline speech recognition (Vosk), limited to your saved phrases for accuracy.
- 484 built-in abilities generated from game data: every weapon's E, chest (R), helmet (D) and
  boots (F) abilities per item, and shared armor abilities on their own ("Dodge F").
- Ability editor with category tabs, search, phrase testing, and import/export.
- Settings: push-to-talk key or mouse button, microphone, speech delay, warning and READY timing, beep,
  overlay opacity, bar colors and sizes with a live preview.
- Voice commands "clear <phrase>" and "clear all".
