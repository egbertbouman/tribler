import sys
from pathlib import Path


def get_home_dir():
    return Path().home()


if sys.platform == "win32":
    def get_appstate_dir():
        homedir = get_home_dir()
        winversion = sys.getwindowsversion()
        if winversion[0] == 6:
            appdir = homedir / "AppData" / "Roaming" / ".Tribler"
        else:
            appdir = homedir / "Application Data" / ".Tribler"
        return appdir
else:
    # linux or darwin (mac)
    def get_appstate_dir():
        return get_home_dir() / ".Tribler"
