"""SDL-backed HOTAS discovery and push-to-talk learning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Callable, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class HotasDevice:
    device_id: int
    name: str
    guid: str
    button_count: int


@dataclass(frozen=True, slots=True)
class HotasBinding:
    device_id: int
    name: str
    guid: str
    button: int

    def document(self) -> dict[str, object]:
        return {"mode": "hotas", **asdict(self)}


class HotasInput(Protocol):
    def devices(self) -> list[HotasDevice]: ...
    def pressed_buttons(self, device_id: int) -> frozenset[int]: ...


class SdlHotasInput:
    """Poll DirectInput/XInput controllers through pygame-ce's SDL backend."""

    def __init__(self) -> None:
        try:
            import pygame
        except ImportError as exc:
            raise OSError("SDL controller support is not installed. Run setup.bat.") from exc
        self._pygame = pygame
        # SDL's event pump needs the video subsystem, but audio must remain untouched.
        pygame.display.init()
        pygame.joystick.init()
        self._controllers: dict[int, object] = {}
        self._refresh()

    def devices(self) -> list[HotasDevice]:
        self._pump()
        self._refresh()
        return [
            HotasDevice(
                device_id=instance_id,
                name=controller.get_name(),
                guid=controller.get_guid(),
                button_count=controller.get_numbuttons(),
            )
            for instance_id, controller in sorted(self._controllers.items())
        ]

    def pressed_buttons(self, device_id: int) -> frozenset[int]:
        self._pump()
        controller = self._controllers.get(device_id)
        if controller is None or not controller.get_init():
            self._refresh()
            controller = self._controllers.get(device_id)
        if controller is None:
            raise OSError(f"SDL controller {device_id} is no longer available.")
        return frozenset(
            index + 1
            for index in range(controller.get_numbuttons())
            if controller.get_button(index)
        )

    def _pump(self) -> None:
        self._pygame.event.pump()

    def _refresh(self) -> None:
        live: dict[int, object] = {}
        for index in range(self._pygame.joystick.get_count()):
            controller = self._pygame.joystick.Joystick(index)
            if not controller.get_init():
                controller.init()
            live[controller.get_instance_id()] = controller
        self._controllers = live


def learn_binding(
    source: HotasInput,
    *,
    timeout: float = 20.0,
    poll_interval: float = 0.02,
    cancelled: Callable[[], bool] | None = None,
) -> HotasBinding:
    devices = source.devices()
    if not devices:
        raise OSError("SDL reported no connected joystick or HOTAS devices.")
    previous = {device.device_id: source.pressed_buttons(device.device_id) for device in devices}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancelled is not None and cancelled():
            raise KeyboardInterrupt
        for device in devices:
            try:
                current = source.pressed_buttons(device.device_id)
            except OSError:
                continue
            new_presses = current - previous[device.device_id]
            previous[device.device_id] = current
            if new_presses:
                return HotasBinding(
                    device.device_id,
                    device.name,
                    device.guid,
                    min(new_presses),
                )
        time.sleep(poll_interval)
    raise TimeoutError("No new HOTAS button press was detected within the setup period.")


def wait_for_release(
    source: HotasInput,
    binding: HotasBinding,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.02,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if binding.button not in source.pressed_buttons(binding.device_id):
            return
        time.sleep(poll_interval)
    raise TimeoutError("The learned HOTAS button was not released.")


def resolve_binding(devices: Sequence[HotasDevice], saved: dict[str, object]) -> HotasBinding:
    button = saved.get("button")
    if not isinstance(button, int) or button < 1:
        raise OSError("The saved HOTAS button is invalid. Open CombatAI configuration.")
    saved_name = saved.get("name")
    saved_guid = saved.get("guid")
    candidates = [
        device for device in devices if (device.name, device.guid) == (saved_name, saved_guid)
    ]
    if len(candidates) != 1:
        raise OSError("The saved HOTAS is no longer uniquely available. Open CombatAI configuration.")
    device = candidates[0]
    if button > device.button_count:
        raise OSError(f"{device.name} no longer reports button {button}.")
    return HotasBinding(device.device_id, device.name, device.guid, button)


class HotasButton:
    def __init__(self, source: HotasInput, binding: HotasBinding) -> None:
        self.source = source
        self.binding = binding

    @property
    def label(self) -> str:
        return f"{self.binding.name} button {self.binding.button}"

    def is_down(self) -> bool:
        return self.binding.button in self.source.pressed_buttons(self.binding.device_id)
