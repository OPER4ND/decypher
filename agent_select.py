"""
Agent Select Overlay - Instalock agents and dodge matches
Shows on second monitor if available, otherwise main screen
"""

import tkinter as tk
import threading
import time
import urllib.request
import io
from valorant_api import ValorantLocalAPI

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import ctypes
    WINDOWS = True
except:
    WINDOWS = False


class AgentSelectOverlay:
    def __init__(self, api: ValorantLocalAPI = None):
        self.api = api or ValorantLocalAPI()
        self.running = True
        self.visible = False
        self._drag_data = {"x": 0, "y": 0}
        self.selected_agent = None
        self.selected_agent_name = None
        self.locked = False
        self.agent_images = {}
        self.agent_buttons = {}
        self.dodge_confirming = False

        # Create window
        self.root = tk.Tk()
        self.root.title("Agent Select")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.overrideredirect(True)
        self.root.configure(bg="#0d1117")

        self._position_window()

        # === HEADER ===
        header = tk.Frame(self.root, bg="#161b22")
        header.pack(fill="x")

        title_row = tk.Frame(header, bg="#161b22")
        title_row.pack(fill="x", padx=12, pady=10)

        title = tk.Label(
            title_row, text="AGENT SELECT",
            font=("Segoe UI", 12, "bold"), fg="#58a6ff", bg="#161b22"
        )
        title.pack(side="left")

        close_btn = tk.Label(
            title_row, text="✕", font=("Segoe UI", 11),
            fg="#8b949e", bg="#161b22", cursor="hand2"
        )
        close_btn.pack(side="right", padx=4)
        close_btn.bind("<Button-1>", lambda e: self.hide())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg="#f85149"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg="#8b949e"))

        # Make header draggable
        for w in [header, title_row, title]:
            w.configure(cursor="fleur")
            w.bind("<Button-1>", self.on_drag_start)
            w.bind("<B1-Motion>", self.on_drag_motion)

        # === AGENT GRID ===
        self.agent_frame = tk.Frame(self.root, bg="#0d1117")
        self.agent_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self._create_agent_grid()

        # === LOCK IN BUTTON ===
        self.lock_btn = tk.Button(
            self.root, text="SELECT AN AGENT",
            font=("Segoe UI", 11, "bold"),
            fg="#8b949e", bg="#21262d",
            activeforeground="#8b949e", activebackground="#21262d",
            relief="flat", cursor="arrow",
            state="disabled",
            disabledforeground="#8b949e"
        )
        self.lock_btn.pack(fill="x", padx=12, pady=(5, 8))

        # === DODGE SECTION (with reserved space for confirmation) ===
        self.dodge_frame = tk.Frame(self.root, bg="#0d1117", height=80)
        self.dodge_frame.pack(fill="x", padx=12, pady=(0, 12))
        self.dodge_frame.pack_propagate(False)  # Fixed height, won't resize

        self.dodge_btn = tk.Button(
            self.dodge_frame, text="DODGE",
            font=("Segoe UI", 9),
            fg="#f85149", bg="#161b22",
            activeforeground="#f85149", activebackground="#21262d",
            relief="flat", cursor="hand2",
            command=self.show_dodge_confirm
        )
        self.dodge_btn.pack(fill="x")

        # Confirm area (hidden initially)
        self.confirm_frame = tk.Frame(self.dodge_frame, bg="#0d1117")

        confirm_label = tk.Label(
            self.confirm_frame, text="Are you sure?",
            font=("Segoe UI", 9), fg="#8b949e", bg="#0d1117"
        )
        confirm_label.pack(pady=(8, 5))

        btn_row = tk.Frame(self.confirm_frame, bg="#0d1117")
        btn_row.pack()

        yes_btn = tk.Button(
            btn_row, text="Yes",
            font=("Segoe UI", 9, "bold"),
            fg="white", bg="#f85149",
            activeforeground="white", activebackground="#da3633",
            relief="flat", cursor="hand2", width=8,
            command=self.do_dodge
        )
        yes_btn.pack(side="left", padx=4)

        no_btn = tk.Button(
            btn_row, text="No",
            font=("Segoe UI", 9),
            fg="#c9d1d9", bg="#21262d",
            activeforeground="#c9d1d9", activebackground="#30363d",
            relief="flat", cursor="hand2", width=8,
            command=self.hide_dodge_confirm
        )
        no_btn.pack(side="left", padx=4)

        # Start hidden
        self.root.withdraw()

        # Load agent images in background
        if PIL_AVAILABLE:
            threading.Thread(target=self._load_agent_images, daemon=True).start()

        # Hotkeys
        self.root.bind("<Escape>", lambda e: self.hide())

    def _position_window(self):
        """Position on second monitor center, or main monitor top-center (left of team list)"""
        window_width = 420
        window_height = 520
        team_list_width = 340  # Account for team list overlay on right

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        try:
            if WINDOWS:
                user32 = ctypes.windll.user32
                virtual_width = user32.GetSystemMetrics(78)
                virtual_left = user32.GetSystemMetrics(76)

                if virtual_width > screen_width:
                    # Second monitor exists - center on it
                    if virtual_left < 0:
                        # Second monitor is on the left
                        second_mon_width = -virtual_left
                        x_pos = virtual_left + (second_mon_width - window_width) // 2
                    else:
                        # Second monitor is on the right
                        second_mon_width = virtual_width - screen_width
                        x_pos = screen_width + (second_mon_width - window_width) // 2
                    y_pos = (screen_height - window_height) // 2
                else:
                    # Single monitor - top center, shifted left to avoid team list
                    x_pos = (screen_width - window_width - team_list_width) // 2
                    y_pos = 50
            else:
                x_pos = (screen_width - window_width - team_list_width) // 2
                y_pos = 50
        except:
            x_pos = (screen_width - window_width - team_list_width) // 2
            y_pos = 50

        self.root.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")

    def _load_agent_images(self):
        """Load agent images from valorant-api.com"""
        for agent_name, agent_id in self.api.AGENTS.items():
            try:
                url = f"https://media.valorant-api.com/agents/{agent_id}/displayicon.png"
                with urllib.request.urlopen(url, timeout=5) as response:
                    data = response.read()
                    image = Image.open(io.BytesIO(data))
                    image = image.resize((40, 40), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self.agent_images[agent_name] = photo

                    # Update button if it exists
                    if agent_name in self.agent_buttons:
                        btn = self.agent_buttons[agent_name]
                        self.root.after(0, lambda b=btn, p=photo, n=agent_name: self._update_button_image(b, p, n))
            except Exception as e:
                pass

    def _update_button_image(self, btn, photo, name):
        """Update button with loaded image"""
        try:
            btn.configure(image=photo, text="", width=40, height=40, compound="center")
            btn.image = photo  # Keep reference
        except:
            pass

    def _create_agent_grid(self):
        """Create clickable agent grid"""
        categories = {
            "Duelists": ["Jett", "Reyna", "Phoenix", "Raze", "Yoru", "Neon", "Iso", "Waylay"],
            "Initiators": ["Sova", "Breach", "Skye", "KAY/O", "Fade", "Gekko", "Tejo"],
            "Controllers": ["Brimstone", "Omen", "Viper", "Astra", "Harbor", "Clove", "Miks"],
            "Sentinels": ["Sage", "Cypher", "Killjoy", "Chamber", "Deadlock", "Vyse", "Veto"],
        }

        cat_colors = {
            "Duelists": "#f85149",
            "Initiators": "#3fb950",
            "Controllers": "#a78bfa",
            "Sentinels": "#58a6ff",
        }

        for cat_name, agents in categories.items():
            cat_label = tk.Label(
                self.agent_frame, text=cat_name.upper(),
                font=("Segoe UI", 8, "bold"),
                fg=cat_colors.get(cat_name, "#8b949e"),
                bg="#0d1117", anchor="w"
            )
            cat_label.pack(fill="x", pady=(6, 3))

            row = tk.Frame(self.agent_frame, bg="#0d1117")
            row.pack(fill="x")

            for agent in agents:
                if agent in self.api.AGENTS:
                    btn = tk.Label(
                        row, text=agent,
                        font=("Segoe UI", 8),
                        fg="#c9d1d9", bg="#161b22",
                        width=6, height=2, cursor="hand2",
                        relief="flat", borderwidth=2
                    )
                    btn.pack(side="left", padx=2, pady=2)

                    self.agent_buttons[agent] = btn

                    # Hover effect
                    btn.bind("<Enter>", lambda e, b=btn, a=agent: self._on_agent_hover(b, a, True))
                    btn.bind("<Leave>", lambda e, b=btn, a=agent: self._on_agent_hover(b, a, False))
                    btn.bind("<Button-1>", lambda e, a=agent: self.select_agent(a))

    def _on_agent_hover(self, btn, agent, entering):
        """Handle hover effect"""
        if self.locked:
            return
        if agent == self.selected_agent_name:
            return  # Don't change selected agent's appearance

        if entering:
            btn.configure(bg="#21262d")
        else:
            btn.configure(bg="#161b22")

    def select_agent(self, agent_name: str):
        """Select an agent (highlight it)"""
        if self.locked:
            return

        # Deselect previous
        if self.selected_agent_name and self.selected_agent_name in self.agent_buttons:
            prev_btn = self.agent_buttons[self.selected_agent_name]
            prev_btn.configure(bg="#161b22", relief="flat")

        # Select new
        self.selected_agent_name = agent_name
        self.selected_agent = self.api.AGENTS.get(agent_name)

        btn = self.agent_buttons[agent_name]
        btn.configure(bg="#238636", relief="solid")

        # Enable lock button
        self.lock_btn.configure(
            text=f"LOCK IN {agent_name.upper()}",
            fg="white", bg="#238636",
            activeforeground="white", activebackground="#2ea043",
            state="normal", cursor="hand2",
            command=self.lock_agent
        )

    def lock_agent(self):
        """Lock the selected agent"""
        if self.locked or not self.selected_agent:
            return

        agent_name = self.selected_agent_name
        agent_id = self.selected_agent

        # Disable button immediately
        self.lock_btn.configure(
            text="LOCKING...",
            fg="#8b949e", bg="#21262d",
            state="disabled", cursor="arrow"
        )

        def do_lock():
            success = self.api.lock_agent(agent_id)
            if success:
                self.locked = True
                self.root.after(0, lambda: self.lock_btn.configure(
                    text="LOCKED",
                    fg="#3fb950", bg="#21262d",
                    state="disabled"
                ))
            else:
                self.root.after(0, lambda: self.lock_btn.configure(
                    text=f"LOCK IN {agent_name.upper()}",
                    fg="white", bg="#238636",
                    state="normal", cursor="hand2"
                ))

        threading.Thread(target=do_lock, daemon=True).start()

    def show_dodge_confirm(self):
        """Show dodge confirmation"""
        self.dodge_confirming = True
        self.dodge_btn.pack_forget()
        self.confirm_frame.pack(fill="x")

    def hide_dodge_confirm(self):
        """Hide dodge confirmation"""
        self.dodge_confirming = False
        self.confirm_frame.pack_forget()
        self.dodge_btn.pack(fill="x")

    def do_dodge(self):
        """Actually dodge the match"""
        def dodge():
            if self.api.dodge_match():
                self.root.after(0, self.hide)
            else:
                self.root.after(0, self.hide_dodge_confirm)

        threading.Thread(target=dodge, daemon=True).start()

    def on_drag_start(self, event):
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()

    def on_drag_motion(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def show(self):
        """Show and reset state"""
        self.locked = False
        self.selected_agent = None
        self.selected_agent_name = None
        self.dodge_confirming = False

        # Reset UI
        self.lock_btn.configure(
            text="SELECT AN AGENT",
            fg="#8b949e", bg="#21262d",
            state="disabled", cursor="arrow"
        )
        self.hide_dodge_confirm()

        # Reset agent buttons
        for btn in self.agent_buttons.values():
            btn.configure(bg="#161b22", relief="flat")

        if not self.visible:
            self.visible = True
            self.root.deiconify()

    def hide(self):
        if self.visible:
            self.visible = False
            self.root.withdraw()

    def close(self):
        self.running = False
        self.root.quit()
        self.root.destroy()


def main():
    """Standalone test"""
    app = AgentSelectOverlay()
    app.show()
    app.root.mainloop()


if __name__ == "__main__":
    main()
