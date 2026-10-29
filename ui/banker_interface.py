"""
Banker Interface - Staff console for branch operations.

A standalone window (launched with `python main.py --banker`) that gives bank
staff a tile-based dashboard for the administrative CLI operations:

    Enroll User        → runs `main.py --enroll` in a dedicated console
                          (interactive: webcam capture + typed details)
    Re-encode Dataset  → rebuilds face encodings, log streamed in-window
    Registered Users   → enrolled-customer table rendered in the UI
    System Self-Test   → component diagnostics, log streamed in-window
    Serial Ports       → detect ESP32 ports and pick one (--port override)
    Exit               → close the console

Styled identically to the customer ATM dashboard (ui/banking_interface.py):
same palette, icon chips, card tiles and in-window overlays.
"""

import datetime
import os
import queue
import subprocess
import sys
import threading
from typing import Callable, Optional

import customtkinter as ctk

import config
from database.db_manager import DatabaseManager
from ui import window_utils
from utils.logger import logger

# Shared design system — palette + icon renderer from the ATM dashboard.
from ui.banking_interface import (
    _blend, _draw_icon,
    BG, CARD, CARD_HV, ACCENT, ACCENT_HV, DANGER, TEXT, MUTED,
    HEADER_BG, PANEL_DK, BORDER, PANEL_CARD,
    COL_WITHDRAW, COL_DEPOSIT, COL_TRANSFER, COL_STATEMENT, COL_PIN, COL_EXIT,
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DONE = object()      # sentinel closing the console stream


class _QueueWriter:
    """File-like stdout shim that funnels prints into a queue."""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class BankerInterface:
    """Staff-facing console window with branch operation tiles."""

    def __init__(self):
        ctk.set_appearance_mode(config.THEME_MODE)
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title(f"{config.BRAND_NAME} - Banker Console")
        window_utils.set_brand_icon(self.root)
        self.root.geometry(f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")
        self.root.minsize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.root.configure(fg_color=BG)
        # Start maximized; the geometry above stays the restore size.
        window_utils.maximize(self.root)

        self.db = DatabaseManager()
        self._icon_cache = {}
        self._overlay = None
        self._toast_job = None
        self._busy = False                 # one operation at a time
        self.port_override: Optional[str] = None

        self.container = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        self.container.pack(fill="both", expand=True)

        self._build_header()
        self._build_grid()
        self._build_footer()

    # ─────────────────────────────────────────────────────────
    # UI construction (mirrors the ATM dashboard design)
    # ─────────────────────────────────────────────────────────

    def _icon_image(self, name, color, px=48):
        key = (name, color, px)
        if key not in self._icon_cache:
            pil = _draw_icon(name, color, px)
            self._icon_cache[key] = ctk.CTkImage(
                light_image=pil, dark_image=pil, size=(px, px)
            )
        return self._icon_cache[key]

    def _build_header(self):
        header = ctk.CTkFrame(self.container, height=120, fg_color=HEADER_BG,
                              corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Left: NoryvX logo lockup + console subtitle
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=36, pady=20)

        text_col = ctk.CTkFrame(left, fg_color="transparent")
        text_col.pack(side="left")

        window_utils.brand_header(text_col, px=52, name_size=30).pack(anchor="w")

        ctk.CTkLabel(
            text_col, text="Banker Console  •  Branch operations — enrollment, "
                           "diagnostics & maintenance",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
            text_color=MUTED, anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        # Right: registered-users card + clock
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=36, pady=18)

        count_card = ctk.CTkFrame(right, fg_color=CARD, corner_radius=14,
                                  border_width=1, border_color=BORDER)
        count_card.pack(anchor="e")

        ctk.CTkLabel(
            count_card, text="REGISTERED USERS",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=10, weight="bold"),
            text_color=MUTED
        ).pack(padx=24, pady=(12, 0), anchor="e")

        self.count_label = ctk.CTkLabel(
            count_card, text="—",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=26, weight="bold"),
            text_color=ACCENT
        )
        self.count_label.pack(padx=24, pady=(0, 12), anchor="e")

        self.clock_label = ctk.CTkLabel(
            right, text="",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11),
            text_color=MUTED
        )
        self.clock_label.pack(anchor="e", pady=(8, 0))

        ctk.CTkFrame(self.container, height=2, fg_color=BORDER).pack(fill="x")

        self._refresh_count()
        self._tick_clock()

    def _build_grid(self):
        wrap = ctk.CTkFrame(self.container, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=28, pady=24)

        for c in range(3):
            wrap.grid_columnconfigure(c, weight=1, uniform="col")
        for r in range(2):
            wrap.grid_rowconfigure(r, weight=1, uniform="row")

        tiles = [
            ("enroll", "Enroll User", "Register a new customer",
             self._do_enroll, COL_WITHDRAW),
            ("encode", "Re-encode Dataset", "Rebuild face encodings",
             self._do_encode, COL_DEPOSIT),
            ("users", "Registered Users", "View enrolled customers",
             self._do_users, COL_TRANSFER),
            ("selftest", "System Self-Test", "Verify all components",
             self._do_selftest, COL_STATEMENT),
            ("ports", "Serial Ports", "Detect & select ESP32 port",
             self._do_ports, COL_PIN),
            ("exit", "Exit", "Close banker console",
             self._do_exit, COL_EXIT),
        ]

        for idx, (icon, title, subtitle, command, color) in enumerate(tiles):
            row, col = divmod(idx, 3)
            tile = self._make_tile(wrap, icon, title, subtitle, command, color)
            tile.grid(row=row, column=col, sticky="nsew", padx=12, pady=12)

    def _make_tile(self, parent, icon_name, title, subtitle, command, color):
        """Same professional card treatment as the ATM dashboard."""
        base = CARD
        hover = CARD_HV
        chip_bg = _blend(CARD, color, 0.18)
        chip_bg_hv = _blend(CARD, color, 0.30)

        tile = ctk.CTkFrame(parent, fg_color=base, corner_radius=18,
                            border_width=1, border_color=BORDER)

        inner = ctk.CTkFrame(tile, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=26, pady=24)

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

        def on_click(_=None):
            if not self._busy:
                command()

        for widget in (tile, inner, top, chip, icon_label, chevron,
                       bottom, title_label, sub_label):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", on_click)
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)

        return tile

    def _build_footer(self):
        footer = ctk.CTkFrame(self.container, height=42, fg_color=HEADER_BG,
                              corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        if config.SOFTWARE_FINGERPRINT:
            mode_text = "SOFTWARE FP"
        elif config.SIMULATION_MODE:
            mode_text = "SIMULATION"
        else:
            mode_text = "HARDWARE"
        ctk.CTkLabel(
            footer, text=f"Mode  •  {mode_text}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11),
            text_color=MUTED
        ).pack(side="left", padx=24)

        self.status_label = ctk.CTkLabel(
            footer, text="",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=12, weight="bold"),
            text_color=ACCENT
        )
        self.status_label.pack(side="left", expand=True)

        self.port_label = ctk.CTkLabel(
            footer, text=f"Serial  •  {config.SERIAL_PORT}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11),
            text_color=MUTED
        )
        self.port_label.pack(side="right", padx=24)

    # ─────────────────────────────────────────────────────────
    # Live updates
    # ─────────────────────────────────────────────────────────

    def _refresh_count(self):
        try:
            self.count_label.configure(text=str(len(self.db.get_all_users())))
        except Exception:
            self.count_label.configure(text="—")
        # Keep the KPI fresh (picks up enrollments done in the console window)
        self.root.after(15000, self._refresh_count)

    def _tick_clock(self):
        now = datetime.datetime.now().strftime("%d %b %Y  |  %H:%M:%S")
        self.clock_label.configure(text=now)
        self.root.after(1000, self._tick_clock)

    def _toast(self, message: str, ok: bool = True):
        color = ACCENT if ok else DANGER
        self.status_label.configure(text=message, text_color=color)
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
        self._toast_job = self.root.after(
            5000, lambda: self.status_label.configure(text="")
        )

    # ─────────────────────────────────────────────────────────
    # In-window overlay (same pattern as the ATM dashboard)
    # ─────────────────────────────────────────────────────────

    def _open_overlay(self, width: int, height: int, title: str,
                      subtitle: str = ""):
        self._close_overlay()
        backdrop = ctk.CTkFrame(self.container, fg_color="#05070D",
                                corner_radius=0)
        backdrop.place(relx=0, rely=0, relwidth=1, relheight=1)
        backdrop.bind("<Button-1>", lambda _e: None)

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

    def _close_button(self, panel, text="Close", command=None):
        btn = ctk.CTkButton(
            panel, text=text,
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HV, text_color="#08251E",
            height=42, corner_radius=10,
            command=command or self._close_overlay
        )
        btn.pack(fill="x", padx=18, pady=(6, 18), side="bottom")
        return btn

    # ─────────────────────────────────────────────────────────
    # Streamed console operations (encode / self-test)
    # ─────────────────────────────────────────────────────────

    def _run_streamed(self, title: str, subtitle: str, target: Callable):
        """Run `target` in a thread, streaming its prints into an overlay."""
        panel = self._open_overlay(760, 600, title, subtitle)
        self._busy = True

        console = ctk.CTkTextbox(
            panel, fg_color=PANEL_DK, text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=10, border_width=1, border_color=BORDER,
            wrap="word"
        )
        console.pack(fill="both", expand=True, padx=18, pady=(6, 4))
        console.configure(state="disabled")

        close_btn = self._close_button(panel, text="Running…")
        close_btn.configure(state="disabled", fg_color="#2A3A5C",
                            text_color=MUTED)

        q: queue.Queue = queue.Queue()

        def worker():
            writer = _QueueWriter(q)
            old_stdout = sys.stdout
            sys.stdout = writer
            try:
                target()
            except Exception as e:          # never let the thread die silent
                print(f"\nERROR: {e}")
            finally:
                sys.stdout = old_stdout
                q.put(_DONE)

        def drain():
            finished = False
            chunks = []
            while True:
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    break
                if item is _DONE:
                    finished = True
                    break
                chunks.append(item)
            if chunks and console.winfo_exists():
                console.configure(state="normal")
                console.insert("end", "".join(chunks))
                console.see("end")
                console.configure(state="disabled")
            if finished:
                self._busy = False
                if close_btn.winfo_exists():
                    close_btn.configure(state="normal", text="Close",
                                        fg_color=ACCENT, text_color="#08251E")
                self._toast(f"{title} finished")
            else:
                self.root.after(80, drain)

        threading.Thread(target=worker, daemon=True).start()
        drain()

    # ─────────────────────────────────────────────────────────
    # Tile actions
    # ─────────────────────────────────────────────────────────

    def _do_enroll(self):
        """Confirm, then launch the interactive enrollment in its own console."""
        panel = self._open_overlay(480, 320, "Enroll New User",
                                   "Interactive enrollment")

        ctk.CTkLabel(
            panel,
            text=("Enrollment opens in a dedicated console window:\n\n"
                  "•  customer details & PIN are typed there\n"
                  "•  the webcam window captures 20 face images\n"
                  "•  fingerprint enrollment follows on-screen steps\n\n"
                  "This console stays available meanwhile."),
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
            text_color=MUTED, justify="left"
        ).pack(padx=28, pady=(10, 0), anchor="w")

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(8, 18), side="bottom")
        ctk.CTkButton(
            row, text="Cancel",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
            fg_color="#2A3A5C", hover_color="#3A4A6C", text_color=TEXT,
            height=42, corner_radius=10, command=self._close_overlay
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(
            row, text="Launch Enrollment",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HV, text_color="#08251E",
            height=42, corner_radius=10, command=self._launch_enroll
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _launch_enroll(self):
        self._close_overlay()
        cmd = [sys.executable, os.path.join(_PROJECT_ROOT, "main.py"), "--enroll"]
        if self.port_override:
            cmd += ["--port", self.port_override]
        try:
            subprocess.Popen(cmd, cwd=_PROJECT_ROOT,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
            logger.system_event("Banker Console", "Enrollment console launched")
            self._toast("Enrollment console opened — follow the steps there")
        except Exception as e:
            logger.error(f"Failed to launch enrollment: {e}")
            self._toast("Could not open enrollment console", ok=False)

    def _do_encode(self):
        def encode_job():
            from face_recognition_module.face_encoder import FaceEncoder
            print("Re-encoding face dataset…\n")
            encoder = FaceEncoder()
            if not encoder.encode_dataset():
                print("\nFace encoding FAILED — check the dataset directory.")
                return
            print("\nFace encoding complete. Updating database records…")
            for user_id in encoder.known_encodings:
                avg = encoder.get_average_encoding(user_id)
                if avg is not None:
                    self.db.update_face_encoding(user_id, avg)
                    print(f"  updated  {user_id}")
            print("\nAll encodings synced to the database.")

        self._run_streamed("Re-encode Dataset",
                           "Rebuilding face encodings from the image dataset",
                           encode_job)

    def _do_selftest(self):
        def selftest_job():
            import main as cli               # reuse the exact CLI self-test
            cli.run_self_test()

        self._run_streamed("System Self-Test",
                           "Database · encodings · webcam · fingerprint · dataset",
                           selftest_job)

    def _do_users(self):
        users = self.db.get_all_users()
        panel = self._open_overlay(820, 660, "Registered Users",
                                   f"{len(users)} enrolled customer(s)")

        scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=18, pady=(4, 4))

        if not users:
            ctk.CTkLabel(
                scroll, text="No users registered yet.",
                font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
                text_color=MUTED
            ).pack(pady=40)
        else:
            for user in users:
                accounts = self.db.get_accounts_by_user(user["user_id"])
                account = accounts[0] if accounts else None
                card = None
                if account:
                    cards = self.db.get_cards_by_account(account["account_id"])
                    card = cards[0] if cards else None
                self._user_row(scroll, user, account, card)

        self._close_button(panel)

    @staticmethod
    def _group_card(number) -> str:
        """1234567890123456 → XXXX XXXX XXXX 3456 (last 4 digits visible)"""
        s = str(number or "")
        if s:
            s = "X" * max(len(s) - 4, 0) + s[-4:]
        return " ".join(s[i:i + 4] for i in range(0, len(s), 4)) or "N/A"

    @staticmethod
    def _mask_balance(balance: float) -> str:
        """25050.0 → '*****' (one star per digit of the integer amount)."""
        return "*" * len(str(int(balance)))

    def _detail_cell(self, parent, label: str, value: str,
                     value_color=None, mono=False, sub=None, sub_color=None):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            cell, text=label.upper(),
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=9, weight="bold"),
            text_color=_blend(PANEL_DK, MUTED, 0.75), anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            cell, text=value,
            font=(ctk.CTkFont(family="Consolas", size=13, weight="bold")
                  if mono else
                  ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold")),
            text_color=value_color or TEXT, anchor="w"
        ).pack(anchor="w")
        if sub:
            ctk.CTkLabel(
                cell, text=sub,
                font=ctk.CTkFont(family=config.FONT_FAMILY, size=10),
                text_color=sub_color or MUTED, anchor="w"
            ).pack(anchor="w")
        return cell

    def _user_row(self, parent, user: dict, account: Optional[dict] = None,
                  card: Optional[dict] = None):
        row = ctk.CTkFrame(parent, fg_color=PANEL_DK, corner_radius=10)
        row.pack(fill="x", pady=4, padx=2)

        # ── Top strip: avatar · name/id · FP ID · Remove ─────────
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))

        name = user.get("name") or "?"
        parts = name.split()
        initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()
        avatar = ctk.CTkFrame(top, width=40, height=40, corner_radius=20,
                              fg_color=_blend(PANEL_DK, COL_TRANSFER, 0.25))
        avatar.pack(side="left", padx=(0, 10))
        avatar.pack_propagate(False)
        ctk.CTkLabel(
            avatar, text=initials, fg_color="transparent",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            text_color=COL_TRANSFER
        ).pack(expand=True)

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            left, text=name,
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            text_color=TEXT, anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            left, text=f"{user['user_id']}  •  enrolled {user.get('created_at', '')}",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=10),
            text_color=MUTED, anchor="w"
        ).pack(anchor="w")

        ctk.CTkButton(
            top, text="Remove",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11, weight="bold"),
            fg_color="transparent", hover_color="#2A1420",
            text_color=DANGER, border_width=1, border_color=_blend(PANEL_DK, DANGER, 0.45),
            width=74, height=28, corner_radius=8,
            command=lambda u=user: self._confirm_remove(u)
        ).pack(side="right", padx=(6, 0))

        fp = user.get("fingerprint_id")
        ctk.CTkLabel(
            top, text=f"FP ID {fp}" if fp is not None else "no FP",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11, weight="bold"),
            text_color=ACCENT if fp is not None else MUTED
        ).pack(side="right", padx=6)

        # ── Divider ──────────────────────────────────────────────
        ctk.CTkFrame(row, height=1, fg_color=_blend(PANEL_DK, BORDER, 0.9)
                     ).pack(fill="x", padx=12, pady=(8, 6))

        # ── Details strip: account · balance · card ──────────────
        detail = ctk.CTkFrame(row, fg_color="transparent")
        detail.pack(fill="x", padx=12, pady=(0, 10))

        if account:
            self._detail_cell(
                detail, "Account",
                str(account.get("account_number") or "N/A"), mono=True,
                sub=str(account.get("account_type") or "").title() or None
            )
            self._detail_cell(
                detail, "Balance",
                self._mask_balance(float(account.get("balance") or 0)),
                value_color=ACCENT, sub="available"
            )
        else:
            self._detail_cell(detail, "Account", "N/A",
                              value_color=MUTED, sub="no account on file")

        if card:
            status = str(card.get("card_status") or "").lower()
            status_color = (ACCENT if status == "active"
                            else DANGER if status in ("blocked", "expired")
                            else MUTED)
            self._detail_cell(
                detail, "Card",
                self._group_card(card.get("card_number")), mono=True,
                sub=f"exp {card.get('expiry_date', '—')}  •  "
                    f"{(status or 'unknown').upper()}",
                sub_color=status_color
            )
        else:
            self._detail_cell(detail, "Card", "N/A",
                              value_color=MUTED, sub="no card issued")

    def _confirm_remove(self, user: dict):
        """Ask for confirmation, then soft-delete the user by user id."""
        name = user.get("name") or "?"
        user_id = user["user_id"]
        panel = self._open_overlay(460, 300, "Remove User",
                                   "This deactivates the customer's access")

        ctk.CTkLabel(
            panel,
            text=(f"Remove  {name}  ({user_id})?\n\n"
                  "•  the user can no longer authenticate at the ATM\n"
                  "•  face images and encodings are permanently deleted\n"
                  "•  the fingerprint template is erased from the sensor\n"
                  "•  accounts and transaction history are preserved\n"
                  "•  re-enrollment is required to restore access"),
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
            text_color=MUTED, justify="left"
        ).pack(padx=28, pady=(10, 0), anchor="w")

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(8, 18), side="bottom")
        ctk.CTkButton(
            row, text="Cancel",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
            fg_color="#2A3A5C", hover_color="#3A4A6C", text_color=TEXT,
            height=42, corner_radius=10,
            command=self._do_users            # back to the list
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(
            row, text="Remove User",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=13, weight="bold"),
            fg_color=DANGER, hover_color="#C0392B", text_color="white",
            height=42, corner_radius=10,
            command=lambda: self._remove_user(user_id, name,
                                              user.get("fingerprint_id"))
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _remove_user(self, user_id: str, name: str,
                     fingerprint_id: Optional[int] = None):
        if self.db.delete_user(user_id):
            from face_recognition_module.face_encoder import FaceEncoder
            if not FaceEncoder().remove_user_data(user_id):
                self._toast(f"Face data cleanup incomplete for {user_id}",
                            ok=False)
            if fingerprint_id is not None:
                threading.Thread(
                    target=self._erase_fingerprint_template,
                    args=(user_id, fingerprint_id), daemon=True
                ).start()
            logger.system_event("Banker Console", f"User removed: {user_id}")
            self.count_label.configure(text=str(len(self.db.get_all_users())))
            self._do_users()                  # refreshed list
            self._toast(f"{name} ({user_id}) removed")
        else:
            self._toast(f"Could not remove {user_id}", ok=False)

    def _erase_fingerprint_template(self, user_id: str, fingerprint_id: int):
        """Erase the user's template from the R307S (background thread)."""
        from fingerprint_module.serial_handler import SerialHandler
        handler = SerialHandler(port=self.port_override)
        ok = False
        try:
            if handler.connect():
                ok = handler.request_deletion(fingerprint_id)
                handler.disconnect()
        except Exception as e:
            logger.error(f"Sensor cleanup failed for {user_id}: {e}")
        if ok:
            logger.system_event(
                "Banker Console",
                f"Fingerprint template {fingerprint_id} erased ({user_id})")
            msg, good = f"Fingerprint template erased from sensor", True
        else:
            msg = (f"Could not erase fingerprint {fingerprint_id} from "
                   "sensor — check the ESP32 connection")
            good = False
        self.root.after(0, lambda: self._toast(msg, ok=good))

    def _do_ports(self):
        from fingerprint_module.serial_handler import SerialHandler
        ports = SerialHandler().list_available_ports()
        panel = self._open_overlay(620, 520, "Serial Ports",
                                   "Select the port the ESP32 is connected to")

        scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=18, pady=(4, 4))

        if not ports:
            ctk.CTkLabel(
                scroll, text="No serial ports found.\nConnect the ESP32 and try again.",
                font=ctk.CTkFont(family=config.FONT_FAMILY, size=13),
                text_color=MUTED, justify="center"
            ).pack(pady=40)
        else:
            for p in ports:
                self._port_row(scroll, p)

        self._close_button(panel)

    def _port_row(self, parent, port: dict):
        device = port["device"]
        selected = device == (self.port_override or config.SERIAL_PORT)

        row = ctk.CTkFrame(parent, fg_color=PANEL_DK, corner_radius=10,
                           border_width=1,
                           border_color=ACCENT if selected else PANEL_DK)
        row.pack(fill="x", pady=4, padx=2)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", padx=14, pady=10, fill="x", expand=True)
        ctk.CTkLabel(
            left, text=device,
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color=TEXT, anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            left, text=port.get("description", ""),
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=11),
            text_color=MUTED, anchor="w"
        ).pack(anchor="w")

        ctk.CTkButton(
            row, text="In use" if selected else "Use",
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=12, weight="bold"),
            fg_color=_blend(PANEL_DK, ACCENT, 0.25) if selected else ACCENT,
            hover_color=ACCENT_HV,
            text_color=ACCENT if selected else "#08251E",
            width=86, height=32, corner_radius=8,
            state="disabled" if selected else "normal",
            command=lambda d=device: self._select_port(d)
        ).pack(side="right", padx=12)

    def _select_port(self, device: str):
        self.port_override = device
        config.SERIAL_PORT = device        # in-process ops use it immediately
        self.port_label.configure(text=f"Serial  •  {device}")
        logger.info(f"Banker console: serial port set to {device}")
        self._close_overlay()
        self._toast(f"Serial port set to {device}")

    def _do_exit(self):
        self.root.destroy()

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def run(self):
        logger.system_event("Banker Console", "Starting staff UI…")
        self.root.mainloop()
