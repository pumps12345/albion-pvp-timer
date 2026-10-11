from pynput import keyboard, mouse

from pvptimer.hotkey import PttState, button_to_name, key_to_name
from pvptimer.settings import PttBinding


def test_key_to_name():
    assert key_to_name(keyboard.Key.f8) == "f8"
    assert key_to_name(keyboard.KeyCode.from_char("V")) == "v"
    assert key_to_name(keyboard.KeyCode.from_vk(200)) == "vk:200"


def test_button_to_name_only_accepts_bindable_buttons():
    assert button_to_name(mouse.Button.x1) == "x1"
    assert button_to_name(mouse.Button.middle) == "middle"
    assert button_to_name(mouse.Button.left) is None


def test_press_and_release_fire_once_and_ignore_auto_repeat():
    state = PttState(PttBinding("keyboard", "f8"))
    assert state.press("keyboard", "f8") is True
    assert state.press("keyboard", "f8") is False  # auto-repeat
    assert state.release("keyboard", "f8") is True
    assert state.release("keyboard", "f8") is False


def test_other_keys_and_devices_are_ignored():
    state = PttState(PttBinding("mouse", "x1"))
    assert state.press("keyboard", "x1") is False
    assert state.press("mouse", "x2") is False
    assert state.press("mouse", None) is False
    assert state.release("mouse", "x1") is False  # release without press


def test_no_binding_never_fires():
    state = PttState(None)
    assert state.press("keyboard", "f8") is False
