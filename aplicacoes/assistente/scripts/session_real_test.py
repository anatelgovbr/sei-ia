"""Compatibilidade: use ``smoke_session_host.py``.

O nome antigo permanece como um launcher fino para não quebrar comandos locais
existentes. Para atingir a stack Docker, use ``smoke_session_stack.sh``.
"""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("smoke_session_host.py")),
        run_name="__main__",
    )
