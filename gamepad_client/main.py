
# native imports
import os
import sys
from collections.abc import Mapping
from functools import partial
from socket import SHUT_RDWR
from threading import Thread
from time import sleep

# local imports
from gamepad_client.keys import HotkeyManager
from streamchatwars._interfaces._gamepads import AbstractReport
from streamchatwars.fallback._vgamepad import XUSB_BUTTON
from streamchatwars.virtual_input.gamepads import XInput_Gamepad
from streamchatwars.virtual_input.input_handler import BasicGamepadHandler
from streamchatwars.virtual_input.input_server import RemoteInputServer

# internal imports
from .config import Client_Settings
from .config import get_client_settings
from .config import read_config
from .tinkerforge_control import InputServerData
from .tinkerforge_control import TinkerforgeControl


# Don't print prompt when importing pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
# pip imports
import pygame  # noqa: E402


pygame_button_to_XUSB_Button: dict[int, XUSB_BUTTON] = {
  0: XUSB_BUTTON.XUSB_GAMEPAD_A,
  1: XUSB_BUTTON.XUSB_GAMEPAD_B,
  2: XUSB_BUTTON.XUSB_GAMEPAD_X,
  3: XUSB_BUTTON.XUSB_GAMEPAD_Y,
  4: XUSB_BUTTON.XUSB_GAMEPAD_BACK,
  5: XUSB_BUTTON.XUSB_GAMEPAD_GUIDE,
  6: XUSB_BUTTON.XUSB_GAMEPAD_START,
  7: XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
  8: XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
  9: XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
  10: XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
  11: XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
  12: XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
  13: XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
  14: XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
  15: XUSB_BUTTON.XUSB_GAMEPAD_BACK
}


class XInput_REPORT_Builder(XInput_Gamepad):
  '''
  Subclass of XInput_Gamepad that doesn't communicate with
  the ViGem virtual gamepad instance, thereby effectively doing
  nothing when called.
  '''
  def __init__(self):
    '''
    Don't try to create virtual gamepad driver ressources so
    that it doesn't exist.
    '''
    self.report: AbstractReport = self.get_default_report()

  def __del__(self, *args, **kwargs):
    '''
    Don't try to release virtual gamepad driver ressources that don't exist.
    '''
    pass

  def update(self):
    '''
    Don't try to update virtual gamepad driver ressources that don't exist.
    '''
    pass

  def build_XInput_REPORT(
    self,
    button_data: dict[int, bool],
    axis_data: dict[int, float],
  ) -> AbstractReport:
    self.report: AbstractReport = self.get_default_report()
    i: int
    for i in button_data:
      self.report.wButtons += pygame_button_to_XUSB_Button[i].value * button_data[i]
    self.left_joystick_float(axis_data.get(0, 0.0), -1 * axis_data.get(1, 0.0))
    self.right_joystick_float(axis_data.get(2, 0.0), -1 * axis_data.get(3, 0.0))
    self.left_trigger_float((axis_data.get(4, 0.0) + 1.0) / 2)
    self.right_trigger_float((axis_data.get(5, 0.0) + 1.0) / 2)
    return self.report


class LocalController:
  """Class representing the PS4 controller. Pretty straightforward functionality."""

  def __init__(
    self,
    report_builder: XInput_REPORT_Builder,
    server_list: list[InputServerData],
    local_gamepad_index: int
  ):
    """Initialize the joystick components"""

    pygame.init()
    pygame.joystick.init()
    self.controller: pygame.joystick.Joystick = pygame.joystick.Joystick(
      local_gamepad_index
    )
    self.controller.init()
    self.axis_data: dict[int, float] = {}
    self.button_data: dict[int, bool] = {}
    self.hat_data: dict[int, tuple[int, int]] = {}
    self.report_builder: XInput_REPORT_Builder = report_builder
    self.server_list: list[InputServerData] = server_list

  def listen(self):
    """Listen for events to happen"""

    if not self.axis_data:
      self.axis_data = {}

    if not self.button_data:
      self.button_data = {}
      for i in range(self.controller.get_numbuttons()):
        self.button_data[i] = False

    if not self.hat_data:
      self.hat_data = {}
      for i in range(self.controller.get_numhats()):
        self.hat_data[i] = (0, 0)

    while TinkerforgeControl.keep_running:
      for event in pygame.event.get():
        if event.type == pygame.JOYAXISMOTION:
          self.axis_data[event.axis] = round(event.value, 4)
        elif event.type == pygame.JOYBUTTONDOWN:
          self.button_data[event.button] = True
        elif event.type == pygame.JOYBUTTONUP:
          self.button_data[event.button] = False
        elif event.type == pygame.JOYHATMOTION:
          self.hat_data[event.hat] = event.value

        report: AbstractReport = self.report_builder.build_XInput_REPORT(
          self.button_data,
          self.axis_data
        )
        for server_data in self.server_list:
          if server_data.active:
            func: partial = partial(BasicGamepadHandler.set_REPORT, server_data.index, report)
            server_data.server.execute(func)


def main():
  config_file = sys.argv[1] if len(sys.argv) > 1 else 'config/default.json'
  config: Mapping = read_config(filename=config_file)
  settings: Client_Settings = get_client_settings(config)

  print("Connecting to input server(s)...")

  report_builder = XInput_REPORT_Builder()
  server_list: list[InputServerData] = []
  hotkey_list: list[str] = []
  for remote_gamepad in settings.remote_gamepads:
    input_server = RemoteInputServer(
      host=remote_gamepad.host,
      port=remote_gamepad.port,
      encryption_key=remote_gamepad.encryption_key,
      encryption_mode=remote_gamepad.encryption_mode
    )
    input_server.add_gamepad(remote_gamepad.index)
    server_list.append(InputServerData(
      input_server,
      remote_gamepad.index,
      False,
      remote_gamepad.rgb_button
    ))
    hotkey_list.append(remote_gamepad.hotkey)
  if len(server_list) == 0:
    print("Config must contain at least 1 remote gamepad!")
    exit(1)
  hkm = HotkeyManager(server_list, hotkey_list)
  Thread(
    target=hkm.scan_loop,
    daemon=True
  ).start()
  print("Starting RGB Button control thread...")
  Thread(
    target=TinkerforgeControl.start_RGB_Buttons,
    args=[server_list, settings.tinkerforge],
    daemon=False
  ).start()
  sleep(0.5)
  controller_client = LocalController(
    report_builder,
    server_list,
    settings.local_gamepad_index
  )
  try:
    controller_client.listen()
  except KeyboardInterrupt:
    TinkerforgeControl.keep_running = False
    hkm.keep_running = False
    for server_data in server_list:
      server_data.server.sock.shutdown(SHUT_RDWR)
  except ConnectionAbortedError:
    TinkerforgeControl.keep_running = False
    for server_data in server_list:
      server_data.server.sock.shutdown(SHUT_RDWR)
    raise
