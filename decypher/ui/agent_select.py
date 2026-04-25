"""Agent Select Overlay - Instalock agents and dodge matches."""

import io
import threading
import tkinter as tk
import urllib.request

from decypher.platform.win32_window import apply_no_activate_toolwindow
from decypher.valorant.valorant_api import ValorantLocalAPI

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class _OverlayBase:
    """Shared font and drag behaviour for both overlays."""

    FONT_FAMILY = "Bahnschrift SemiCondensed"

    def on_drag_start(self, event):
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()

    def on_drag_motion(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")


class AgentSelectOverlay(_OverlayBase):

    def __init__(self, api: ValorantLocalAPI = None, master=None):
        self.api = api or ValorantLocalAPI()
        self.master = master
        self.owns_root = master is None
        self.running = True
        self.visible = False
        self._drag_data = {"x": 0, "y": 0}
        self.selected_agent = None
        self.selected_agent_name = None
        self.locked = False
        self.agent_images = {}
        self.agent_buttons = {}
        self.agent_icon_urls = {}
        self.rendered_catalog_source = None
        self.agent_images_loading = False
        self.dodge_confirming = False
        self.window_width = 420

        self.root = tk.Tk() if self.owns_root else tk.Toplevel(master)
        self.root.title("Agent Select")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.overrideredirect(True)
        self.root.configure(bg="#0d1117")
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        if not self.owns_root:
            try:
                self.root.transient(master)
            except Exception:
                pass

        self._position_window()
        self.root.after(100, self._apply_no_activate)

        header = tk.Frame(self.root, bg="#161b22")
        header.pack(fill="x")

        title_row = tk.Frame(header, bg="#161b22")
        title_row.pack(fill="x", padx=12, pady=10)

        title = tk.Label(
            title_row, text="AGENT SELECT",
            font=(self.FONT_FAMILY, 16, "bold"), fg="#58a6ff", bg="#161b22",
        )
        title.pack(side="left")

        close_btn = tk.Label(
            title_row, text="X", font=(self.FONT_FAMILY, 13),
            fg="#8b949e", bg="#161b22", cursor="hand2",
        )
        close_btn.pack(side="right", padx=4)
        close_btn.bind("<Button-1>", lambda e: self.hide())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg="#f85149"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg="#8b949e"))

        for w in [header, title_row, title]:
            w.configure(cursor="fleur")
            w.bind("<Button-1>", self.on_drag_start)
            w.bind("<B1-Motion>", self.on_drag_motion)

        self.agent_frame = tk.Frame(self.root, bg="#0d1117")
        self.agent_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self._refresh_agent_grid()

        self.lock_btn = tk.Button(
            self.root, text="SELECT AN AGENT",
            font=(self.FONT_FAMILY, 13, "bold"),
            fg="#8b949e", bg="#21262d",
            activeforeground="#8b949e", activebackground="#21262d",
            relief="flat", cursor="arrow",
            state="disabled",
            disabledforeground="#8b949e",
        )
        self.lock_btn.pack(fill="x", padx=12, pady=(5, 8))

        self.dodge_frame = tk.Frame(self.root, bg="#0d1117", height=80)
        self.dodge_frame.pack(fill="x", padx=12, pady=(0, 12))
        self.dodge_frame.pack_propagate(False)

        self.dodge_btn = tk.Button(
            self.dodge_frame, text="DODGE",
            font=(self.FONT_FAMILY, 11),
            fg="#f85149", bg="#161b22",
            activeforeground="#f85149", activebackground="#21262d",
            relief="flat", cursor="hand2",
            command=self.show_dodge_confirm,
        )
        self.dodge_btn.pack(fill="x")

        self.confirm_frame = tk.Frame(self.dodge_frame, bg="#0d1117")

        confirm_label = tk.Label(
            self.confirm_frame, text="Are you sure?",
            font=(self.FONT_FAMILY, 11), fg="#8b949e", bg="#0d1117",
        )
        confirm_label.pack(pady=(8, 5))

        btn_row = tk.Frame(self.confirm_frame, bg="#0d1117")
        btn_row.pack()

        yes_btn = tk.Button(
            btn_row, text="Yes",
            font=(self.FONT_FAMILY, 11, "bold"),
            fg="white", bg="#f85149",
            activeforeground="white", activebackground="#da3633",
            relief="flat", cursor="hand2", width=8,
            command=self.do_dodge,
        )
        yes_btn.pack(side="left", padx=4)

        no_btn = tk.Button(
            btn_row, text="No",
            font=(self.FONT_FAMILY, 11),
            fg="#c9d1d9", bg="#21262d",
            activeforeground="#c9d1d9", activebackground="#30363d",
            relief="flat", cursor="hand2", width=8,
            command=self.hide_dodge_confirm,
        )
        no_btn.pack(side="left", padx=4)

        self.root.withdraw()
        self.root.bind("<Escape>", lambda e: self.hide())

    def _apply_no_activate(self):
        apply_no_activate_toolwindow(self.root)

    def _position_window(self):
        self.root.update_idletasks()
        window_height = max(1, self.root.winfo_reqheight())
        screen_width = self.root.winfo_screenwidth()
        x_pos = (screen_width - self.window_width) // 2
        self.root.geometry(f"{self.window_width}x{window_height}+{x_pos}+50")

    def _set_lock_btn(self, state: str, agent_name: str = ""):
        name = agent_name.upper()
        if state == "idle":
            self.lock_btn.configure(
                text="SELECT AN AGENT", fg="#8b949e", bg="#21262d",
                activeforeground="#8b949e", activebackground="#21262d",
                state="disabled", cursor="arrow",
            )
        elif state == "ready":
            self.lock_btn.configure(
                text=f"LOCK IN {name}", fg="white", bg="#238636",
                activeforeground="white", activebackground="#2ea043",
                state="normal", cursor="hand2", command=self.lock_agent,
            )
        elif state == "locking":
            self.lock_btn.configure(
                text="LOCKING...", fg="#8b949e", bg="#21262d",
                state="disabled", cursor="arrow",
            )
        elif state == "locked":
            self.lock_btn.configure(
                text=f"LOCKED IN {name}", fg="#3fb950", bg="#21262d",
                activeforeground="#3fb950", activebackground="#21262d",
                state="disabled", cursor="arrow",
            )

    def _load_agent_images(self):
        self.agent_images_loading = True
        try:
            for agent_name, icon_url in list(self.agent_icon_urls.items()):
                if not self.running:
                    return
                if agent_name in self.agent_images:
                    btn = self.agent_buttons.get(agent_name)
                    if btn:
                        self._queue_button_image_update(btn, self.agent_images[agent_name], agent_name)
                    continue
                try:
                    with urllib.request.urlopen(icon_url, timeout=5) as response:
                        data = response.read()
                    if not self.running:
                        return
                    image = Image.open(io.BytesIO(data)).resize((40, 40), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self.agent_images[agent_name] = photo
                    if agent_name in self.agent_buttons:
                        self._queue_button_image_update(self.agent_buttons[agent_name], photo, agent_name)
                except Exception:
                    pass
        finally:
            self.agent_images_loading = False

    def preload_agent_images(self):
        if not PIL_AVAILABLE or self.agent_images_loading:
            return
        self.agent_images_loading = True
        threading.Thread(target=self._load_agent_images, daemon=True).start()

    def _queue_button_image_update(self, btn, photo, name):
        try:
            self.root.after(0, lambda b=btn, p=photo, n=name: self._update_button_image(b, p, n))
        except Exception:
            pass

    def _update_button_image(self, btn, photo, name):
        if not self.running:
            return
        try:
            btn.configure(image=photo, text="", width=40, height=40, compound="center")
            btn.image = photo  # Keep reference — tkinter GCs unreferenced PhotoImages
        except Exception:
            pass

    def _refresh_agent_grid(self):
        catalog = self.api.get_agent_catalog()
        source = catalog.get("source")
        names = tuple(
            agent.get("name")
            for role in catalog.get("roles", [])
            for agent in role.get("agents", [])
        )
        render_key = (source, names)
        if self.rendered_catalog_source == render_key:
            return

        for widget in self.agent_frame.winfo_children():
            widget.destroy()
        self.agent_buttons.clear()
        self.agent_icon_urls.clear()
        self.rendered_catalog_source = render_key
        self._create_agent_grid(catalog)
        self.preload_agent_images()
        if self.visible:
            self._position_window()

    def _create_agent_grid(self, catalog: dict):
        cat_colors = {
            "Duelists":   "#f85149",
            "Initiators": "#3fb950",
            "Controllers":"#a78bfa",
            "Sentinels":  "#58a6ff",
        }

        for role in catalog.get("roles", []):
            cat_name = role.get("name", "Agents")
            agents = role.get("agents", [])
            if not agents:
                continue

            tk.Label(
                self.agent_frame, text=cat_name.upper(),
                font=(self.FONT_FAMILY, 10, "bold"),
                fg=cat_colors.get(cat_name, "#8b949e"),
                bg="#0d1117", anchor="w",
            ).pack(fill="x", pady=(6, 3))

            row = tk.Frame(self.agent_frame, bg="#0d1117")
            row.pack(fill="x")

            for agent in agents:
                agent_name = agent.get("name")
                if not agent_name or not agent.get("uuid"):
                    continue

                self.agent_icon_urls[agent_name] = agent.get("icon_url")
                btn = tk.Label(
                    row, text=agent_name,
                    font=(self.FONT_FAMILY, 10),
                    fg="#c9d1d9", bg="#161b22",
                    width=6, height=2, cursor="hand2",
                    relief="flat", borderwidth=2,
                )
                btn.pack(side="left", padx=2, pady=2)

                self.agent_buttons[agent_name] = btn
                if agent_name in self.agent_images:
                    self._update_button_image(btn, self.agent_images[agent_name], agent_name)

                btn.bind("<Enter>", lambda e, b=btn, a=agent_name: self._on_agent_hover(b, a, True))
                btn.bind("<Leave>", lambda e, b=btn, a=agent_name: self._on_agent_hover(b, a, False))
                btn.bind("<Button-1>", lambda e, a=agent_name: self.select_agent(a))

    def _on_agent_hover(self, btn, agent, entering):
        if self.locked or agent == self.selected_agent_name:
            return
        btn.configure(bg="#21262d" if entering else "#161b22")

    def _clear_selected_agent_button(self):
        if self.selected_agent_name and self.selected_agent_name in self.agent_buttons:
            self.agent_buttons[self.selected_agent_name].configure(bg="#161b22", relief="flat")

    def _set_selected_agent(self, agent_name: str, agent_id: str | None = None):
        self._clear_selected_agent_button()
        self.selected_agent_name = agent_name
        self.selected_agent = agent_id or self.api.get_agent_uuid(agent_name)
        if not self.selected_agent:
            return False
        btn = self.agent_buttons.get(agent_name)
        if btn:
            btn.configure(bg="#238636", relief="solid")
        return True

    def select_agent(self, agent_name: str):
        if self.locked or not self._set_selected_agent(agent_name):
            return
        self._set_lock_btn("ready", agent_name)

    def lock_agent(self):
        if self.locked or not self.selected_agent:
            return
        agent_name = self.selected_agent_name
        agent_id = self.selected_agent
        self._set_lock_btn("locking")

        def do_lock():
            if self.api.lock_agent(agent_id):
                self.locked = True
                self.root.after(0, lambda: self._set_lock_btn("locked", agent_name))
            else:
                self.root.after(0, lambda: self._set_lock_btn("ready", agent_name))

        threading.Thread(target=do_lock, daemon=True).start()

    def sync_from_game(self, agent_id: str | None, selection_state: str | None = None):
        """Reflect agent changes made through Valorant's native pregame UI."""
        if not self.running or not agent_id:
            return

        agent_name = self.api.get_agent_name(agent_id)
        if not agent_name:
            return

        self._refresh_agent_grid()
        normalized_state = str(selection_state or "").strip().lower()
        is_locked = normalized_state == "locked"
        if self.locked and self.selected_agent == agent_id and not is_locked:
            is_locked = True

        if (
            self.selected_agent == agent_id
            and self.locked == is_locked
            and self.selected_agent_name == agent_name
        ):
            return

        if not self._set_selected_agent(agent_name, agent_id):
            return

        self.locked = is_locked
        self._set_lock_btn("locked" if is_locked else "ready", agent_name)

    def show_dodge_confirm(self):
        self.dodge_confirming = True
        self.dodge_btn.pack_forget()
        self.confirm_frame.pack(fill="x")

    def hide_dodge_confirm(self):
        self.dodge_confirming = False
        self.confirm_frame.pack_forget()
        self.dodge_btn.pack(fill="x")

    def do_dodge(self):
        def dodge():
            if self.api.dodge_match():
                self.root.after(0, self.hide)
            else:
                self.root.after(0, self.hide_dodge_confirm)
        threading.Thread(target=dodge, daemon=True).start()

    def show(self):
        self._refresh_agent_grid()
        self.locked = False
        self.selected_agent = None
        self.selected_agent_name = None
        self.dodge_confirming = False
        self._set_lock_btn("idle")
        self.hide_dodge_confirm()
        for btn in self.agent_buttons.values():
            btn.configure(bg="#161b22", relief="flat")
        self._position_window()
        self.visible = True
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(50, self._apply_no_activate)

    def hide(self):
        if self.visible:
            self.visible = False
            self.root.withdraw()

    def close(self):
        self.running = False
        if self.owns_root:
            self.root.quit()
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    app = AgentSelectOverlay()
    app.show()
    app.root.mainloop()


if __name__ == "__main__":
    main()
