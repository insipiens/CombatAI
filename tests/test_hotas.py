from __future__ import annotations

import unittest

from dcs_radio_voice_control.hotas import HotasDevice, learn_binding, resolve_binding, wait_for_release


class FakeHotas:
    def __init__(self, devices: list[HotasDevice], states: dict[int, list[frozenset[int]]]) -> None:
        self._devices = devices
        self.states = states

    def devices(self) -> list[HotasDevice]:
        return self._devices

    def pressed_buttons(self, device_id: int) -> frozenset[int]:
        values = self.states[device_id]
        return values.pop(0) if len(values) > 1 else values[0]


class HotasTests(unittest.TestCase):
    def test_learning_scans_all_devices_for_first_new_press(self) -> None:
        stick = HotasDevice(4, "Stick", "guid-stick", 64)
        throttle = HotasDevice(9, "Throttle", "guid-throttle", 80)
        source = FakeHotas(
            [stick, throttle],
            {
                4: [frozenset(), frozenset()],
                9: [frozenset(), frozenset({47})],
            },
        )
        binding = learn_binding(source, timeout=0.1, poll_interval=0)
        self.assertEqual((binding.name, binding.button), ("Throttle", 47))

    def test_learning_ignores_button_held_when_scan_starts(self) -> None:
        stick = HotasDevice(4, "Stick", "guid-stick", 64)
        source = FakeHotas(
            [stick],
            {4: [frozenset({2}), frozenset({2}), frozenset(), frozenset({2})]},
        )
        binding = learn_binding(source, timeout=0.1, poll_interval=0)
        self.assertEqual(binding.button, 2)

    def test_saved_binding_follows_unique_guid_and_name_after_reorder(self) -> None:
        devices = [HotasDevice(12, "Throttle", "guid-throttle", 80)]
        binding = resolve_binding(
            devices,
            {"device_id": 9, "name": "Throttle", "guid": "guid-throttle", "button": 47},
        )
        self.assertEqual(binding.device_id, 12)

    def test_identical_reordered_devices_are_rejected(self) -> None:
        devices = [
            HotasDevice(12, "Panel", "same-guid", 64),
            HotasDevice(13, "Panel", "same-guid", 64),
        ]
        with self.assertRaisesRegex(OSError, "uniquely"):
            resolve_binding(
                devices,
                {"device_id": 9, "name": "Panel", "guid": "same-guid", "button": 4},
            )

    def test_release_confirmation_waits_until_button_is_up(self) -> None:
        device = HotasDevice(4, "Stick", "guid-stick", 64)
        source = FakeHotas([device], {4: [frozenset({3}), frozenset(), frozenset()]})
        binding = resolve_binding(
            [device],
            {"device_id": 4, "name": "Stick", "guid": "guid-stick", "button": 3},
        )
        wait_for_release(source, binding, timeout=0.1, poll_interval=0)
        self.assertEqual(source.pressed_buttons(4), frozenset())


if __name__ == "__main__":
    unittest.main()
