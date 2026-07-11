"""
Banking Interface - Post-authentication ATM dashboard.

Rendered as a full-window PAGE inside the existing ATM window (not a separate
Toplevel), so the whole experience stays in one seamless layout. Opens after a
successful biometric login and presents a tile-based transaction menu
(deposit, withdraw, transfer, PIN change, mini statement, exit) styled with the
same dark-teal theme as the authentication screen.

All actions are wired to the same BankingService the CLI / web app use, so
fraud scoring, e-mail alerts and transaction logging happen identically. Every
prompt (amount entry, PIN entry, statement) is shown as an in-window overlay
rather than a popup dialog, keeping a single-window feel.
"""

import datetime
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageDraw

import config
from banking.account_manager import BankingService
from database.db_manager import DatabaseManager
from utils.logger import logger

# ── Palette (derived from config, kept consistent with the auth screen) ──
BG        = config.SECONDARY_COLOR      # page background      #1A1A2E
CARD      = "#152036"                   # tile / panel surface (refined)
CARD_HV   = "#1B2947"                   # tile hover surface
ACCENT    = config.PRIMARY_COLOR        # teal                 #00D4AA
ACCENT_HV = "#00B894"                   # teal hover
DANGER    = config.ACCENT_COLOR         # red                  #E94560
TEXT      = config.TEXT_COLOR           # #EAEAEA
MUTED     = "#8A97AC"                   # secondary text
HEADER_BG = "#0D1526"                   # header / footer bar
PANEL_DK  = "#0A0F1A"                   # inset fields
BORDER    = "#243149"                   # subtle borders
PANEL_CARD = "#16213E"                  # overlay panel surface

# Per-action accent colours — a restrained, cohesive fintech palette that
# colour-codes each transaction instead of two flat teal blocks.
COL_WITHDRAW  = "#00D4AA"   # teal
COL_DEPOSIT   = "#34D399"   # emerald
COL_TRANSFER  = "#5B8DEF"   # blue
COL_STATEMENT = "#A78BFA"   # violet
COL_PIN       = "#F5A623"   # amber
COL_EXIT      = "#E94560"   # red


def _fmt(amount: float) -> str:
    """Format a rupee amount the same way the e-mail alerts do."""
    return f"₹{amount:,.2f}"


def _blend(base_hex: str, mix_hex: str, t: float) -> str:
    """Blend two hex colours; `t` is the fraction of `mix_hex`."""
    a = base_hex.lstrip("#")
    b = mix_hex.lstrip("#")
    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    c = round(ab + (bb - ab) * t)
    return f"#{r:02X}{g:02X}{c:02X}"


def _draw_icon(name: str, color: str, px: int = 52) -> Image.Image:
    """
    Render a crisp, anti-aliased line icon as an RGBA image.

    Icons are drawn on a 64-unit grid at 4x supersampling then downscaled, so
    strokes get clean rounded caps and smooth edges — no emoji, no bitmap fuzz.
    """
    ss = 4
    S = 64 * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = int(5.0 * ss)
    r = w // 2

    def sc(pts):
        return [(x * ss, y * ss) for (x, y) in pts]

    def stroke(pts):
        p = sc(pts)
        d.line(p, fill=color, width=w, joint="curve")
        for (x, y) in p:                       # rounded caps/joins
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)

    def rrect(box, radius):
        x0, y0, x1, y1 = [v * ss for v in box]
        d.rounded_rectangle((x0, y0, x1, y1), radius=radius * ss,
                            outline=color, width=w)

    if name == "deposit":                       # up arrow onto a tray
        stroke([(14, 50), (50, 50)])
        stroke([(32, 46), (32, 16)])
        stroke([(21, 27), (32, 16), (43, 27)])
    elif name == "withdraw":                     # down arrow onto a tray
        stroke([(14, 50), (50, 50)])
        stroke([(32, 14), (32, 40)])
        stroke([(21, 29), (32, 40), (43, 29)])
    elif name == "transfer":                     # two opposing arrows
        stroke([(15, 25), (46, 25)])
        stroke([(39, 18), (47, 25), (39, 32)])
        stroke([(49, 41), (18, 41)])
        stroke([(25, 34), (17, 41), (25, 48)])
    elif name == "statement":                    # document with lines
        rrect((19, 10, 45, 54), 5)
        stroke([(26, 22), (38, 22)])
        stroke([(26, 30), (38, 30)])
        stroke([(26, 38), (34, 38)])
    elif name == "pin":                          # padlock
        rrect((18, 29, 46, 53), 5)
        d.arc([24 * ss, 15 * ss, 40 * ss, 37 * ss], start=180, end=360,
              fill=color, width=w)
        d.ellipse([(32 - 2.6) * ss, (39 - 2.6) * ss,
                   (32 + 2.6) * ss, (39 + 2.6) * ss], fill=color)
    elif name == "exit":                         # door + outward arrow
        stroke([(34, 12), (16, 12), (16, 52), (34, 52)])
        stroke([(26, 32), (50, 32)])
        stroke([(42, 24), (52, 32), (42, 40)])
    elif name == "enroll":                       # person + plus
        d.ellipse([20 * ss, 13 * ss, 34 * ss, 27 * ss],
                  outline=color, width=w)
        d.arc([13 * ss, 33 * ss, 41 * ss, 61 * ss], start=180, end=360,
              fill=color, width=w)
        stroke([(48, 20), (48, 34)])
        stroke([(41, 27), (55, 27)])
    elif name == "encode":                       # face inside scan frame
        stroke([(22, 13), (14, 13), (14, 21)])
        stroke([(42, 13), (50, 13), (50, 21)])
        stroke([(50, 43), (50, 51), (42, 51)])
        stroke([(22, 51), (14, 51), (14, 43)])
        d.ellipse([26 * ss, 21 * ss, 38 * ss, 33 * ss],
                  outline=color, width=w)
        d.arc([22 * ss, 33 * ss, 42 * ss, 49 * ss], start=180, end=360,
              fill=color, width=w)
    elif name == "users":                        # two people
        d.ellipse([17 * ss, 14 * ss, 31 * ss, 28 * ss],
                  outline=color, width=w)
        d.arc([10 * ss, 34 * ss, 38 * ss, 62 * ss], start=180, end=360,
              fill=color, width=w)
        d.arc([36 * ss, 17 * ss, 50 * ss, 31 * ss], start=270, end=90,
              fill=color, width=w)
        d.arc([36 * ss, 36 * ss, 58 * ss, 58 * ss], start=245, end=360,
              fill=color, width=w)
    elif name == "selftest":                     # shield + check
        stroke([(32, 11), (49, 17), (47, 36), (32, 53),
                (17, 36), (15, 17), (32, 11)])
        stroke([(24, 31), (30, 38), (41, 24)])
    elif name == "ports":                        # power plug + cable
        stroke([(25, 11), (25, 21)])
        stroke([(39, 11), (39, 21)])
        rrect((19, 21, 45, 38), 5)
        stroke([(32, 38), (32, 46)])
        stroke([(32, 46), (28, 52)])

    return img.resize((px, px), Image.LANCZOS)


class BankingInterface:
    """
    Full-window banking dashboard shown as a page over the ATM window.

    Args:
        parent:  The root/Toplevel of the ATM interface.
        db:      Shared DatabaseManager instance.
        user_id: The authenticated user's id.
        on_exit: Optional callback fired when the user leaves the dashboard
                 (used to reset the auth screen back to "System Ready").
    """

    def __init__(self, parent, db: DatabaseManager, user_id: str,
                 on_exit: Optional[Callable] = None):
        self.parent = parent
        self.db = db
        self.user_id = user_id
        self.user = db.get_user(user_id) or {"name": "Customer"}
        self.banking = BankingService(db)
        self.on_exit = on_exit
        self._toast_job = None
        self._overlay = None
        self._icon_cache = {}   # keeps CTkImage refs alive + avoids redraws

        account = self._account()
        self.account_number = account["account_number"] if account else "—"

        # ── Page container (covers the whole window; same layout, no box) ──
        self.container = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        self.container.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_header()
        self._build_grid()
        self._build_footer()

    # ─────────────────────────────────────────────────────────
    # Data helpers
    # ─────────────────────────────────────────────────────────

    def _account(self):
        accounts = self.db.get_accounts_by_user(self.user_id)
        return accounts[0] if accounts else None

    # ─────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────

    def _build_header(self):
        header = ctk.CTkFrame(self.container, height=120, fg_color=HEADER_BG,
                              corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Left: avatar + greeting
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=36, pady=20)

        name = self.user.get("name") or "Customer"
        parts = name.split()
        initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()

        avatar = ctk.CTkFrame(left, width=58, height=58, corner_radius=29,
                              fg_color=_blend(HEADER_BG, ACCENT, 0.22),
                              border_width=1, border_color=_blend(HEADER_BG, ACCENT, 0.5))
        avatar.pack(side="left", padx=(0, 16))
        avatar.pack_propagate(False)
        ctk.CTkLabel(
            avatar, text=initials, fg_color="transparent",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=20, weight="bold"),
            text_color=ACCENT
        ).pack(expand=True)

        text_col = ctk.CTkFrame(left, fg_color="transparent")
        text_col.pack(side="left")

        hour = datetime.datetime.now().hour
        greeting = ("Good Morning" if hour < 12
                    else "Good Afternoon" if hour < 17
                    else "Good Evening")
        first_name = parts[0] if parts else ""

        ctk.CTkLabel(
            text_col, text=f"{greeting}, {first_name}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=28, weight="bold"),
            text_color=TEXT, anchor="w"
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_col, text="Please select a transaction",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
            text_color=MUTED, anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        # Right: balance card + clock
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=36, pady=18)

        balance_card = ctk.CTkFrame(right, fg_color=CARD, corner_radius=14,
                                    border_width=1, border_color=BORDER)
        balance_card.pack(anchor="e")

        ctk.CTkLabel(
            balance_card, text="AVAILABLE BALANCE",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=10, weight="bold"),
            text_color=MUTED
        ).pack(padx=24, pady=(12, 0), anchor="e")

        self.balance_label = ctk.CTkLabel(
            balance_card, text="—",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=26, weight="bold"),
            text_color=ACCENT
        )
        self.balance_label.pack(padx=24, pady=(0, 12), anchor="e")

        self.clock_label = ctk.CTkLabel(
            right, text="",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11),
            text_color=MUTED
        )
        self.clock_label.pack(anchor="e", pady=(8, 0))

        # Divider under header
        ctk.CTkFrame(self.container, height=2, fg_color=BORDER).pack(fill="x")

        self._refresh_balance()
        self._tick_clock()

    def _build_grid(self):
        wrap = ctk.CTkFrame(self.container, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=28, pady=24)

        for c in range(3):
            wrap.grid_columnconfigure(c, weight=1, uniform="col")
        for r in range(2):
            wrap.grid_rowconfigure(r, weight=1, uniform="row")

        # (icon, title, subtitle, command, accent colour)
        tiles = [
            ("withdraw", "Withdraw", "Cash withdrawal", self._do_withdraw, COL_WITHDRAW),
            ("deposit", "Deposit", "Add money to account", self._do_deposit, COL_DEPOSIT),
            ("transfer", "Transfer", "Send to another account", self._do_transfer, COL_TRANSFER),
            ("statement", "Mini Statement", "Recent transactions", self._do_statement, COL_STATEMENT),
            ("pin", "PIN Change", "Update your 4-digit PIN", self._do_pin_change, COL_PIN),
            ("exit", "Exit", "End session / take card", self._do_exit, COL_EXIT),
        ]

        for idx, (icon, title, subtitle, command, color) in enumerate(tiles):
            row, col = divmod(idx, 3)
            tile = self._make_tile(wrap, icon, title, subtitle, command, color)
            tile.grid(row=row, column=col, sticky="nsew", padx=12, pady=12)

    def _icon_image(self, name, color, px=48):
        key = (name, color, px)
        if key not in self._icon_cache:
            pil = _draw_icon(name, color, px)
            self._icon_cache[key] = ctk.CTkImage(
                light_image=pil, dark_image=pil, size=(px, px)
            )
        return self._icon_cache[key]

    def _make_tile(self, parent, icon_name, title, subtitle, command, color):
        """A professional transaction card: icon chip, title/subtitle, chevron."""
        base = CARD
        hover = CARD_HV
        chip_bg = _blend(CARD, color, 0.18)
        chip_bg_hv = _blend(CARD, color, 0.30)

        tile = ctk.CTkFrame(parent, fg_color=base, corner_radius=18,
                            border_width=1, border_color=BORDER)

        inner = ctk.CTkFrame(tile, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=26, pady=24)

        # Top row: icon chip (left) + chevron (right)
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        chip = ctk.CTkFrame(top, width=64, height=64, corner_radius=16,
                            fg_color=chip_bg)
        chip.pack(side="left")
        chip.pack_propagate(False)
        icon_label = ctk.CTkLabel(
            chip, text="", image=self._icon_image(icon_name, color),
            fg_color="transparent"
        )
        icon_label.pack(expand=True)

        chevron = ctk.CTkLabel(
            top, text="›", fg_color="transparent",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=26, weight="bold"),
            text_color=_blend(CARD, TEXT, 0.35)
        )
        chevron.pack(side="right", anchor="n")

        # Bottom-anchored text block
        bottom = ctk.CTkFrame(inner, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", anchor="w")

        title_label = ctk.CTkLabel(
            bottom, text=title, fg_color="transparent",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=21, weight="bold"),
            text_color=TEXT, anchor="w"
        )
        title_label.pack(anchor="w")

        sub_label = ctk.CTkLabel(
            bottom, text=subtitle, fg_color="transparent",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=12),
            text_color=MUTED, anchor="w"
        )
        sub_label.pack(anchor="w", pady=(2, 0))

        def on_enter(_=None):
            tile.configure(fg_color=hover, border_color=color)
            chip.configure(fg_color=chip_bg_hv)
            chevron.configure(text_color=color)

        def on_leave(_=None):
            tile.configure(fg_color=base, border_color=BORDER)
            chip.configure(fg_color=chip_bg)
            chevron.configure(text_color=_blend(CARD, TEXT, 0.35))

        # Whole card behaves as one button.
        for widget in (tile, inner, top, chip, icon_label, chevron,
                       bottom, title_label, sub_label):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)

        return tile

    def _build_footer(self):
        footer = ctk.CTkFrame(self.container, height=42, fg_color=HEADER_BG,
                              corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkLabel(
            footer, text=f"Account  •  {self.account_number}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11),
            text_color=MUTED
        ).pack(side="left", padx=24)

        self.status_label = ctk.CTkLabel(
            footer, text="",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=12, weight="bold"),
            text_color=ACCENT
        )
        self.status_label.pack(side="left", expand=True)

        ctk.CTkLabel(
            footer, text="SecureATM  •  Contact Center: 1800-000-0000",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11),
            text_color=MUTED
        ).pack(side="right", padx=24)

    # ─────────────────────────────────────────────────────────
    # Live header updates
    # ─────────────────────────────────────────────────────────

    def _refresh_balance(self):
        balance = self.banking.get_balance(self.user_id)
        self.balance_label.configure(
            text=_fmt(balance) if balance is not None else "No account"
        )

    def _tick_clock(self):
        if not self.container.winfo_exists():
            return
        now = datetime.datetime.now().strftime("%d %b %Y  |  %H:%M:%S")
        self.clock_label.configure(text=now)
        self.container.after(1000, self._tick_clock)

    def _toast(self, message: str, ok: bool = True):
        """Flash a status message in the footer for a few seconds."""
        color = ACCENT if ok else DANGER
        self.status_label.configure(text=message, text_color=color)
        if self._toast_job:
            self.container.after_cancel(self._toast_job)
        self._toast_job = self.container.after(
            5000, lambda: self.status_label.configure(text="")
        )

    def _after_txn(self, ok: bool, message: str, balance: Optional[float]):
        if balance is not None:
            self.balance_label.configure(text=_fmt(balance))
        self._toast(message, ok=ok)

    # ─────────────────────────────────────────────────────────
    # In-window overlay (modal panel, no separate window)
    # ─────────────────────────────────────────────────────────

    def _open_overlay(self, width: int, height: int, title: str,
                      subtitle: str = ""):
        """Dim the page and return a centered card panel to fill in."""
        self._close_overlay()
        backdrop = ctk.CTkFrame(self.container, fg_color="#05070D",
                                corner_radius=0)
        backdrop.place(relx=0, rely=0, relwidth=1, relheight=1)
        backdrop.bind("<Button-1>", lambda _e: None)  # swallow clicks

        panel = ctk.CTkFrame(backdrop, width=width, height=height,
                             fg_color=PANEL_CARD, corner_radius=18,
                             border_width=1, border_color=BORDER)
        panel.place(relx=0.5, rely=0.5, anchor="center")
        panel.pack_propagate(False)

        ctk.CTkLabel(
            panel, text=title,
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=19, weight="bold"),
            text_color=TEXT
        ).pack(pady=(22, 2))
        if subtitle:
            ctk.CTkLabel(
                panel, text=subtitle,
                font=ctk.CTkFont(family=config.FONT_FAMILY, size=12),
                text_color=MUTED
            ).pack(pady=(0, 6))

        self._overlay = backdrop
        return panel

    def _close_overlay(self):
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None

    # ─────────────────────────────────────────────────────────
    # Transaction actions
    # ─────────────────────────────────────────────────────────

    def _do_deposit(self):
        self._ask_amount(
            "Deposit", "Enter amount to deposit",
            lambda amt: self._after_txn(*self.banking.deposit(self.user_id, amt))
        )

    def _do_withdraw(self):
        self._ask_amount(
            "Withdraw", "Enter amount to withdraw",
            lambda amt: self._after_txn(*self.banking.withdraw(self.user_id, amt))
        )

    def _do_transfer(self):
        def step_amount(to_account):
            to_account = to_account.strip()
            if not to_account:
                return
            self._ask_amount(
                "Transfer", f"Amount to send to {to_account}",
                lambda amt: self._after_txn(
                    *self.banking.transfer(self.user_id, to_account, amt)
                )
            )
        self._ask_text("Transfer", "Enter the destination account number",
                       step_amount)

    def _do_pin_change(self):
        def got_current(current):
            if not self.db.verify_pin(self.user_id, current):
                self._toast("Current PIN is incorrect", ok=False)
                return
            self._ask_pin("Enter New PIN",
                          lambda new: got_new(current, new))

        def got_new(current, new):
            if new == current:
                self._toast("New PIN must differ from the old one", ok=False)
                return
            self._ask_pin("Confirm New PIN",
                          lambda confirm: got_confirm(new, confirm))

        def got_confirm(new, confirm):
            if new != confirm:
                self._toast("New PINs do not match", ok=False)
                return
            if self.db.update_pin(self.user_id, new):
                self._toast("PIN changed successfully", ok=True)
            else:
                self._toast("Could not update PIN", ok=False)

        self._ask_pin("Enter Current PIN", got_current)

    def _do_statement(self):
        self._show_statement()

    def _do_exit(self):
        self._close()

    # ─────────────────────────────────────────────────────────
    # Overlay prompts
    # ─────────────────────────────────────────────────────────

    def _ask_amount(self, title: str, prompt: str, on_ok: Callable[[float], None]):
        panel = self._open_overlay(400, 560, title, prompt)
        self._amt_str = ""

        display = ctk.CTkLabel(
            panel, text=_fmt(0),
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=28, weight="bold"),
            text_color=ACCENT, fg_color=PANEL_DK, corner_radius=10,
            width=300, height=58
        )
        display.pack(pady=(8, 4))

        error = ctk.CTkLabel(
            panel, text="", font=ctk.CTkFont(family=config.FONT_FAMILY, size=10),
            text_color=DANGER
        )
        error.pack()

        def value():
            try:
                return float(self._amt_str) if self._amt_str else 0.0
            except ValueError:
                return 0.0

        def render():
            display.configure(text=_fmt(value()))

        def press(ch):
            if ch == "." and "." in self._amt_str:
                return
            if "." in self._amt_str and ch != "." and \
                    len(self._amt_str.split(".")[1]) >= 2:
                return
            if len(self._amt_str) < 12:
                self._amt_str += ch
                render()

        def backspace():
            self._amt_str = self._amt_str[:-1]
            render()

        def confirm():
            amount = value()
            if amount <= 0:
                error.configure(text="Enter an amount greater than zero")
                return
            self._close_overlay()
            on_ok(round(amount, 2))

        self._build_keypad(
            panel,
            [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], [".", "0", "⌫"]],
            press, backspace
        )
        self._build_confirm_row(panel, confirm)

    def _ask_pin(self, title: str, on_ok: Callable[[str], None]):
        panel = self._open_overlay(360, 500, title, "Use the keypad below")
        self._pin_str = ""
        length = config.PIN_LENGTH

        display = ctk.CTkLabel(
            panel, text="○ " * length,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=ACCENT, fg_color=PANEL_DK, corner_radius=10,
            width=220, height=54
        )
        display.pack(pady=(8, 8))

        def render():
            dots = "● " * len(self._pin_str) + \
                   "○ " * (length - len(self._pin_str))
            display.configure(text=dots.strip())

        def press(digit):
            if len(self._pin_str) < length:
                self._pin_str += digit
                render()
                if len(self._pin_str) == length:
                    self.container.after(120, confirm)

        def backspace():
            self._pin_str = self._pin_str[:-1]
            render()

        def confirm():
            if len(self._pin_str) == length:
                entered = self._pin_str
                self._close_overlay()
                on_ok(entered)

        self._build_keypad(
            panel,
            [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["⌫", "0", "✓"]],
            press, backspace, submit=confirm
        )
        self._build_cancel_only(panel)

    def _ask_text(self, title: str, prompt: str, on_ok: Callable[[str], None]):
        panel = self._open_overlay(420, 300, title, prompt)

        entry = ctk.CTkEntry(
            panel, width=300, height=46, corner_radius=10,
            fg_color=PANEL_DK, border_color=BORDER, text_color=TEXT,
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=16),
            justify="center", placeholder_text="Account number"
        )
        entry.pack(pady=(14, 10))
        entry.focus_set()

        def confirm():
            text = entry.get().strip()
            if not text:
                return
            self._close_overlay()
            on_ok(text)

        entry.bind("<Return>", lambda _e: confirm())
        self._build_confirm_row(panel, confirm)

    # ── Shared overlay widgets ───────────────────────────────

    def _build_keypad(self, panel, layout, press, backspace, submit=None):
        keypad = ctk.CTkFrame(panel, fg_color="transparent")
        keypad.pack(padx=24, pady=(6, 4))
        for r, row in enumerate(layout):
            for c, label in enumerate(row):
                if label == "⌫":
                    cmd, color, hover, tc = backspace, "#2A3A5C", "#3A4A6C", TEXT
                elif label == "✓":
                    cmd, color, hover, tc = (submit or (lambda: None)), ACCENT, ACCENT_HV, "#08251E"
                else:
                    cmd, color, hover, tc = (lambda l=label: press(l)), "#1B2838", "#2A3A5C", TEXT
                ctk.CTkButton(
                    keypad, text=label,
                    font=ctk.CTkFont(family=config.FONT_FAMILY, size=18, weight="bold"),
                    width=80, height=50, corner_radius=10,
                    fg_color=color, hover_color=hover, text_color=tc, command=cmd
                ).grid(row=r, column=c, padx=5, pady=5)

    def _build_confirm_row(self, panel, confirm):
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(8, 18), side="bottom")
        ctk.CTkButton(
            row, text="Cancel",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
            fg_color="#2A3A5C", hover_color="#3A4A6C", text_color=TEXT,
            height=42, corner_radius=10, command=self._close_overlay
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(
            row, text="Confirm",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HV, text_color="#08251E",
            height=42, corner_radius=10, command=confirm
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _build_cancel_only(self, panel):
        ctk.CTkButton(
            panel, text="Cancel",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=12),
            fg_color="#2A3A5C", hover_color="#3A4A6C", text_color=TEXT,
            width=160, height=38, corner_radius=10, command=self._close_overlay
        ).pack(pady=(6, 18), side="bottom")

    # ─────────────────────────────────────────────────────────
    # Statement overlay
    # ─────────────────────────────────────────────────────────

    def _show_statement(self):
        transactions = self.banking.get_mini_statement(self.user_id, limit=15)
        panel = self._open_overlay(560, 620, "Mini Statement",
                                   f"Account {self.account_number}")

        scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=18, pady=(4, 4))

        if not transactions:
            ctk.CTkLabel(
                scroll, text="No transactions yet.",
                font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
                text_color=MUTED
            ).pack(pady=40)
        else:
            for txn in transactions:
                self._statement_row(scroll, txn)

        ctk.CTkButton(
            panel, text="Close",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HV, text_color="#08251E",
            height=42, corner_radius=10, command=self._close_overlay
        ).pack(fill="x", padx=18, pady=(4, 18), side="bottom")

    def _statement_row(self, parent, txn: dict):
        credit_types = {"deposit", "transfer_in"}
        is_credit = txn["txn_type"] in credit_types
        sign = "+" if is_credit else "-"
        amount_color = config.SUCCESS_COLOR if is_credit else DANGER

        row = ctk.CTkFrame(parent, fg_color=PANEL_DK, corner_radius=10)
        row.pack(fill="x", pady=4, padx=2)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", padx=14, pady=10, fill="x", expand=True)

        ctk.CTkLabel(
            left, text=txn["txn_type"].replace("_", " ").title(),
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            text_color=TEXT, anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            left, text=f"{txn.get('category', 'Other')}  •  {txn.get('timestamp', '')}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=10),
            text_color=MUTED, anchor="w"
        ).pack(anchor="w")

        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right", padx=14)
        ctk.CTkLabel(
            right, text=f"{sign} {_fmt(txn['amount'])}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            text_color=amount_color, anchor="e"
        ).pack(anchor="e")
        ctk.CTkLabel(
            right, text=f"Bal: {_fmt(txn['balance_after'])}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=10),
            text_color=MUTED, anchor="e"
        ).pack(anchor="e")

    # ─────────────────────────────────────────────────────────
    # Teardown
    # ─────────────────────────────────────────────────────────

    def _close(self):
        logger.info(f"Banking session ended for {self.user_id}")
        self._close_overlay()
        self.container.destroy()
        if self.on_exit:
            self.on_exit()
