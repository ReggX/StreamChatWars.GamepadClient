

# native imports
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from math import ceil
from math import floor
from operator import add
from time import sleep

# pip imports
from colorama import Back
from colorama import Fore
from tinkerforge.bricklet_linear_poti_v2 import BrickletLinearPotiV2
from tinkerforge.bricklet_rgb_led_button import BrickletRGBLEDButton
from tinkerforge.ip_connection import IPConnection

# local imports
from streamchatwars.virtual_input.input_server import RemoteInputServer

# internal imports
from .config import RGB_Button
from .config import Tinkerforge_Settings


@dataclass
class InputServerData:
  server: RemoteInputServer
  index: int
  active: bool
  rgb_button: RGB_Button


def print_current_state(server_list: list[InputServerData]):
  button_states: list[str] = []
  for server in server_list:
    color: str = (
      f'{Fore.BLACK}{Back.LIGHTCYAN_EX}'
      if server.active else
      f'{Fore.WHITE}{Back.RED}'
    )
    button_states.append(f'{color}[{server.index}]{Fore.RESET}{Back.RESET}')
  print(
    f'{" ".join(button_states)}',
    end='\r'
  )
  TinkerforgeControl.color_all_buttons(server_list)


class TinkerforgeControl:
  host: str = "localhost"
  port: int = 4223
  uid: str | None = None  # Change to the UID of your Linear Poti Bricklet 2.0
  upper_threshold: int = 95
  lower_threshold: int = 5
  old_position: int = -100
  old_section: int = -100
  keep_running: bool = True

  uid_dict: dict[str, BrickletRGBLEDButton] = {}
  # button state is saved independently from InputServerData.active since other
  # events (hotkeys) can manipulate state and we want the buttons to toggle
  # between all or nothing, not from one partial state to the opposite partial
  # state
  button_state_dict: dict[str, bool] = {}
  index_dict: dict[str, list[int]] = {}
  button_settings: list[RGB_Button] = []

  @classmethod
  def cb_button(
    cls,
    state,
    uid: str,
    server_list: list[InputServerData]
  ) -> None:
    if state:  # only trigger on release
      try:
        new_state = not cls.button_state_dict.get(uid, True)
        cls.button_state_dict[uid] = new_state
        for index in cls.index_dict[uid]:
          server_list[index].active = new_state
        print_current_state(server_list)
      except IndexError:
        pass

  @classmethod
  def color_all_buttons(cls, server_list: list[InputServerData]) -> None:
    color_dict: dict[str, tuple[int, int, int]] = {}
    button_dict: dict[str, BrickletRGBLEDButton] = {}
    for server_data in server_list:
      uid: str = server_data.rgb_button.uid
      old_color = color_dict.get(uid, (0, 0, 0))
      add_color = (
        server_data.rgb_button.color_on
        if server_data.active else
        server_data.rgb_button.color_off
      )
      color_dict[uid] = tuple(
        map(add, add_color, old_color)
      )
      button: BrickletRGBLEDButton = cls.uid_dict[uid]
      button_dict[uid] = button
    for uid, button in button_dict.items():
      button.set_color(*color_dict[uid])

  # Callback function for position callback
  @classmethod
  def cb_position(
    cls,
    position: int,
    section_width: float,
    server_list: list[InputServerData]
  ) -> None:
    if abs(position - cls.old_position) > 2:

      section = int((position - cls.lower_threshold) // section_width)
      if section == cls.old_section:
        return

      if section < 0:
        # None
        for server_data in server_list:
          server_data.active = False
        print("No gamepads active")
      elif section >= len(server_list):
        # All
        for server_data in server_list:
          server_data.active = True
        print("All gamepads active")
      else:
        # one section only
        for server_data in server_list:
          server_data.active = False
        server_list[section - 1].active = True
        print(f"Gamepad {server_list[section].index} active")

      cls.old_section = section
      cls.old_position = position

  @classmethod
  def print_steps(
    cls,
    server_list: list[InputServerData],
    section_width: float
  ):
    print(f"   <{cls.lower_threshold}    : No controllers active")
    for i, server_data in enumerate(server_list):
      lower_bounds = cls.lower_threshold + ceil(i * section_width)
      upper_bounds = cls.lower_threshold + floor((i + 0.9999) * section_width)
      print(
        f"{str(lower_bounds).rjust(3)} to {str(upper_bounds).rjust(3)}: "
        f"controller index {server_data.index} active"
      )
    print(f"   >={cls.upper_threshold}   : All controllers active")

  @classmethod
  def start_LinearPoti(
    cls,
    server_list: list[InputServerData],
    tinkerforge_settings: Tinkerforge_Settings
  ) -> None:
    cls.host = tinkerforge_settings.host
    cls.port = tinkerforge_settings.port
    cls.uid = tinkerforge_settings.linear_poti.uid
    cls.upper_threshold = tinkerforge_settings.linear_poti.upper_threshold
    cls.lower_threshold = tinkerforge_settings.linear_poti.lower_threshold

    assert(cls.uid is not None)
    assert(cls.upper_threshold >= cls.lower_threshold)

    number_of_sections = len(server_list)
    section_width = (cls.upper_threshold - cls.lower_threshold) / number_of_sections
    cls.print_steps(server_list, section_width)

    ipcon = IPConnection()  # Create IP connection
    lp = BrickletLinearPotiV2(cls.uid, ipcon)  # Create device object

    @contextmanager
    def ipcon_connect_manager(ipcon: IPConnection) -> Generator:
      try:
        ipcon.connect(cls.host, cls.port)  # Connect to brickd
        yield
      finally:
        ipcon.disconnect()

      # Don't use device before ipcon is connected
    with ipcon_connect_manager(ipcon):
      # initialize current position
      number_of_sections = len(server_list)
      section_width = (cls.upper_threshold - cls.lower_threshold) / number_of_sections
      cls.cb_position(
        lp.get_position(),
        section_width=section_width,
        server_list=server_list
      )

      # Register position callback to function cb_position
      lp.register_callback(
        lp.CALLBACK_POSITION,
        partial(cls.cb_position, section_width=section_width, server_list=server_list)
      )

      # Set period for position callback to 0.25s (250ms) without a threshold
      lp.set_position_callback_configuration(
        period=250,
        value_has_to_change=True,
        option=BrickletLinearPotiV2.THRESHOLD_OPTION_OFF,
        min=0,
        max=0
      )

      while cls.keep_running:
        sleep(0.25)

  @classmethod
  def start_RGB_Buttons(
    cls,
    server_list: list[InputServerData],
    tinkerforge_settings: Tinkerforge_Settings
  ) -> None:
    cls.host = tinkerforge_settings.host
    cls.port = tinkerforge_settings.port
    cls.button_settings = [
      server_data.rgb_button
      for server_data in server_list
    ]

    assert(len(cls.button_settings) > 0)

    ipcon = IPConnection()  # Create IP connection
    for i, button in enumerate(cls.button_settings):
      if button.uid not in cls.uid_dict:
        rgb_button = BrickletRGBLEDButton(button.uid, ipcon)
        cls.uid_dict[button.uid] = rgb_button
      else:
        rgb_button = cls.uid_dict[button.uid]
      try:
        index_list = cls.index_dict[button.uid]
      except KeyError:
        index_list = []
        cls.index_dict[button.uid] = index_list
      index_list.append(i)

    @contextmanager
    def ipcon_connect_manager(ipcon: IPConnection) -> Generator:
      try:
        ipcon.connect(cls.host, cls.port)  # Connect to brickd
        yield
      finally:
        for button in cls.uid_dict.values():
          button.set_color(0, 0, 0)
        ipcon.disconnect()

      # Don't use device before ipcon is connected
    with ipcon_connect_manager(ipcon):
      for uid, button in cls.uid_dict.items():
        cls.cb_button(True, uid=uid, server_list=server_list)
        button.register_callback(
          button.CALLBACK_BUTTON_STATE_CHANGED,
          partial(cls.cb_button, uid=uid, server_list=server_list)
        )

      while cls.keep_running:
        sleep(0.25)
