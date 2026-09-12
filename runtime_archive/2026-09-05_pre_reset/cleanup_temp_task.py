import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree

work_tree.mark_task_dropped("task_9112dc3f", reason="temp_validation_cleanup")
print("dropped task_9112dc3f")
