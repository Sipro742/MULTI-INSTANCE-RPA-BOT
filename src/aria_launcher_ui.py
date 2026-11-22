import subprocess
import threading
import tkinter as tk
from pathlib import Path
import customtkinter as ctk
from datetime import datetime
import re
import aria_db
from aria_db_ui import AriaDBManagerWindow

# Configuración inicial de apariencia
ctk.set_appearance_mode("System")  # "Dark", "Light", "System"
ctk.set_default_color_theme("blue")

class AriaLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("A.R.I.A. - Panel de Control Operativo")
        self.geometry("1150x680")

        # Variables de estado y contador automático
        self.procesos = []
        self.is_running = False
        self.contador_ordenes = 0
        aria_db.init_db()
        self.hora_inicio_sesion = None
        self.desglose_tipos = {}
        self.desglose_estados = {"ARANCELADA": 0, "SIMULADA": 0, "OMITIDA": 0, "ERROR": 0}

        # Paleta de colores distintivos para cada instancia
        self.colores_instancias = {
            1: "#3b82f6",  # Azul
            2: "#10b981",  # Verde
            3: "#f59e0b",  # Naranja / Amarillo
            4: "#8b5cf6",  # Púrpura
            5: "#ec4899"   # Rosa
        }

        # --- DISTRIBUCIÓN PRINCIPAL (Grid 1 Fila, 2 Columnas) ---
        self.grid_columnconfigure(0, weight=1)  # Panel izquierdo (Controles y Métricas)
        self.grid_columnconfigure(1, weight=1)  # Panel derecho (Logs)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # PANEL IZQUIERDO (Controles, Config y Métricas)
        # ==========================================
        self.left_frame = ctk.CTkFrame(self, corner_radius=10)
        self.left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.left_frame.grid_rowconfigure(0, weight=0) # Métricas
        self.left_frame.grid_rowconfigure(1, weight=0) # Configuración
        self.left_frame.grid_rowconfigure(2, weight=0) # Botones
        self.left_frame.grid_columnconfigure(0, weight=1)

        # --- 1. SECCIÓN DE MÉTRICAS (Superior Izquierdo) ---
        self.metrics_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.metrics_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(self.metrics_frame, text="📊 Métricas de Ejecución", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 5))
        
        self.lbl_estado = ctk.CTkLabel(self.metrics_frame, text="Estado: En espera de inicio", text_color="orange", font=ctk.CTkFont(size=12))
        self.lbl_estado.pack(anchor="w")
        
        self.lbl_ordenes = ctk.CTkLabel(self.metrics_frame, text="Órdenes procesadas: 0", font=ctk.CTkFont(size=12))
        self.lbl_ordenes.pack(anchor="w")

        # --- 2. SECCIÓN DE CONFIGURACIÓN (Centro Izquierdo) ---
        self.config_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.config_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(self.config_frame, text="⚙️ Configuración", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 5))

        # Input: Número de Ventanas / Instancias
        ctk.CTkLabel(self.config_frame, text="Número de instancias / ventanas:").pack(anchor="w")
        self.spin_ventanas = ctk.CTkComboBox(self.config_frame, values=["1", "2", "3", "4", "5"])
        self.spin_ventanas.set("3")  # Valor por defecto
        self.spin_ventanas.pack(anchor="w", fill="x", pady=(0, 10))

        # Input: Proveedor (Lista desplegable basada en SQLite / credenciales)
        ctk.CTkLabel(self.config_frame, text="Proveedor a trabajar:").pack(anchor="w")
        proveedores_db = list(aria_db.listar_proveedores_lab().keys()) or ["ALFALAB"]
        self.combo_proveedor = ctk.CTkComboBox(self.config_frame, values=proveedores_db)
        self.combo_proveedor.set(proveedores_db[0])
        self.combo_proveedor.pack(anchor="w", fill="x", pady=(0, 10))

        # Checkbox: Dry-Run (Simulación)
        self.check_dryrun = ctk.CTkCheckBox(self.config_frame, text="Modo Simulación (Dry-Run)")
        self.check_dryrun.select()  # Activado por defecto por seguridad
        self.check_dryrun.pack(anchor="w", pady=5)

        # Checkbox: Modo Headless (Sin interfaz gráfica)
        self.check_headless = ctk.CTkCheckBox(self.config_frame, text="Modo Oculto / Headless (Ahorra RAM)")
        self.check_headless.deselect()  # Desactivado por defecto para ver el navegador
        self.check_headless.pack(anchor="w", pady=5)

        # Checkbox: Modo Optimización2 (bloqueo de recursos + flags de Chromium + viewport reducido)
        self.check_optimizacion2 = ctk.CTkCheckBox(self.config_frame, text="Modo Optimización2")
        self.check_optimizacion2.deselect()  # Desactivado por defecto
        self.check_optimizacion2.pack(anchor="w", pady=5)

        # Checkbox: Modo Procedimientos Únicos (usa PROCEDIMIENTOS_EXTRA.txt en lugar del flujo de laboratorios)
        self.check_procedimientos = ctk.CTkCheckBox(self.config_frame, text="Modo Procedimientos Únicos")
        self.check_procedimientos.deselect()  # Desactivado por defecto
        self.check_procedimientos.pack(anchor="w", pady=5)

        # --- 3. SECCIÓN DE BOTONES (Inferior Izquierdo) ---
        self.buttons_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.buttons_frame.grid(row=2, column=0, padx=10, pady=15, sticky="ew")

        self.btn_iniciar = ctk.CTkButton(self.buttons_frame, text="Iniciar Aria", fg_color="green", hover_color="darkgreen", command=self.iniciar_aria)
        self.btn_iniciar.pack(fill="x", pady=4)

        # Botón centralizado para enviar ENTER a todas las instancias en uso
        self.btn_enter = ctk.CTkButton(self.buttons_frame, text="⏎ Enviar ENTER (Continuar)", fg_color="#2563eb", hover_color="#1d4ed8", state="disabled", command=self.enviar_enter)
        self.btn_enter.pack(fill="x", pady=4)

        self.btn_finalizar = ctk.CTkButton(self.buttons_frame, text="Finalizar Programa", fg_color="red", hover_color="darkred", state="disabled", command=self.finalizar_aria)
        self.btn_finalizar.pack(fill="x", pady=4)
        self.btn_db = ctk.CTkButton(
        self.buttons_frame,
        text="🗄️ Base de Datos y Reportes PDF",
        fg_color="#4b5563",
        hover_color="#374151",
        command=self.abrir_gestor_db,
        )
        self.btn_db.pack(fill="x", pady=4)

        # ==========================================
        # PANEL DERECHO (Consola de Logs)
        # ==========================================
        self.right_frame = ctk.CTkFrame(self, corner_radius=10)
        self.right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.right_frame, text="📜 Registro de Actividad (Colores por Instancia)", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        # Caja de texto para los logs estilo consola
        self.log_textbox = ctk.CTkTextbox(self.right_frame, corner_radius=5, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.log_textbox.configure(state="disabled")

        # Configurar etiquetas de color para cada instancia en el widget de texto subyacente
        for idx, color in self.colores_instancias.items():
            self.log_textbox._textbox.tag_config(f"inst_{idx}", foreground=color)
        self.log_textbox._textbox.tag_config("system", foreground="#9ca3af") # Gris claro para mensajes del sistema
    def abrir_gestor_db(self):
        AriaDBManagerWindow(self, on_close_callback=self._recargar_proveedores_ui)

    def _recargar_proveedores_ui(self):
        provs = list(aria_db.listar_proveedores_lab().keys())
        if provs:
            self.combo_proveedor.configure(values=provs)
        if self.combo_proveedor.get() not in provs:
            self.combo_proveedor.set(provs[0])
    def escribir_log(self, mensaje: str, tag="system"):
        """Inserta texto en la consola de logs con formato de color por hilo."""
        self.log_textbox.configure(state="normal")
        self.log_textbox._textbox.insert("end", mensaje + "\n", tag)
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def iniciar_aria(self):
        ventanas = int(self.spin_ventanas.get())
        proveedor = self.combo_proveedor.get()
        is_dry_run = self.check_dryrun.get() == 1

        # Reiniciar contador para la nueva ejecución
        self.contador_ordenes = 0
        self.hora_inicio_sesion = datetime.now()
        self.desglose_tipos = {}
        self.desglose_estados = {"ARANCELADA": 0, "SIMULADA": 0, "OMITIDA": 0, "ERROR": 0}
        self.lbl_ordenes.configure(text="Órdenes procesadas: 0")

        self.is_running = True
        self.btn_iniciar.configure(state="disabled")
        self.btn_enter.configure(state="normal")
        self.btn_finalizar.configure(state="normal")
        self.spin_ventanas.configure(state="disabled")
        self.combo_proveedor.configure(state="disabled")
        
        self.lbl_estado.configure(text="Estado: Ejecutándose (Usa 'Enviar ENTER' cuando requiera continuar)", text_color="green")
        self.escribir_log(f"--- Iniciando {ventanas} instancia(s) de Aria para {proveedor} ---", "system")

        # Lanzar los procesos en hilos separados
        threading.Thread(target=self._ejecutar_procesos_aria, args=(ventanas, proveedor, is_dry_run), daemon=True).start()

    def _ejecutar_procesos_aria(self, ventanas: int, proveedor: str, is_dry_run: bool):
        script_path = Path(__file__).resolve().parent / "clinsys_arancelar_sinautolog.py"
        is_headless = self.check_headless.get() == 1  # Leer el estado del checkbox
        is_optimizacion2 = self.check_optimizacion2.get() == 1  # Leer el estado del checkbox de optimización 2
        is_procedimientos = self.check_procedimientos.get() == 1  # Leer el estado del checkbox de procedimientos únicos
        
        for i in range(ventanas):
            if not self.is_running:
                break
            
            cmd = ["python", str(script_path), "--proveedor", proveedor]
            if is_dry_run:
                cmd.append("--dry-run")

            if is_headless:  # Si está marcado, enviamos el argumento al motor
                cmd.append("--headless")

            if is_optimizacion2:  # Si está marcado, enviamos el argumento al motor
                cmd.append("--optimizacion2")

            if is_procedimientos:  # Si está marcado, el motor trabaja con PROCEDIMIENTOS_EXTRA.txt
                cmd.append("--procedimientos-unicos")

            # Ejecutamos el subproceso con comunicación stdin abierta
            proceso = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.procesos.append(proceso)

            # Hilo para leer la salida de esta instancia con su etiqueta de color asignada
            tag_name = f"inst_{i+1}"
            threading.Thread(target=self._leer_salida_proceso, args=(proceso, i+1, tag_name), daemon=True).start()

    def _leer_salida_proceso(self, proceso, id_instancia, tag_name):
        for linea in iter(proceso.stdout.readline, ''):
            if linea:
                texto_limpio = linea.strip()
                self.escribir_log(f"[Instancia {id_instancia}] {texto_limpio}", tag_name)

                # Detección automática en tiempo real de órdenes procesadas con éxito
                if "ARANCELADA" in texto_limpio.upper() or "SIMULADA" in texto_limpio.upper():
                    self.contador_ordenes += 1
                    # Actualizar la interfaz de forma segura desde el hilo secundario
                    self.after(0, lambda: self.lbl_ordenes.configure(text=f"Órdenes procesadas: {self.contador_ordenes}"))

                m_res = re.search(r"->\s*(ARANCELADA|SIMULADA|OMITIDA|ERROR)\s*\|\s*[^|]*\|\s*(.+)$", texto_limpio)
                if m_res:
                    est = m_res.group(1).strip().upper()
                    det = m_res.group(2).strip()
                    self.desglose_estados[est] = self.desglose_estados.get(est, 0) + 1
                    if est in ("ARANCELADA", "SIMULADA"):
                        categoria = det.split("|")[0].strip() if "|" in det else det
                        self.desglose_tipos[categoria] = self.desglose_tipos.get(categoria, 0) + 1

        proceso.stdout.close()

    def enviar_enter(self):
        """Envía un ENTER a la entrada estándar de todas las instancias que sigan activas."""
        activas = 0
        for proc in self.procesos:
            if proc.poll() is None:  # Si el proceso sigue ejecutándose
                try:
                    proc.stdin.write("\n")
                    proc.stdin.flush()
                    activas += 1
                except Exception:
                    pass
        
        if activas > 0:
            self.escribir_log(f"--- [UI] Señal ENTER enviada a {activas} instancia(s) activa(s) ---", "system")
        else:
            self.escribir_log("--- [UI] No hay instancias activas esperando confirmación ---", "system")

    def finalizar_aria(self):
        self.is_running = False
        if self.hora_inicio_sesion is not None:
            modo = "Procedimientos Únicos" if self.check_procedimientos.get() == 1 else "Laboratorios"
        if self.check_dryrun.get() == 1:
            modo += " (Dry-Run)"
        rid, nombre_pdf = aria_db.generar_y_guardar_reporte_pdf(
        fecha_inicio=self.hora_inicio_sesion,
        fecha_fin=datetime.now(),
        proveedor=self.combo_proveedor.get(),
        modo=modo,
        total_exito=self.contador_ordenes,
        desglose_por_tipo=self.desglose_tipos,
        desglose_por_estado=self.desglose_estados,
        )
        self.hora_inicio_sesion = None
        self.escribir_log(f"--- [BD] Reporte PDF #{rid} guardado en SQLite ({nombre_pdf}) ---", "system")
        self.escribir_log("--- Finalizando todas las instancias de Aria... ---", "system")
        
        for proc in self.procesos:
            try:
                proc.terminate()
            except Exception:
                pass
        
        self.procesos.clear()
        self.btn_iniciar.configure(state="normal")
        self.btn_enter.configure(state="disabled")
        self.btn_finalizar.configure(state="disabled")
        self.spin_ventanas.configure(state="normal")
        self.combo_proveedor.configure(state="normal")
        self.lbl_estado.configure(text="Estado: Finalizado / Detenido", text_color="red")
        self.escribir_log("--- Programa finalizado por el operador ---", "system")

if __name__ == "__main__":
    app = AriaLauncherApp()
    app.mainloop()