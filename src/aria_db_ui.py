import os
from pathlib import Path
from tkinter import messagebox
import customtkinter as ctk
import aria_db


class AriaDBManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_close_callback=None):
        super().__init__(parent)
        self.title("A.R.I.A. - Gestor de Base de Datos y Reportes")
        self.geometry("760x560")
        self.on_close_callback = on_close_callback
        self.grab_set()

        aria_db.init_db()

        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_cred = self.tabview.add("Credenciales")
        self.tab_prov = self.tabview.add("Proveedores Lab")
        self.tab_proc = self.tabview.add("Procedimientos")
        self.tab_rep = self.tabview.add("Reportes PDF")

        self._build_tab_credenciales()
        self._build_tab_proveedores()
        self._build_tab_procedimientos()
        self._build_tab_reportes()

        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    def _cerrar(self):
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()

    # ---------------- TAB 1: CREDENCIALES ----------------
    def _build_tab_credenciales(self):
        usuario, password = aria_db.obtener_credenciales()
        frame = ctk.CTkFrame(self.tab_cred, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Credenciales de Acceso SIGSS",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(frame, text="Usuario:").pack(anchor="w")
        self.entry_user = ctk.CTkEntry(frame)
        self.entry_user.insert(0, usuario)
        self.entry_user.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(frame, text="Contraseña:").pack(anchor="w")
        self.entry_pass = ctk.CTkEntry(frame, show="*")
        self.entry_pass.insert(0, password)
        self.entry_pass.pack(fill="x", pady=(0, 15))

        ctk.CTkButton(
            frame,
            text="Guardar / Sobrescribir Credenciales",
            fg_color="green",
            hover_color="darkgreen",
            command=self._guardar_cred,
        ).pack(anchor="w")

    def _guardar_cred(self):
        u, p = self.entry_user.get().strip(), self.entry_pass.get().strip()
        if not u or not p:
            messagebox.showwarning("Campos vacíos", "Ingresa usuario y contraseña.")
            return
        aria_db.guardar_credenciales(u, p)
        messagebox.showinfo("Guardado", "Credenciales actualizadas en SQLite.")

    # ---------------- TAB 2: PROVEEDORES LAB ----------------
    def _build_tab_proveedores(self):
        top = ctk.CTkFrame(self.tab_prov, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=10)

        self.entry_prov_nombre = ctk.CTkEntry(top, placeholder_text="Nombre proveedor (ej. SEPROLAB)")
        self.entry_prov_nombre.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.entry_prov_nit = ctk.CTkEntry(top, placeholder_text="NIT", width=150)
        self.entry_prov_nit.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            top,
            text="Guardar",
            width=90,
            fg_color="#2563eb",
            command=self._guardar_prov,
        ).pack(side="left")

        self.scroll_prov = ctk.CTkScrollableFrame(self.tab_prov)
        self.scroll_prov.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._refrescar_proveedores()

    def _guardar_prov(self):
        n, nit = self.entry_prov_nombre.get().strip(), self.entry_prov_nit.get().strip()
        if not n or not nit:
            return
        aria_db.guardar_proveedor_lab(n, nit)
        self.entry_prov_nombre.delete(0, "end")
        self.entry_prov_nit.delete(0, "end")
        self._refrescar_proveedores()

    def _refrescar_proveedores(self):
        for w in self.scroll_prov.winfo_children():
            w.destroy()
        for nombre, nit in aria_db.listar_proveedores_lab().items():
            row = ctk.CTkFrame(self.scroll_prov)
            row.pack(fill="x", pady=3, padx=4)
            ctk.CTkLabel(row, text=f"{nombre} | NIT: {nit}").pack(side="left", padx=8, pady=5)
            ctk.CTkButton(
                row,
                text="Eliminar",
                width=75,
                fg_color="red",
                hover_color="darkred",
                command=lambda n=nombre: (aria_db.eliminar_proveedor_lab(n), self._refrescar_proveedores()),
            ).pack(side="right", padx=6, pady=4)

    # ---------------- TAB 3: PROCEDIMIENTOS ÚNICOS ----------------
    def _build_tab_procedimientos(self):
        top = ctk.CTkFrame(self.tab_proc, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=10)

        self.entry_p_serv = ctk.CTkEntry(top, placeholder_text="Servicio (ej. CARDIOLOGIA)", width=170)
        self.entry_p_serv.pack(side="left", padx=(0, 5))

        self.entry_p_prov = ctk.CTkEntry(top, placeholder_text="Proveedor exacto SIGSS")
        self.entry_p_prov.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.entry_p_nit = ctk.CTkEntry(top, placeholder_text="NIT", width=110)
        self.entry_p_nit.pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            top,
            text="Guardar",
            width=80,
            fg_color="#2563eb",
            command=self._guardar_proc,
        ).pack(side="left")

        self.scroll_proc = ctk.CTkScrollableFrame(self.tab_proc)
        self.scroll_proc.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._refrescar_procedimientos()

    def _guardar_proc(self):
        s, p, nit = (
            self.entry_p_serv.get().strip(),
            self.entry_p_prov.get().strip(),
            self.entry_p_nit.get().strip(),
        )
        if not s or not p or not nit:
            return
        aria_db.guardar_procedimiento_extra(s, p, nit)
        self.entry_p_serv.delete(0, "end")
        self.entry_p_prov.delete(0, "end")
        self.entry_p_nit.delete(0, "end")
        self._refrescar_procedimientos()

    def _refrescar_procedimientos(self):
        for w in self.scroll_proc.winfo_children():
            w.destroy()
        for serv, prov, nit in aria_db.listar_procedimientos_extra():
            row = ctk.CTkFrame(self.scroll_proc)
            row.pack(fill="x", pady=3, padx=4)
            ctk.CTkLabel(
                row,
                text=f"{serv} -> {prov} ({nit})",
                wraplength=540,
                justify="left",
            ).pack(side="left", padx=8, pady=5)
            ctk.CTkButton(
                row,
                text="Eliminar",
                width=75,
                fg_color="red",
                hover_color="darkred",
                command=lambda s=serv: (aria_db.eliminar_procedimiento_extra(s), self._refrescar_procedimientos()),
            ).pack(side="right", padx=6, pady=4)

    # ---------------- TAB 4: REPORTES PDF ----------------
    def _build_tab_reportes(self):
        self.scroll_rep = ctk.CTkScrollableFrame(self.tab_rep)
        self.scroll_rep.pack(fill="both", expand=True, padx=10, pady=10)
        self._refrescar_reportes()

    def _refrescar_reportes(self):
        for w in self.scroll_rep.winfo_children():
            w.destroy()
        reportes = aria_db.listar_reportes_pdf()
        if not reportes:
            ctk.CTkLabel(self.scroll_rep, text="Aún no hay reportes PDF guardados en la base de datos.").pack(pady=20)
            return
        for r in reportes:
            row = ctk.CTkFrame(self.scroll_rep)
            row.pack(fill="x", pady=4, padx=4)
            info = f"#{r['id']} | {r['fecha_inicio']} ({r['duracion_texto']}) | {r['proveedor']} | Éxitos: {r['total_exito']}"
            ctk.CTkLabel(row, text=info).pack(side="left", padx=8, pady=6)
            ctk.CTkButton(
                row,
                text="Abrir PDF",
                width=90,
                fg_color="#2563eb",
                command=lambda rid=r["id"]: self._abrir_pdf(rid),
            ).pack(side="right", padx=6, pady=4)

    def _abrir_pdf(self, reporte_id: int):
        carpeta = Path(__file__).resolve().parent / "salida" / "reportes_pdf"
        ruta = aria_db.exportar_reporte_pdf(reporte_id, carpeta)
        if ruta and ruta.is_file():
            try:
                os.startfile(str(ruta))  # Windows
            except AttributeError:
                messagebox.showinfo("PDF Exportado", f"Guardado en:\n{ruta}")