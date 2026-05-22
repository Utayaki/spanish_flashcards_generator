from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TEST_FILES = [
    "test_phase10_complete.py",
    "test_phase9_keyboard_saving.py",
    "test_phase8_verb_editor.py",
    "test_phase7_other_editor.py",
    "test_phase6_nominal_editor.py",
    "test_phase5_widgets.py",
    "test_phase4_threaded_search.py",
]

def main() -> int:
    root = Path(__file__).resolve().parent
    for test_file in TEST_FILES:
        print(f"== {test_file} ==", flush=True)
        result = subprocess.run([sys.executable, test_file], cwd=root, text=True)
        if result.returncode != 0:
            return result.returncode
    print("All complete-project checks passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
