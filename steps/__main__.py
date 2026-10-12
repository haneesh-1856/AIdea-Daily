"""Run the day: python -m steps [last step] [--date YYYY-MM-DD] [--force]"""

import sys

from steps.runner import main

if __name__ == "__main__":
    sys.exit(main())
