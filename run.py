"""Entry point: `python run.py` from source, and the script PyInstaller builds JobAds.exe from."""

import sys

from jobads.main import main

if __name__ == "__main__":
    sys.exit(main())
