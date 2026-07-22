"""
Tkinter GUI for the AI Text Toolkit (standard library only).

Two tabs:
  * Detect   -- estimate AI-likelihood of pasted text.
  * Humanize -- rewrite AI-sounding text to read more naturally.

Launch with run.bat, or:  python gui.py   /   python -m ai_text_toolkit.gui
"""

from __future__ import annotations

import queue
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# Work whether run as a module or as a loose script.
try:
    from ai_text_toolkit import common, ai_detector, ai_humanizer, docio
except ImportError:  # pragma: no cover
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ai_text_toolkit import common, ai_detector, ai_humanizer, docio


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI Text Toolkit  —  Detector + Humanizer")
        self.geometry("820x640")
        self.minsize(720, 560)
        self.cfg = common.load_config()

        # Worker threads push zero-arg callables here; only the main thread
        # (this poller) ever touches tk widgets -> thread-safe.
        self.ui_queue: "queue.Queue" = queue.Queue()
        self.after(60, self._drain_ui_queue)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.detect_tab = DetectTab(nb, self)
        self.human_tab = HumanizeTab(nb, self)
        nb.add(self.detect_tab, text="  Detect AI  ")
        nb.add(self.human_tab, text="  Humanize  ")

        self.status = ttk.Label(self, text="Ready — offline mode (no API, open-source).",
                                relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

    def set_status(self, msg: str) -> None:
        self.status.configure(text=msg)

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                callback = self.ui_queue.get_nowait()
                try:
                    callback()
                except Exception:  # noqa: BLE001 - one bad callback must not kill the pump
                    self.set_status("A UI update failed (see console).")
        except queue.Empty:
            pass
        self.after(60, self._drain_ui_queue)


class _BaseTab(ttk.Frame):
    """Shared input/output layout for both tabs."""

    def __init__(self, master, app: App) -> None:
        super().__init__(master, padding=10)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(5, weight=1)

    def _make_input(self, row: int) -> scrolledtext.ScrolledText:
        ttk.Label(self, text="Input text").grid(row=row, column=0, sticky="w")
        box = scrolledtext.ScrolledText(self, height=10, wrap="word", font=("Segoe UI", 10))
        box.grid(row=row + 1, column=0, sticky="nsew", pady=(2, 8))
        return box

    def _make_output(self, row: int, label: str) -> scrolledtext.ScrolledText:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w")
        box = scrolledtext.ScrolledText(self, height=10, wrap="word",
                                        font=("Consolas", 10), state="disabled")
        box.grid(row=row + 1, column=0, sticky="nsew", pady=(2, 4))
        return box

    def _set_text(self, widget: scrolledtext.ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _load_file_into(self, widget: scrolledtext.ScrolledText) -> None:
        patterns = " ".join(sorted("*" + e for e in docio.SUPPORTED_EXT if e))
        path = filedialog.askopenfilename(
            title="Open document",
            filetypes=[("Documents", patterns), ("All files", "*.*")])
        if not path:
            return
        try:
            text = docio.extract_text(path)
        except Exception as exc:  # noqa: BLE001 - show any read error to the user
            messagebox.showerror("Open failed", str(exc))
            return
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        self.app.set_status(f"Loaded {len(text)} chars from {path}")

    def _run_async(self, work, on_done, button: ttk.Button, busy_msg: str) -> None:
        button.configure(state="disabled")
        self.app.set_status(busy_msg)

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                result = f"ERROR: {exc}"

            def finish() -> None:
                on_done(result)
                button.configure(state="normal")
                self.app.set_status("Done.")

            # Marshal back to the main thread via the queue (thread-safe).
            self.app.ui_queue.put(finish)

        threading.Thread(target=runner, daemon=True).start()


class DetectTab(_BaseTab):
    def __init__(self, master, app: App) -> None:
        super().__init__(master, app)
        self.input = self._make_input(0)

        ctl = ttk.Frame(self)
        ctl.grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Label(ctl, text="Backend").pack(side="left")
        self.backend = tk.StringVar(value=app.cfg.get("detector_backend", "auto"))
        ttk.Combobox(ctl, textvariable=self.backend, width=12, state="readonly",
                     values=["auto", "heuristic", "model"]).pack(side="left", padx=6)
        ttk.Button(ctl, text="Open document…",
                   command=lambda: self._load_file_into(self.input)).pack(side="left", padx=6)
        self.btn = ttk.Button(ctl, text="Detect", command=self.on_detect)
        self.btn.pack(side="right")

        self.output = self._make_output(4, "Result")

    def on_detect(self) -> None:
        text = self.input.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("No text", "Paste or load some text first.")
            return
        backend = self.backend.get()

        def work() -> str:
            return ai_detector.detect(text, backend=backend, cfg=self.app.cfg).as_text()

        self._run_async(work, lambda r: self._set_text(self.output, r),
                        self.btn, "Analysing… (first model run downloads weights)")


class HumanizeTab(_BaseTab):
    def __init__(self, master, app: App) -> None:
        super().__init__(master, app)
        self.input = self._make_input(0)

        ctl = ttk.Frame(self)
        ctl.grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Label(ctl, text="Backend").pack(side="left")
        self.backend = tk.StringVar(value=app.cfg.get("humanizer_backend", "auto"))
        ttk.Combobox(ctl, textvariable=self.backend, width=10, state="readonly",
                     values=["auto", "rules", "model"]).pack(side="left", padx=6)
        ttk.Label(ctl, text="Strength").pack(side="left", padx=(10, 0))
        self.strength = tk.StringVar(value=app.cfg.get("humanizer_strength", "medium"))
        ttk.Combobox(ctl, textvariable=self.strength, width=8, state="readonly",
                     values=["light", "medium", "strong"]).pack(side="left", padx=6)
        ttk.Button(ctl, text="Open document…",
                   command=lambda: self._load_file_into(self.input)).pack(side="left", padx=6)
        self.btn = ttk.Button(ctl, text="Humanize", command=self.on_humanize)
        self.btn.pack(side="right")

        self.output = self._make_output(4, "Rewritten text")
        self._report = None

        self.result_lbl = ttk.Label(self, text="AI probability: —", foreground="#06c")
        self.result_lbl.grid(row=6, column=0, sticky="w")

        bottom = ttk.Frame(self)
        bottom.grid(row=7, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(bottom, text="Copy output", command=self.copy_output).pack(side="left")
        ttk.Button(bottom, text="Save output…", command=self.save_output).pack(side="left", padx=6)
        ttk.Button(bottom, text="Show changes", command=self.show_changes).pack(side="left")

    def on_humanize(self) -> None:
        text = self.input.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("No text", "Paste or load some text first.")
            return
        backend, strength = self.backend.get(), self.strength.get()

        def work():
            return ai_humanizer.humanize_with_report(
                text, backend=backend, strength=strength, cfg=self.app.cfg)

        def done(report) -> None:
            if isinstance(report, str):        # an error string from _run_async
                self._set_text(self.output, report)
                return
            self._report = report
            self._set_text(self.output, report.humanized)
            delta = report.reduction_pct
            if delta > 0:
                change = f"down {delta:.0f} pts (more human)"
            elif delta < 0:
                change = f"up {abs(delta):.0f} pts (more AI-like)"
            else:
                change = "no change"
            self.result_lbl.configure(
                text=f"AI probability: {report.before_pct:.0f}%  ->  "
                     f"{report.after_pct:.0f}%   ({change})")

        self._run_async(work, done, self.btn, "Rewriting & measuring…")

    def show_changes(self) -> None:
        if not self._report:
            messagebox.showinfo("No changes yet", "Humanize some text first.")
            return
        dlg = tk.Toplevel(self)
        dlg.title("Exact conversion (before -> after)")
        dlg.geometry("640x480")
        box = scrolledtext.ScrolledText(dlg, wrap="word", font=("Consolas", 10))
        box.pack(fill="both", expand=True)
        box.insert("1.0", "\n".join(self._report.diff) or "(no changes were made)")
        box.configure(state="disabled")

    def copy_output(self) -> None:
        text = self.output.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.app.set_status("Output copied to clipboard.")

    def save_output(self) -> None:
        text = self.output.get("1.0", "end").strip()
        if not text:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Text files", "*.txt")])
        if path:
            open(path, "w", encoding="utf-8").write(text)
            self.app.set_status(f"Saved to {path}")


def main() -> int:
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
