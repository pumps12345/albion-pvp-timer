import uuid

from pvptimer.instance import InstanceServer, acquire_single_instance, ask_running_instance_to_show


def test_only_one_instance_can_hold_the_lock(tmp_path):
    first = acquire_single_instance(tmp_path)
    assert first is not None
    assert acquire_single_instance(tmp_path) is None
    first.unlock()
    again = acquire_single_instance(tmp_path)
    assert again is not None
    again.unlock()


def test_second_launch_asks_the_running_window_to_show(qtbot):
    name = f"pvptimer-test-{uuid.uuid4().hex}"
    server = InstanceServer(name)
    with qtbot.waitSignal(server.activated, timeout=3000):
        assert ask_running_instance_to_show(name) is True
    server.close()


def test_asking_with_no_running_instance_fails_quietly(qtbot):
    assert ask_running_instance_to_show(f"pvptimer-test-{uuid.uuid4().hex}") is False
