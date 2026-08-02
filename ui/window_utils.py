"""Shared window helpers for the CustomTkinter top-level windows."""

import tkinter as tk


def _apply_maximize(window) -> None:
    """Put `window` into its platform's maximized state."""
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


def maximize(window) -> None:
    """Open `window` maximized to fill the screen.

    Deferred to the first event-loop tick rather than applied immediately.
    CTk.mainloop() withdraws the window and calls deiconify() before entering
    the loop (customtkinter/windows/ctk_tk.py), and deiconify() restores the
    window to the *normal* state — so a "zoomed" set during __init__ is
    silently discarded, and the window opens maximized then shrinks. Callbacks
    queued with after() before mainloop() still run once the loop starts,
    which is after that deiconify.

    Any geometry() set beforehand remains the restore size, so un-maximizing
    returns to the designed layout size.
    """
    window.after(0, lambda: _apply_maximize(window))
