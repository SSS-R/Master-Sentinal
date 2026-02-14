"""UI components used across the Master Sentinal application."""

import customtkinter as ctk


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
