from __future__ import annotations

import os
import sys


def _setup_numpy_dll_paths() -> None:
    if not getattr(sys, "frozen", False):
        return

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        return

    if sys.platform == "win32":
        import glob

        registered = set()
        for pattern in [
            os.path.join(meipass, "numpy", "core", "*.dll"),
            os.path.join(meipass, "numpy", "core", "*.pyd"),
            os.path.join(meipass, "scipy", "**", "*.dll"),
            os.path.join(meipass, "scipy", "**", "*.pyd"),
            os.path.join(meipass, "**", "*.dll"),
            os.path.join(meipass, "**", "*.pyd"),
        ]:
            for f in glob.glob(pattern, recursive=True):
                d = os.path.dirname(f)
                if d not in registered:
                    registered.add(d)
                    try:
                        os.add_dll_directory(d)
                    except AttributeError:
                        pass

    if sys.platform == "darwin":
        _orig_dyld = os.environ.get("DYLD_LIBRARY_PATH", "")
        numpy_lib_paths = []
        for candidate in [
            os.path.join(meipass, "numpy", "core"),
            os.path.join(meipass, ".dylibs"),
        ]:
            if os.path.isdir(candidate):
                numpy_lib_paths.append(candidate)
        if numpy_lib_paths:
            extra = ":".join(numpy_lib_paths)
            if _orig_dyld:
                os.environ["DYLD_LIBRARY_PATH"] = f"{extra}:{_orig_dyld}"
            else:
                os.environ["DYLD_LIBRARY_PATH"] = extra


_setup_numpy_dll_paths()
