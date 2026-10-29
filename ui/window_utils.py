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


def set_brand_icon(window) -> None:
    """Use the NoryvX mark as the window / taskbar icon (Windows .ico)."""
    import config
    try:
        window.iconbitmap(config.LOGO_ICO_PATH)
    except tk.TclError:
        pass


def brand_header(parent, px: int = 40, name_size: int = 22):
    """
    Build the shared "logo + NoryvX" lockup used by every window header.

    Returns the frame (not yet packed) so each caller can place it in its own
    layout. The CTkImage is stored on the frame to keep a live reference.
    """
    import customtkinter as ctk
    from PIL import Image

    import config

    lockup = ctk.CTkFrame(parent, fg_color="transparent")
    try:
        mark = Image.open(config.LOGO_MARK_SMALL_PATH)
        lockup._brand_img = ctk.CTkImage(light_image=mark, dark_image=mark,
                                         size=(px, px))
        ctk.CTkLabel(lockup, text="", image=lockup._brand_img,
                     fg_color="transparent").pack(side="left", padx=(0, 10))
    except OSError:
        pass  # missing asset: fall back to the wordmark alone

    ctk.CTkLabel(
        lockup, text=config.BRAND_NAME, fg_color="transparent",
        font=ctk.CTkFont(family=config.FONT_FAMILY, size=name_size, weight="bold"),
        text_color=config.BRAND_COLOR
    ).pack(side="left")
    return lockup
