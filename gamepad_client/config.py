
# native imports
import json
from collections.abc import Mapping
from typing import Any


def read_config(filename: str = "config/default.json") -> Mapping[str, Any]:
  with open(filename, mode='r') as config_file:
    return json.load(config_file)


class Linear_Poti:
  def __init__(
    self,
    **kwargs
  ) -> None:
    self.uid: str = kwargs.get('uid', '')
    self.upper_threshold: int = kwargs.get('upper_threshold', 95)
    self.lower_threshold: int = kwargs.get('lower_threshold', 5)


class RGB_Button:
  def __init__(
    self,
    **kwargs
  ) -> None:
    self.uid: str = kwargs.get('uid', '')
    self.color_off: list[int] = kwargs.get('color_off', [1, 1, 1])
    self.color_on: list[int] = kwargs.get('color_on', [15, 15, 15])


class Remote_Gamepad:
  def __init__(
    self,
    **kwargs
  ) -> None:
    self.host: str = kwargs.get('host', 'localhost')
    self.port: int = kwargs.get('port', 33010)
    self.index: int = kwargs.get('index', 0)
    self.encryption_key: str = kwargs.get('encryption_key', '')
    self.encryption_mode: str = kwargs.get('encryption_mode', 'AES-GCM')
    self.hotkey: str = kwargs.get('hotkey', '')
    self.rgb_button: RGB_Button = RGB_Button(**kwargs.get('rgb_button', {}))


class Tinkerforge_Settings:
  def __init__(
    self,
    **kwargs
  ) -> None:
    self.host: str = kwargs.get('host', 'localhost')
    self.port: int = kwargs.get('port', 4223)
    self.linear_poti: Linear_Poti = Linear_Poti(**kwargs.get('linear_poti', {}))


class Client_Settings:
  def __init__(
    self,
    **kwargs
  ) -> None:
    self.local_gamepad_index: int = kwargs.get('local_gamepad_index', 0)
    self.remote_gamepads: list[Remote_Gamepad] = [
      Remote_Gamepad(**d) for d in kwargs.get('remote_gamepads', [])
    ]
    self.tinkerforge: Tinkerforge_Settings = Tinkerforge_Settings(**kwargs.get('tinkerforge', {}))


def get_client_settings(config: Mapping) -> Client_Settings:
  return Client_Settings(**config)
