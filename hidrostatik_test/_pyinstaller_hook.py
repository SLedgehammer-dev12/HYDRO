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
        numpy_core_dir = os.path.join(meipass, "numpy", "core")
        if os.path.isdir(numpy_core_dir):
            try:
                os.add_dll_directory(numpy_core_dir)
            except AttributeError:
                pass

        scipy_dirs = [
            os.path.join(meipass, "scipy", "linalg"),
            os.path.join(meipass, "scipy", "interpolate"),
            os.path.join(meipass, "scipy", "special"),
        ]
        for d in scipy_dirs:
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except AttributeError:
                    pass

        for root, _dirs, files in os.walk(meipass):
            for f in files:
                if f.endswith((".dll", ".pyd")):
                    try:
                        os.add_dll_directory(root)
                    except AttributeError:
                        break
            break

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
