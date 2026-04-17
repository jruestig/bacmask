"""BacMask entry point. Bootstraps logging + launches the Kivy app."""

from bacmask.ui.app import main
from bacmask.utils.logger import setup_logging

if __name__ == "__main__":
    setup_logging()
    main()
