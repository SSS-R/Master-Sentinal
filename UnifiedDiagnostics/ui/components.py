import customtkinter as ctk

class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title, value_var, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=("white", "gray20"))
        
        self.title_label = ctk.CTkLabel(self, text=title, font=("Roboto Medium", 14), text_color="gray70")
        self.title_label.pack(pady=(10, 0), padx=10, anchor="w")
        
        self.value_label = ctk.CTkLabel(self, textvariable=value_var, font=("Roboto", 24, "bold"))
        self.value_label.pack(pady=(5, 10), padx=10, anchor="w")

class InfoRow(ctk.CTkFrame):
    def __init__(self, master, label_text, value_text, *args, **kwargs):
        super().__init__(master, fg_color="transparent", *args, **kwargs)
        
        self.label = ctk.CTkLabel(self, text=label_text, font=("Roboto", 12), text_color="gray60", width=120, anchor="w")
        self.label.pack(side="left", padx=5)
        
        self.value = ctk.CTkLabel(self, text=value_text, font=("Roboto", 12, "bold"), anchor="w", wraplength=400)
        self.value.pack(side="left", padx=5, fill="x", expand=True)

class SectionFrame(ctk.CTkFrame):
    def __init__(self, master, title, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        
        self.title = ctk.CTkLabel(self, text=title, font=("Roboto", 18, "bold"))
        self.title.pack(pady=10,padx=10, anchor="w")
        
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=10, pady=5)

    def add_row(self, label, value):
        row = InfoRow(self.content, label, value)
        row.pack(fill="x", pady=2)
