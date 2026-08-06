---
name: Python import analysis
description: Static analysis must be pointed at Replit's project-local Python packages.
---

Pyright needs `.pythonlibs/lib/python3.11/site-packages` in `extraPaths` to resolve packages installed by Replit's managed Python environment.

**Why:** The runtime can import installed packages even when the editor language server cannot discover them automatically.

**How to apply:** Keep the project-level Pyright configuration aligned with the active Python module and update the site-packages path if the Python version changes.