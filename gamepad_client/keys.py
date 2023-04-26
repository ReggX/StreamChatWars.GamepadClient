
# native imports
import sys
from time import sleep

# pip imports
from keyboard import is_pressed
from keyboard import parse_hotkey

# local imports
from gamepad_client.tinkerforge_control import InputServerData
from gamepad_client.tinkerforge_control import print_current_state


class HotkeyManager:
  server_list: list[InputServerData]
  hotkey_list: list[str]
  keep_running: bool

  def __init__(
    self,
    server_list: list[InputServerData],
    hotkey_list: list[str],
  ) -> None:
    self.keep_running = True
    self.server_list = server_list
    self.hotkey_list = hotkey_list
    self.currently_pressed: dict[str, bool] = {}
    self.verify_hotkeys()

  def verify_hotkeys(self):
    for hotkey in self.hotkey_list:
      if hotkey:
        try:
          parse_hotkey(hotkey)
        except ValueError as e:
          print(
            f"Invalid hotkey! Failed to parse: {hotkey!r}\n"
            f"{e.args[0]}"
          )
          sys.exit(1)

  def scan_loop(self):
    while self.keep_running:
      for i, hotkey in enumerate(self.hotkey_list):
        if is_pressed(hotkey):
          if not self.currently_pressed.get(hotkey):
            server = self.server_list[i]
            server.active = not server.active
            self.currently_pressed[hotkey] = True
            print_current_state(self.server_list)
        else:
          self.currently_pressed[hotkey] = False
      sleep(0.001)
