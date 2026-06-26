"""UI components used across the Master Sentinal application."""

from collections import deque

import customtkinter as ctk


class LiveChart(ctk.CTkFrame):
    """A lightweight live chart drawn on a tkinter canvas (no extra deps).

    Two render modes share one widget:

    * ``"bars"`` — a histogram of the latest per-series values (e.g. per-thread
      CPU usage right now).
    * ``"line"`` — a time-series line of the overall value's recent history.

    Values are expected on a 0-100 scale (percentages). Call :meth:`update_values`
    each tick with the current per-series list; the widget keeps its own history
    for the line view. :meth:`toggle_mode` flips between the two views.
    """

    _BAR_COLOR = "#2e8b57"
    _LINE_COLOR = "#1f9bd6"
    _GRID_COLOR = "#3a3a3a"
    _AXIS_TEXT = "#888888"

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *args,
        height: int = 160,
        history: int = 90,
        mode: str = "bars",
        **kwargs,
    ) -> None:
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=("white", "gray17"))

        self._mode = mode
        self._latest: list[float] = []
        self._overall_history: deque[float] = deque(maxlen=history)

        # Canvas background tuned for the dark theme; CTkCanvas would re-theme,
        # but a plain tk Canvas via CTkFrame keeps the drawing API simple.
        self._canvas = ctk.CTkCanvas(
            self, height=height, highlightthickness=0, background="#1d1d1d",
        )
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self._canvas.bind("<Configure>", lambda _event: self._redraw())

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Switch render mode to ``"bars"`` or ``"line"`` and redraw."""
        if mode not in ("bars", "line"):
            return
        self._mode = mode
        self._redraw()

    def toggle_mode(self) -> str:
        """Flip between bar and line views; return the new mode."""
        self.set_mode("line" if self._mode == "bars" else "bars")
        return self._mode

    def update_values(self, values: list[float], overall: float | None = None) -> None:
        """Feed the latest per-series values (0-100) and append to history.

        ``overall`` is the single value tracked for the line view; when omitted
        it defaults to the average of ``values``.
        """
        self._latest = [self._clamp(v) for v in values]
        if overall is None:
            overall = sum(self._latest) / len(self._latest) if self._latest else 0.0
        self._overall_history.append(self._clamp(overall))
        self._redraw()

    @staticmethod
    def _clamp(value: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, value))

    def _redraw(self) -> None:
        try:
            self._canvas.delete("all")
            width = self._canvas.winfo_width()
            height = self._canvas.winfo_height()
            if width <= 1 or height <= 1:
                return
            self._draw_gridlines(width, height)
            if self._mode == "bars":
                self._draw_bars(width, height)
            else:
                self._draw_line(width, height)
        except Exception:
            # Drawing must never crash the UI thread.
            pass

    def _draw_gridlines(self, width: int, height: int) -> None:
        pad_left, pad_bottom, pad_top = 32, 16, 8
        for pct in (0, 25, 50, 75, 100):
            y = pad_top + (height - pad_top - pad_bottom) * (1 - pct / 100)
            self._canvas.create_line(pad_left, y, width - 4, y, fill=self._GRID_COLOR)
            self._canvas.create_text(
                pad_left - 6, y, text=f"{pct}", anchor="e",
                fill=self._AXIS_TEXT, font=("Roboto", 8),
            )

    def _draw_bars(self, width: int, height: int) -> None:
        pad_left, pad_bottom, pad_top = 32, 16, 8
        if not self._latest:
            return
        plot_w = width - pad_left - 6
        plot_h = height - pad_top - pad_bottom
        count = len(self._latest)
        slot = plot_w / count
        bar_w = max(2, slot * 0.7)
        for i, value in enumerate(self._latest):
            x0 = pad_left + i * slot + (slot - bar_w) / 2
            x1 = x0 + bar_w
            bar_h = plot_h * (value / 100)
            y1 = pad_top + plot_h
            y0 = y1 - bar_h
            color = self._BAR_COLOR if value < 85 else "#d9534f"
            self._canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
            if count <= 32:
                self._canvas.create_text(
                    (x0 + x1) / 2, y1 + 7, text=str(i), anchor="n",
                    fill=self._AXIS_TEXT, font=("Roboto", 7),
                )

    def _draw_line(self, width: int, height: int) -> None:
        pad_left, pad_bottom, pad_top = 32, 16, 8
        history = list(self._overall_history)
        if len(history) < 2:
            return
        plot_w = width - pad_left - 6
        plot_h = height - pad_top - pad_bottom
        step = plot_w / (len(history) - 1)
        points: list[float] = []
        for i, value in enumerate(history):
            x = pad_left + i * step
            y = pad_top + plot_h * (1 - value / 100)
            points.extend((x, y))
        self._canvas.create_line(*points, fill=self._LINE_COLOR, width=2, smooth=True)
        # Highlight the most recent point.
        self._canvas.create_oval(
            points[-2] - 3, points[-1] - 3, points[-2] + 3, points[-1] + 3,
            fill=self._LINE_COLOR, outline="",
        )


class MetricCard(ctk.CTkFrame):
    """A dashboard card displaying a title and a live-updating value."""

    def __init__(self, master: ctk.CTkBaseClass, title: str, value_var: ctk.StringVar, *args, **kwargs) -> None:
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=("white", "gray20"))

        self.title_label = ctk.CTkLabel(self, text=title, font=("Roboto Medium", 14), text_color="gray70")
        self.title_label.pack(pady=(10, 0), padx=10, anchor="w")

        self.value_label = ctk.CTkLabel(self, textvariable=value_var, font=("Roboto", 24, "bold"))
        self.value_label.pack(pady=(5, 10), padx=10, anchor="w")


class InfoRow(ctk.CTkFrame):
    """A single label → value row used inside SectionFrame."""

    def __init__(self, master: ctk.CTkBaseClass, label_text: str, value_text: str, *args, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", *args, **kwargs)

        self.label = ctk.CTkLabel(self, text=label_text, font=("Roboto", 12), text_color="gray60", width=120, anchor="w")
        self.label.pack(side="left", padx=5)

        self.value = ctk.CTkLabel(self, text=value_text, font=("Roboto", 12, "bold"), anchor="w", wraplength=400)
        self.value.pack(side="left", padx=5, fill="x", expand=True)


class SectionFrame(ctk.CTkFrame):
    """A titled section container that holds InfoRow children."""

    def __init__(self, master: ctk.CTkBaseClass, title: str, *args, **kwargs) -> None:
        super().__init__(master, *args, **kwargs)

        self.title = ctk.CTkLabel(self, text=title, font=("Roboto", 18, "bold"))
        self.title.pack(pady=10, padx=10, anchor="w")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=10, pady=5)

    def add_row(self, label: str, value: str) -> "InfoRow":
        """Add a label-value row and return the InfoRow widget reference."""
        row = InfoRow(self.content, label, value)
        row.pack(fill="x", pady=2)
        return row
