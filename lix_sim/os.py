"""api.OS implementation for the pygame simulator."""

from lix import api


class SimOS(api.OS):
    def __init__(self, display, buttons):
        self.display = display
        self.buttons = buttons
        self.ir   = None
        self.leds = None
        self.adc  = None

        self._quit_requested = False
        self._launch_request = None
        self._settings: dict = {}

    def quit(self):
        self._quit_requested = True

    def launch(self, name):
        self._launch_request = name
        self._quit_requested = True

    def settings_get(self, key, default=None):
        return self._settings.get(key, default)

    def settings_set(self, key, value):
        self._settings[key] = value
