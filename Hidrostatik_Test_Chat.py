from hidrostatik_test.ui.app import HydrostaticTestApp, main

from hidrostatik_test.ui.constants import (
    AUTO_A_MODE,
    AUTO_B_MODE,
    MANUAL_A_MODE,
    MANUAL_B_MODE,
    REFERENCE_A_MODE,
    REFERENCE_B_MODE,
)

__all__ = [
    "AUTO_A_MODE",
    "AUTO_B_MODE",
    "MANUAL_A_MODE",
    "MANUAL_B_MODE",
    "REFERENCE_A_MODE",
    "REFERENCE_B_MODE",
    "HydrostaticTestApp",
    "main",
]


if __name__ == "__main__":
    import sys
    import tkinter.messagebox as mb

    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        mb.showerror(
            "Beklenmeyen Hata",
            f"Uygulama baslatilirken bir hata olustu:\n\n{exc}",
        )
        sys.exit(1)
