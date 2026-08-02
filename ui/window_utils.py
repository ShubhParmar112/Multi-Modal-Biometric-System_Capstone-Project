"""Shared window helpers for the CustomTkinter top-level windows."""

import tkinter as tk


def maximize(window) -> None:
    """Open `window` maximized to fill the screen.

    "zoomed" is the state name Windows and most Linux window managers use.
    A few X11 WMs only accept the "-zoomed" attribute instead, and some
    accept neither — in that case we size the window to the screen ourselves
    so it still fills the display rather than silently staying small.

    Any geometry() set before this call remains the window's restore size,
    so un-maximizing returns to the designed layout size.
    """
    try:
        window.state("zoomed")
        return
    except tk.TclError:
        pass

    try:
        window.attributes("-zoomed", True)
        return
    except tk.TclError:
        pass

    window.geometry(
        f"{window.winfo_screenwidth()}x{window.winfo_screenheight()}+0+0")
