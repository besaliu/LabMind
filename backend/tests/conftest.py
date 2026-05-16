import sys
import os
from pathlib import Path

# Ensure backend/ is on sys.path so `import storage`, `import main` etc. work
sys.path.insert(0, str(Path(__file__).parent.parent))
