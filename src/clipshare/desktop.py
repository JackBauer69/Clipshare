"""Tkinter control window for the browser-based ClipShare session."""

import queue
import signal
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from .clipboard_share import ShareServer, local_ip
from .instance import SingleInstanceLock


class ClipShareApp:
    def __init__(self, root, instance_lock):
        self.root = root
        self.instance_lock = instance_lock
        self.session = None
        self.events = queue.Queue()
        self.busy = False
        self.quit_after_stop = False

        root.title("ClipShare")
        root.geometry("620x530")
        root.minsize(520, 480)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="ClipShare", font=("TkDefaultFont", 20, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Share text, files, and folders with devices on your local network.",
            wraplength=560,
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        status_frame = ttk.LabelFrame(frame, text="Sharing status", padding=12)
        status_frame.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        status_frame.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Starting ClipShare…")
        ttk.Label(status_frame, textvariable=self.status_var, font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.port_notice_var = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=self.port_notice_var, wraplength=550).grid(row=0, column=1, sticky="e")
        ttk.Label(status_frame, text="Local address").grid(row=1, column=0, sticky="w", pady=(12, 2))
        self.local_url_var = tk.StringVar(value="")
        ttk.Entry(status_frame, textvariable=self.local_url_var, state="readonly").grid(row=2, column=0, sticky="ew")
        ttk.Label(status_frame, text="For other devices on this network").grid(row=3, column=0, sticky="w", pady=(10, 2))
        self.lan_url_var = tk.StringVar(value="")
        ttk.Entry(status_frame, textvariable=self.lan_url_var, state="readonly").grid(row=4, column=0, sticky="ew")
        ttk.Button(status_frame, text="Copy LAN address", command=self.copy_lan_url).grid(row=5, column=0, sticky="w", pady=(6, 0))

        code_frame = ttk.LabelFrame(frame, text="Session code", padding=12)
        code_frame.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        code_frame.columnconfigure(0, weight=1)
        ttk.Label(code_frame, text="Enter this 4-digit code on your phone or another device. This computer joins automatically.", wraplength=550).grid(row=0, column=0, sticky="w")
        self.code_var = tk.StringVar(value="")
        ttk.Label(code_frame, textvariable=self.code_var, font=("TkFixedFont", 18, "bold")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(code_frame, text="Copy code", command=self.copy_code).grid(row=2, column=0, sticky="w", pady=(6, 0))

        ttk.Label(
            frame,
            text="Only share on a network you trust. Local network traffic uses HTTP and is not encrypted. "
            "Messages and uploaded files are temporary and are erased when sharing stops.",
            wraplength=560,
        ).grid(row=4, column=0, sticky="w", pady=(0, 14))

        controls = ttk.Frame(frame)
        controls.grid(row=5, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)
        self.open_button = ttk.Button(controls, text="Open ClipShare", command=self.open_browser, state="disabled")
        self.open_button.grid(row=0, column=0, sticky="w")
        self.start_button = ttk.Button(controls, text="Start sharing", command=self.start_session, state="disabled")
        self.start_button.grid(row=0, column=1, padx=(8, 0))
        self.stop_button = ttk.Button(controls, text="Stop sharing", command=self.stop_session, state="disabled")
        self.stop_button.grid(row=0, column=2, padx=(8, 0))
        self.quit_button = ttk.Button(controls, text="Quit", command=self.quit_app)
        self.quit_button.grid(row=0, column=3, padx=(8, 0))
        self.feedback_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.feedback_var).grid(row=6, column=0, sticky="w", pady=(8, 0))

        root.after(100, self.poll_events)
        root.after(200, self.start_session)

    def set_state(self, running):
        self.open_button.configure(state="normal" if running and not self.busy else "disabled")
        self.start_button.configure(state="disabled" if running or self.busy else "normal")
        self.stop_button.configure(state="normal" if running and not self.busy else "disabled")
        self.quit_button.configure(state="disabled" if self.busy else "normal")

    def start_session(self):
        if self.session is not None or self.busy:
            return
        try:
            session = ShareServer().start()
        except OSError as error:
            self.status_var.set("ClipShare could not start")
            self.set_state(False)
            messagebox.showerror(
                "Could not start ClipShare",
                f"ClipShare could not open a network port. Check your network permissions and try again.\n\n{error}",
                parent=self.root,
            )
            return
        self.session = session
        self.status_var.set("Sharing is on")
        self.port_notice_var.set("")
        self.local_url = f"http://localhost:{session.port}/"
        self.local_url_var.set(self.local_url)
        address = local_ip()
        self.lan_url = f"http://{address}:{session.port}/" if address else "LAN address unavailable on this network"
        self.lan_url_var.set(self.lan_url)
        self.code_var.set(session.state.pairing_code)
        if session.port_fallback:
            self.port_notice_var.set(f"Port 3570 was busy; using port {session.port} instead.")
        self.instance_lock.write_state({"running": True, "port": session.port})
        self.set_state(True)
        if not webbrowser.open(session.local_login_url()):
            messagebox.showinfo("ClipShare is ready", "Click Open ClipShare to open the sharing page.", parent=self.root)

    def open_browser(self):
        if self.session is not None:
            webbrowser.open(self.session.local_login_url())

    def copy_lan_url(self):
        if not getattr(self, "lan_url", "") or self.lan_url.startswith("LAN address unavailable"):
            self.feedback_var.set("No LAN address is available. Connect this computer to a network and try again.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.lan_url)
        self.feedback_var.set("LAN address copied")

    def copy_code(self):
        if not self.code_var.get():
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.code_var.get())
        self.feedback_var.set("Session code copied")

    def stop_session(self, quit_after=False):
        if self.session is None or self.busy:
            return
        session = self.session
        self.busy = True
        self.quit_after_stop = quit_after
        self.status_var.set("Stopping sharing and removing temporary files…")
        self.set_state(True)

        def stop_worker():
            try:
                session.stop()
                self.events.put(("stopped", None))
            except Exception as error:  # keep the GUI alive to report shutdown failures
                self.events.put(("stop-error", error))

        threading.Thread(target=stop_worker, name="ClipShareStop", daemon=True).start()

    def poll_events(self):
        try:
            while True:
                event, detail = self.events.get_nowait()
                if event == "stopped":
                    self.session = None
                    self.instance_lock.write_state({"running": False})
                    self.status_var.set("Sharing is off; temporary content was removed")
                    self.port_notice_var.set("")
                    self.local_url_var.set("")
                    self.lan_url_var.set("")
                    self.code_var.set("")
                    self.feedback_var.set("")
                    self.busy = False
                    if self.quit_after_stop:
                        self.root.destroy()
                        return
                    self.quit_after_stop = False
                    self.set_state(False)
                elif event == "stop-error":
                    self.busy = False
                    self.quit_after_stop = False
                    self.status_var.set(
                        "ClipShare could not confirm shutdown. Sharing may still be running; retry Stop sharing."
                    )
                    messagebox.showerror(
                        "Could not stop ClipShare",
                        "ClipShare could not confirm that sharing stopped. The session is still tracked. "
                        "Use Stop sharing to retry shutdown.\n\n"
                        f"{detail}",
                        parent=self.root,
                    )
                    self.set_state(self.session is not None)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self.poll_events)

    def on_close(self):
        if self.busy:
            return
        if self.session is not None:
            if not messagebox.askyesno(
                "Stop and quit ClipShare?",
                "Closing ClipShare stops sharing and deletes the temporary session content. Continue?",
                parent=self.root,
            ):
                return
            self.stop_session(quit_after=True)
            return
        self.root.destroy()

    def quit_app(self):
        self.on_close()


def existing_instance(lock):
    state = lock.read_state()
    root = tk.Tk()
    root.withdraw()
    if state.get("running") and isinstance(state.get("port"), int):
        webbrowser.open(f"http://localhost:{state['port']}/")
        # A second process cannot safely mint a local login ticket; use the
        # existing desktop window's Open ClipShare button for automatic login.
    else:
        messagebox.showinfo(
            "ClipShare is already open",
            "Use the existing ClipShare window to start sharing.",
            parent=root,
        )
    root.destroy()


def main():
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        existing_instance(instance_lock)
        return
    try:
        root = tk.Tk()
        app = ClipShareApp(root, instance_lock)

        def request_os_shutdown():
            if app.session is not None:
                app.stop_session(quit_after=True)
            else:
                root.destroy()

        signal.signal(signal.SIGTERM, lambda _signum, _frame: root.after(0, request_os_shutdown))
        root.mainloop()
    finally:
        instance_lock.write_state({"running": False})
        instance_lock.release()
