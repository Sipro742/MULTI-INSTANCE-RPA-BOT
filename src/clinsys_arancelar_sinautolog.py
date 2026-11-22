#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A.R.I.A. (Asistente Rápido e Inteligente para Arancelamiento)
CLINSYS - Asistente Semicontrolado con Autologin y Monitoreo Continuo (ADM > MOD-465)
"""
from __future__ import annotations
import aria_db
import argparse
import csv
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import Frame, Page, sync_playwright

# --------------------------------------------------------------------------
# CONFIGURACION (Optimización de velocidad y tiempos reducidos)
# --------------------------------------------------------------------------
BASE_URL = os.getenv("CLINSYS_URL", "http://clinsys.example.com/")    
FRAME_URL_PART = "MOD465_ASIGNA_PROVEEDOR"             
MENU_SELECTOR = 'div.button-app[web$="MOD465_ASIGNA_PROVEEDOR.aspx"]'  
PALABRA_CLAVE = "LABORATORIO"
TIPO_COMPRA = "COMPRA DIRECTA"
TIMEOUT_MS = 42_000                                    # Reducido un 30%

BUSCAR = "input[value='Buscar'], input[value='BUSCAR'], button:has-text('Buscar')"
ARANCELAR = "input[value*='Arancel'], button:has-text('Arancel')"
CAMBIAR_ESTADO = "input[value*='Cambiar a estado impreso'], input[id*='btnCambiarEstado']"
VOLVER = "a[href*='Toolbar1'][href*='Cancelar']"        

log = logging.getLogger("clinsys")


def norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


@dataclass
class Credenciales:
    usuario: str = ""
    password: str = ""
    colegiados: Dict[str, str] = field(default_factory=dict)    
    proveedores: Dict[str, str] = field(default_factory=dict)   


def leer_credenciales(ruta: Path) -> Credenciales:
    aria_db.init_db()
    usuario, password = aria_db.obtener_credenciales()
    cred = Credenciales(
        usuario=os.getenv("CLINSYS_USER", usuario),
        password=os.getenv("CLINSYS_PASS", password),
        colegiados=aria_db.listar_colegiados(),
        proveedores=aria_db.listar_proveedores_lab(),
    )
    return cred


def elegir_opcion(opciones: List[str], palabra_proveedor: str, hoy: date) -> Optional[int]:
    clave = norm(palabra_proveedor)
    for i, texto in enumerate(opciones):
        t = norm(texto)
        if "PROVEEDOR:" not in t or clave not in t:
            continue
        m = re.search(r"VIGENCIA:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", t)
        if not m:
            return i  
        ini = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        fin = datetime.strptime(m.group(2), "%d/%m/%Y").date()
        if ini <= hoy <= fin:
            return i
    return None


@dataclass
class Resultado:
    hora: str
    colegiado: str
    mod465: str
    estado: str      
    detalle: str


class ClinsysBot:
    def __init__(self, page: Page, cred: Credenciales, proveedor: str, nit: str,
                 dry_run: bool, salida: Path):
        self.page, self.cred = page, cred
        self.proveedor, self.nit = proveedor, nit
        self.dry_run, self.salida = dry_run, salida
        self.frame: Frame = None  # type: ignore
        self.resultados: List[Resultado] = []
        self.dialogos: List[str] = []
        page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog) -> None:
        log.info("   [ALERTA DEL SISTEMA]: %s", dialog.message)
        self.dialogos.append(dialog.message)
        dialog.accept()

    def _registrar(self, colegiado: str, num_orden: str, estado: str, detalle: str) -> None:
        self.resultados.append(Resultado(datetime.now().strftime("%H:%M:%S"),
                                         colegiado, num_orden, estado, detalle))
        log.info("   -> %s | %s | %s", estado, num_orden or "?", detalle)

    def _captura(self, nombre: str) -> None:
        try:
            self.page.screenshot(path=str(self.salida / f"{nombre}.png"), full_page=True)
        except Exception:  
            pass

    def login_automatico(self) -> None:
        log.info("Abriendo %s", BASE_URL)
        self.page.goto(BASE_URL, wait_until="domcontentloaded")
        
        # Esperar a que la página de login esté completamente cargada
        self.page.wait_for_timeout(1000)
        
        # Buscamos los inputs de forma general en la página de acceso
        inputs = self.page.locator("input:visible")
        if inputs.count() >= 2:
            log.info("Iniciando sesión automáticamente como %s", self.cred.usuario)
            
            # El primer input visible suele ser el usuario y el segundo la contraseña
            user_input = inputs.nth(0)
            pwd_input = inputs.nth(1)
            
            user_input.click()
            user_input.fill(self.cred.usuario)
            self.page.wait_for_timeout(400)
            
            pwd_input.click()
            pwd_input.fill(self.cred.password)
            self.page.wait_for_timeout(400)
            
            # Enviar el formulario presionando Enter en la contraseña
            pwd_input.press("Enter")
        else:
            log.warning("No se detectaron los campos de autologin automáticamente.")

        # Pausa de control conectada al botón de la UI
        print("\n" + "="*60)
        print(" [PASO 1] Autologin enviado.")
        print(" Verifica en el navegador que la sesión haya iniciado correctamente.")
        print(" Si ya estás dentro, presiona el botón 'Enviar ENTER' en la UI...")
        print("="*60 + "\n")
        sys.stdout.flush()
        input()  # Espera la señal del botón azul de la interfaz
        
        log.info("Continuando con el flujo...")
        self.page.wait_for_timeout(1500)

    def abrir_modulo(self) -> None:
        log.info("Abriendo modulo 'Asignar Precio - Proveedor'")
        self.page.wait_for_timeout(1400)
        self.page.locator(MENU_SELECTOR).first.dispatch_event("click")
        
        self.page.wait_for_function(
            "p => [...document.querySelectorAll('iframe')].some(f => (f.src||'').includes(p))",
            arg=FRAME_URL_PART, timeout=TIMEOUT_MS)
        
        for _ in range(60):  
            marcos = [f for f in self.page.frames if FRAME_URL_PART.lower() in f.url.lower()]
            if marcos:
                self.frame = marcos[-1]
                break
            self.page.wait_for_timeout(300)
        else:
            raise RuntimeError("No se encontro el iframe del modulo.")
        
        log.info("Modulo cargado. Pausa de seguridad...")
        self.page.wait_for_timeout(2000)

    def listar_filas(self) -> List[Tuple[int, str]]:
        filas = self.frame.evaluate(
            r"""() => [...document.querySelectorAll('a')]
                     .filter(a => a.innerText.trim() === 'Seleccionar')
                     .map((a, i) => ({i, t: ((a.closest('tr')||{}).innerText||'').replace(/\s+/g,' ').trim()}))""")
        return [(x["i"], x["t"]) for x in filas]

    def volver_al_listado(self, buscar_despues: bool = True) -> None:
        f = self.frame
        log.info("Regresando al listado principal...")
        self.page.wait_for_timeout(2000)
        if f.locator(VOLVER).count():
            f.locator(VOLVER).first.click()
        else:
            try:
                f.evaluate("__doPostBack('RapCommand$Toolbar1','Cancelar')")
            except Exception:
                pass
        
        self.page.wait_for_timeout(1400)
        
        if buscar_despues:
            self.hacer_clic_buscar()

    def hacer_clic_buscar(self) -> None:
        f = self.frame
        log.info("Ejecutando búsqueda automática en el sistema...")
        btn_buscar = f.locator(BUSCAR).first
        try:
            if btn_buscar.is_visible():
                # Si el botón está deshabilitado porque el CLINSYS ya está cargando, esperamos a que se habilite
                if not btn_buscar.is_enabled():
                    log.info("El botón Buscar está ocupándose en una consulta previa. Esperando a que se habilite...")
                    btn_buscar.wait_for(state="enabled", timeout=20_000)
                
                if btn_buscar.is_enabled():
                    btn_buscar.click(timeout=15_000)
                    self.page.wait_for_timeout(2000)
        except Exception as exc:
            log.warning("Aviso al actualizar listado (el sistema ya estaba recargando): %s", str(exc).splitlines()[0][:100])

    def leer_estudio(self) -> str:
        f = self.frame
        log.info("Leyendo detalles del estudio solicitado...")
        self.page.wait_for_timeout(1500)
        f.wait_for_function("() => /Estudio solicitado/i.test(document.body.innerText)",
                            timeout=TIMEOUT_MS)
        txt = f.evaluate("document.body.innerText")
        m = re.search(r"Estudio solicitado:\s*(.*?)\s*(?:Tipo de compra:|Datos del Registro:)",
                      txt, re.S | re.I)
        if not m:
            raise RuntimeError("No se pudo leer 'Estudio solicitado:'")
        return re.sub(r"\s+", " ", m.group(1)).strip()

    def seleccionar_tipo_compra(self) -> None:
        f = self.frame
        log.info("Seleccionando tipo de compra (%s)...", TIPO_COMPRA)
        self.page.wait_for_timeout(1500)
        
        sel = f.locator("select").filter(has=f.locator("option", has_text=TIPO_COMPRA)).first
        sel.wait_for(state="attached", timeout=TIMEOUT_MS)
        actual = sel.evaluate("s => s.options[s.selectedIndex].text")
        if TIPO_COMPRA in norm(actual):
            return  
        idx = sel.evaluate(
            "(s, t) => [...s.options].findIndex(o => o.text.toUpperCase().includes(t))", TIPO_COMPRA)
        sel.select_option(index=idx)                    
        self.page.wait_for_timeout(2000)

    def seleccionar_proveedor(self) -> None:
        f = self.frame
        log.info("Seleccionando proveedor (%s)...", self.proveedor)
        self.page.wait_for_timeout(1500)
        
        f.wait_for_function(
            "() => [...document.querySelectorAll('select option')].some(o => /Proveedor:/i.test(o.text))",
            timeout=TIMEOUT_MS)
        sel = f.locator("select").filter(has=f.locator("option", has_text="Proveedor:")).first
        opciones = sel.evaluate("s => [...s.options].map(o => o.text)")
        idx = elegir_opcion(opciones, self.proveedor, date.today())
        if idx is None:
            raise RuntimeError(f"No hay opcion vigente para el proveedor '{self.proveedor}'")
        log.info("   proveedor seleccionado: %s", re.sub(r"\s+", " ", opciones[idx]))
        sel.select_option(index=idx)                    
        
        self.page.wait_for_timeout(2000)
        f.wait_for_function(
            "nit => [...document.querySelectorAll('input')].some(i => i.value.trim() === nit)",
            arg=self.nit, timeout=TIMEOUT_MS)

    def arancelar_y_cambiar_estado(self) -> None:
        f = self.frame
        self.dialogos.clear()
        
        log.info("Paso 1: Haciendo clic en 'Arancelar documento'...")
        self.page.wait_for_timeout(800)
        boton_arancel = f.locator(ARANCELAR).first
        boton_arancel.scroll_into_view_if_needed()
        boton_arancel.click()
        
        for _ in range(80):                     
            if self.dialogos:
                break
            self.page.wait_for_timeout(100)
        
        msg = " ".join(self.dialogos)
        log.info("   Alerta de arancelado detectada: %s", msg or "sin alerta")
        self.page.wait_for_timeout(800)

        log.info("Paso 2: Haciendo clic en 'Cambiar a estado impreso'...")
        boton_estado = f.locator(CAMBIAR_ESTADO).first
        boton_estado.scroll_into_view_if_needed()
        boton_estado.click()
        
        log.info("Paso 3: Aceptando confirmación de estado impreso...")
        self.page.wait_for_timeout(800)
        self.page.wait_for_timeout(1500)

    def procesar_orden(self, colegiado: str, indice: int, texto_fila: str) -> None:
        m = re.search(r"(\d{5,7})\s+SISTEMA", texto_fila)
        num_orden = m.group(1) if m else ""
        log.info("--- Procesando orden MOD-465: %s ---", num_orden or texto_fila[:60])
        try:
            self.page.wait_for_timeout(1000)
            self.frame.get_by_role("link", name="Seleccionar", exact=True).nth(indice).click()
            
            estudio = self.leer_estudio()
            log.info("   estudio: %s", estudio[:110])

            if PALABRA_CLAVE not in norm(estudio):      
                self._registrar(colegiado, num_orden, "OMITIDA", "No es LABORATORIO: " + estudio[:80])
                self.volver_al_listado()
                return

            self.seleccionar_tipo_compra()
            self.seleccionar_proveedor()
            
            if not self.dry_run:
                self.arancelar_y_cambiar_estado()
            else:
                log.info("   [DRY-RUN]: se omite 'Arancelar documento' y el cambio de estado.")
            
            if self.dry_run:
                self._registrar(colegiado, num_orden, "SIMULADA", f"{self.proveedor} (dry-run completado)")
                log.info("   [DRY-RUN]: Pausa corta para verificación...")
                self.page.wait_for_timeout(2000)
            else:
                self._registrar(colegiado, num_orden, "ARANCELADA", self.proveedor)
            
            self.volver_al_listado()
        except Exception as exc:  
            self._registrar(colegiado, num_orden, "ERROR", str(exc).splitlines()[0][:200])
            self._captura(f"error_{colegiado}_{num_orden or 'x'}")
            log.warning("   Error en la orden. Intentando reanudar...")
            try:
                self.volver_al_listado()
            except Exception:  
                pass

    def iniciar_modo_manual_asistido(self) -> None:
        print("\n" + "="*60)
        print(" [PASO 2] A.R.I.A. está lista en el módulo 'Asignar Precio - Proveedor'.")
        print(" Por favor:")
        print("   1. Ingresa el número de colegiado en la pantalla del CLINSYS.")
        print("   2. Ajusta las fechas si lo deseas y haz clic en 'Buscar' TÚ MISMO por primera vez.")
        print("   3. Asegúrate de que las órdenes ya aparezcan listadas.")
        print(" Cuando estés listo, ven aquí a la consola y presiona ENTER")
        print(" para que A.R.I.A. comience a procesar y vigilar continuamente.")
        print("="*60 + "\n")
        sys.stdout.flush()
        input()
        log.info("A.R.I.A. iniciada: Procesamiento ultrarrápido y monitoreo continuo activo...")
        
        # Forzar búsqueda inicial inmediata
        self.hacer_clic_buscar()

        colegiado_actual = "MANUAL"
        
        while True:
            try:
                ordenes_procesadas_en_ciclo = 0

                en_detalle_inicial = False
                try:
                    en_detalle_inicial = self.frame.evaluate("() => /Estudio solicitado/i.test(document.body.innerText)")
                except Exception:
                    pass

                if en_detalle_inicial:
                    log.info("--- ¡Detectada orden única directa en pantalla! Analizando... ---")
                    try:
                        estudio = self.leer_estudio()
                        log.info("   estudio: %s", estudio[:110])

                        if PALABRA_CLAVE not in norm(estudio):
                            self._registrar(colegiado_actual, "UNICA", "OMITIDA", "No es LABORATORIO (orden única): " + estudio[:80])
                            self.volver_al_listado(buscar_despues=False)
                        else:
                            self.seleccionar_tipo_compra()
                            self.seleccionar_proveedor()
                            if not self.dry_run:
                                self.arancelar_y_cambiar_estado()
                            else:
                                log.info("   [DRY-RUN]: se omite 'Arancelar documento' y el cambio de estado.")
                            
                            if self.dry_run:
                                self._registrar(colegiado_actual, "UNICA", "SIMULADA", f"{self.proveedor} (dry-run)")
                                self.page.wait_for_timeout(2000)
                            else:
                                self._registrar(colegiado_actual, "UNICA", "ARANCELADA", self.proveedor)
                            
                            self.volver_al_listado(buscar_despues=True)
                            ordenes_procesadas_en_ciclo += 1
                    except Exception as exc:
                        self._registrar(colegiado_actual, "UNICA", "ERROR", str(exc).splitlines()[0][:200])
                        self._captura("error_orden_unica")
                        self.volver_al_listado(buscar_despues=False)

                vistos: set = set()
                while True:
                    try:
                        if self.frame.evaluate("() => /Estudio solicitado/i.test(document.body.innerText)"):
                            break
                    except Exception:
                        pass

                    candidata = None
                    filas = self.listar_filas()
                    for i, texto in filas:
                        if texto in vistos:
                            continue
                        vistos.add(texto)
                        if "ORDENADO" not in norm(texto):
                            continue                        
                        if PALABRA_CLAVE not in norm(texto):
                            self._registrar(colegiado_actual, "", "OMITIDA", "No es LABORATORIO (listado)")
                            continue
                        candidata = (i, texto)
                        break
                    
                    if candidata is None:
                        break
                    
                    self.procesar_orden(colegiado_actual, *candidata)
                    ordenes_procesadas_en_ciclo += 1

                if ordenes_procesadas_en_ciclo > 0:
                    log.info("Ciclo de procesamiento finalizado. Se procesaron %d órdenes.", ordenes_procesadas_en_ciclo)
                else:
                    log.info("No se encontraron órdenes pendientes en este momento.")

                minutos_espera = 2
                segundos_espera = minutos_espera * 60
                log.info("A.R.I.A. entrando en modo de espera: revisando de nuevo en %d minutos...", minutos_espera)
                
                tiempo_transcurrido = 0
                while tiempo_transcurrido < segundos_espera:
                    self.page.wait_for_timeout(20000)  
                    tiempo_transcurrido += 20

                log.info("Tiempo de espera cumplido. Actualizando listado automáticamente...")
                self.hacer_clic_buscar()

            except Exception as exc:
                log.error("Ocurrió un error en el bucle de monitoreo continuo de A.R.I.A.: %s", exc)
                log.info("Reintentando el ciclo de monitoreo en 1 minuto...")
                self.page.wait_for_timeout(60000)

    def guardar_csv(self) -> Path:
        ruta = self.salida / f"resultados_{datetime.now():%Y%m%d_%H%M%S}.csv"
        with ruta.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["hora", "colegiado", "mod465", "estado", "detalle"])
            w.writerows([[r.hora, r.colegiado, r.mod465, r.estado, r.detalle] for r in self.resultados])
        return ruta


# ==========================================================================
# MODO "PROCEDIMIENTOS ÚNICOS"  (--procedimientos-unicos)
# ==========================================================================
ARCHIVO_PROCEDIMIENTOS = "PROCEDIMIENTOS_EXTRA.txt"
OK_ARANCEL = re.compile(r"realizado con .?xito", re.I)
_PALABRAS_VACIAS = {"SOCIEDAD", "ANONIMA", "SA", "DRA", "DR", "LIC", "DE", "LA", "EL", "Y"}


@dataclass
class ProcedimientoExtra:
    servicio: str     
    proveedor: str    
    nit: str          


def leer_procedimientos_extra(ruta: Path) -> List[ProcedimientoExtra]:
    aria_db.init_db()
    filas = aria_db.listar_procedimientos_extra()
    if not filas:
        raise ValueError("La tabla procedimientos_extra en SQLite no contiene servicios válidos.")
    return [ProcedimientoExtra(servicio=s, proveedor=p, nit=n) for s, p, n in filas]


def _limpiar(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", norm(texto)).strip()


def _opcion_vigente(texto: str, hoy: date) -> bool:
    m = re.search(r"VIGENCIA:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", norm(texto))
    if not m:
        return True
    ini = datetime.strptime(m.group(1), "%d/%m/%Y").date()
    fin = datetime.strptime(m.group(2), "%d/%m/%Y").date()
    return ini <= hoy <= fin


def elegir_opcion_proveedor_extra(opciones: List[str], proveedor: str, hoy: date) -> Optional[int]:
    buscado = _limpiar(proveedor)
    palabras = [t for t in buscado.split() if t not in _PALABRAS_VACIAS and len(t) > 1]
    exactas: List[int] = []
    parciales: List[int] = []
    for i, texto in enumerate(opciones):
        t = norm(texto)
        if "PROVEEDOR:" not in t:
            continue
        m = re.search(r"PROVEEDOR:\s*(.*?)\s*(?:;|$)", t)
        nombre = _limpiar(m.group(1)) if m else _limpiar(t)
        if buscado and nombre and (buscado in nombre or nombre in buscado):
            exactas.append(i)
        elif palabras and all(p in nombre.split() for p in palabras):
            parciales.append(i)
    for grupo in (exactas, parciales):
        for i in grupo:
            if _opcion_vigente(opciones[i], hoy):
                return i
    return None


class ClinsysBotProcedimientos(ClinsysBot):
    MAX_INTENTOS = 2     
    MINUTOS_ESPERA = 2   

    def __init__(self, page: Page, cred: Credenciales, proveedor: str, nit: str,
                 dry_run: bool, salida: Path, procedimientos: List[ProcedimientoExtra]):
        super().__init__(page, cred, proveedor, nit, dry_run, salida)
        self.procedimientos = procedimientos
        self._cerradas: set = set()                 
        self._intentos: Dict[str, int] = {}

    @staticmethod
    def _num_orden(texto_fila: str) -> str:
        m = re.search(r"(\d{5,7})\s+SISTEMA", texto_fila)
        return m.group(1) if m else ""

    def _clave_fila(self, texto_fila: str) -> str:
        return self._num_orden(texto_fila) or texto_fila

    def _en_detalle(self) -> bool:
        try:
            return bool(self.frame.evaluate("() => /Estudio solicitado/i.test(document.body.innerText)"))
        except Exception:
            return False

    def _buscar_servicio(self, texto: str) -> Optional[ProcedimientoExtra]:
        t = norm(texto)
        hallados = [p for p in self.procedimientos
                    if re.search(rf"(?<![A-Z0-9]){re.escape(norm(p.servicio))}(?![A-Z0-9])", t)]
        if not hallados:
            return None
        mayor = max(len(norm(p.servicio)) for p in hallados)
        top = [p for p in hallados if len(norm(p.servicio)) == mayor]
        if len({(norm(p.proveedor), p.nit) for p in top}) > 1:
            raise RuntimeError("Servicio ambiguo en el estudio: " + ", ".join(p.servicio for p in top))
        return top[0]

    def _servicio_en_listado(self, texto_fila: str) -> bool:
        try:
            if self._buscar_servicio(texto_fila) is not None:
                return True
            if PALABRA_CLAVE in norm(texto_fila):
                return True
            return False
        except RuntimeError:
            return True   

    def seleccionar_proveedor_extra(self, proc: ProcedimientoExtra) -> None:
        f = self.frame
        log.info("Seleccionando proveedor (%s | NIT %s)...", proc.proveedor, proc.nit)
        self.page.wait_for_timeout(1500)
        f.wait_for_function(
            "() => [...document.querySelectorAll('select option')].some(o => /Proveedor:/i.test(o.text))",
            timeout=TIMEOUT_MS)
        sel = f.locator("select").filter(has=f.locator("option", has_text="Proveedor:")).first
        opciones = sel.evaluate("s => [...s.options].map(o => o.text)")
        idx = elegir_opcion_proveedor_extra(opciones, proc.proveedor, date.today())
        if idx is None:
            raise RuntimeError(f"No hay opcion vigente para el proveedor '{proc.proveedor}'")
        log.info("   proveedor seleccionado: %s", re.sub(r"\s+", " ", opciones[idx]))
        sel.select_option(index=idx)
        self.page.wait_for_timeout(2000)
        nit_ok = re.sub(r"[^0-9A-Z]", "", proc.nit.upper())
        f.wait_for_function(
            "nit => [...document.querySelectorAll('input')].some("
            "i => i.value.toUpperCase().replace(/[^0-9A-Z]/g, '') === nit)",
            arg=nit_ok, timeout=TIMEOUT_MS)

    def _arancelar_validado(self) -> None:
        f = self.frame
        self.dialogos.clear()
        log.info("Paso 1: Haciendo clic en 'Arancelar documento'...")
        self.page.wait_for_timeout(800)
        boton_arancel = f.locator(ARANCELAR).first
        boton_arancel.scroll_into_view_if_needed()
        boton_arancel.click()
        for _ in range(150):                        
            if self.dialogos:
                break
            self.page.wait_for_timeout(100)
        msg = " ".join(self.dialogos)
        if not OK_ARANCEL.search(msg):
            raise RuntimeError(f"El sistema no confirmó el arancelado: {msg or 'sin alerta'}")
        self.page.wait_for_timeout(800)

        log.info("Paso 2: Haciendo clic en 'Cambiar a estado impreso'...")
        boton_estado = f.locator(CAMBIAR_ESTADO).first
        boton_estado.scroll_into_view_if_needed()
        boton_estado.click()
        log.info("Paso 3: Aceptando confirmación de estado impreso...")
        self.page.wait_for_timeout(800)
        self.page.wait_for_timeout(1500)

    def _procesar_detalle_actual(self, colegiado: str, etiqueta: str, clave: Optional[str],
                                 buscar_despues: bool = True) -> None:
        estudio = self.leer_estudio()
        log.info("   estudio: %s", estudio[:110])
        proc = self._buscar_servicio(estudio)

        if proc is None:
            if PALABRA_CLAVE in norm(estudio):
                log.info("   Es un laboratorio normal. Usando proveedor principal de la UI: %s", self.proveedor)
                self.seleccionar_tipo_compra()
                self.seleccionar_proveedor()  

                detalle = f"Laboratorio | {self.proveedor} | NIT {self.nit}"
                if self.dry_run:
                    self._registrar(colegiado, etiqueta, "SIMULADA", detalle + " (dry-run)")
                else:
                    self._arancelar_validado()
                    self._registrar(colegiado, etiqueta, "ARANCELADA", detalle)
                if clave:
                    self._cerradas.add(clave)
                self.volver_al_listado(buscar_despues=buscar_despues)
                return
            else:
                if clave:
                    self._cerradas.add(clave)
                self._registrar(colegiado, etiqueta, "OMITIDA",
                                "No es procedimiento extra ni LABORATORIO: " + estudio[:80])
                self.volver_al_listado(buscar_despues=buscar_despues)
                return

        log.info("   servicio detectado: %s -> %s (NIT %s)", proc.servicio, proc.proveedor, proc.nit)
        self.seleccionar_tipo_compra()
        self.seleccionar_proveedor_extra(proc)

        detalle = f"{proc.servicio} | {proc.proveedor} | NIT {proc.nit}"
        if self.dry_run:                            
            self._registrar(colegiado, etiqueta, "SIMULADA", detalle + " (dry-run: sin arancelar)")
        else:
            self._arancelar_validado()
            self._registrar(colegiado, etiqueta, "ARANCELADA", detalle)
        if clave:
            self._cerradas.add(clave)
        self.volver_al_listado(buscar_despues=buscar_despues)

    def _fallo(self, colegiado: str, etiqueta: str, clave: Optional[str], exc: Exception,
               buscar_despues: bool = True) -> None:
        detalle = (str(exc).splitlines() or [repr(exc)])[0][:160]
        if clave:
            n = self._intentos.get(clave, 0) + 1
            self._intentos[clave] = n
            if n >= self.MAX_INTENTOS:
                self._cerradas.add(clave)
                detalle += f" (intento {n}/{self.MAX_INTENTOS}: revisar manualmente)"
        self._registrar(colegiado, etiqueta, "ERROR", detalle)
        self._captura(f"error_proc_{colegiado}_{etiqueta or 'x'}")
        log.warning("   Error en la orden. Intentando reanudar...")
        try:
            self.volver_al_listado(buscar_despues=buscar_despues)
        except Exception:
            pass

    def procesar_orden_unico(self, colegiado: str, indice: int, texto_fila: str, clave: str) -> None:
        etiqueta = self._num_orden(texto_fila) or texto_fila[:40]
        log.info("--- Procesando orden MOD-465 (procedimiento): %s ---", etiqueta)
        try:
            self.page.wait_for_timeout(1000)
            self.frame.get_by_role("link", name="Seleccionar", exact=True).nth(indice).click()
            self._procesar_detalle_actual(colegiado, etiqueta, clave)
        except Exception as exc:
            self._fallo(colegiado, etiqueta, clave, exc)

    def iniciar_modo_procedimientos(self) -> None:
        print("\n" + "="*60)
        print(" [PASO 2] A.R.I.A. (Procedimientos Únicos) lista en 'Asignar Precio - Proveedor'.")
        print(f" Servicios cargados desde {ARCHIVO_PROCEDIMIENTOS}: {len(self.procedimientos)}")
        for p in self.procedimientos:
            print(f"   - {p.servicio}  ->  {p.proveedor} (NIT {p.nit})")
        print(" Por favor:")
        print("   1. Ingresa el número de colegiado en la pantalla del CLINSYS.")
        print("   2. Ajusta las fechas si lo deseas y haz clic en 'Buscar' TÚ MISMO por primera vez.")
        print("   3. Asegúrate de que las órdenes ya aparezcan listadas.")
        print(" Cuando estés listo, ven aquí a la consola y presiona ENTER")
        print(" para que A.R.I.A. comience a procesar y vigilar continuamente.")
        print("="*60 + "\n")
        sys.stdout.flush()
        input()
        log.info("A.R.I.A. [Procedimientos Únicos] iniciada: monitoreo continuo activo...")

        # Forzar búsqueda inicial inmediata
        self.hacer_clic_buscar()

        colegiado_actual = "MANUAL"

        while True:
            try:
                procesadas = 0

                if self._en_detalle():
                    log.info("--- ¡Detectada orden única directa en pantalla! Analizando... ---")
                    try:
                        self._procesar_detalle_actual(colegiado_actual, "UNICA", None, buscar_despues=True)
                        procesadas += 1
                    except Exception as exc:
                        self._fallo(colegiado_actual, "UNICA", None, exc, buscar_despues=False)

                vistos: set = set()
                while True:
                    if self._en_detalle():
                        break
                    candidata = None
                    for i, texto in self.listar_filas():
                        clave = self._clave_fila(texto)
                        if clave in vistos:
                            continue
                        vistos.add(clave)
                        if "ORDENADO" not in norm(texto) or clave in self._cerradas:
                            continue
                        if not self._servicio_en_listado(texto):
                            self._cerradas.add(clave)      
                            self._registrar(colegiado_actual, self._num_orden(texto), "OMITIDA",
                                            f"Servicio no listado en {ARCHIVO_PROCEDIMIENTOS} ni es LABORATORIO (listado)")
                            continue
                        candidata = (i, texto, clave)
                        break
                    if candidata is None:
                        break
                    self.procesar_orden_unico(colegiado_actual, *candidata)
                    procesadas += 1

                if procesadas > 0:
                    log.info("Ciclo de procesamiento finalizado. Se procesaron %d órdenes.", procesadas)
                else:
                    log.info("No se encontraron órdenes pendientes en este momento.")

                log.info("A.R.I.A. entrando en modo de espera: revisando de nuevo en %d minutos...",
                         self.MINUTOS_ESPERA)
                transcurrido = 0
                while transcurrido < self.MINUTOS_ESPERA * 60:
                    self.page.wait_for_timeout(20000)
                    transcurrido += 20
                log.info("Tiempo de espera cumplido. Actualizando listado automáticamente...")
                self.hacer_clic_buscar()

            except Exception as exc:
                log.error("Ocurrió un error en el bucle de monitoreo continuo de A.R.I.A.: %s", exc)
                log.info("Reintentando el ciclo de monitoreo en 1 minuto...")
                self.page.wait_for_timeout(60000)


def main() -> int:
    aqui = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="A.R.I.A. - Asistente de Arancelamiento con Monitoreo Continuo en CLINSYS")
    ap.add_argument("--credenciales", type=Path, default=aqui / "CREDENCIALES.txt")
    ap.add_argument("--proveedor", default="DELTALAB",
                    help="Palabra clave del proveedor. Defecto: DELTALAB")
    ap.add_argument("--dry-run", action="store_true", help="Hace todo menos el clic en 'Arancelar documento'")
    ap.add_argument("--headless", action="store_true", help="Ejecuta el navegador en segundo plano sin mostrar ventanas")
    ap.add_argument("--optimizacion2", action="store_true", help="Modo Optimización2: bloquea imágenes/CSS/fuentes, flags extra de Chromium y viewport 1280x720")
    ap.add_argument("--procedimientos-unicos", action="store_true",
                    help="Modo Procedimientos Únicos: arancela los servicios de PROCEDIMIENTOS_EXTRA.txt con su proveedor y NIT")
    ap.add_argument("--salida", type=Path, default=aqui / "salida")
    args = ap.parse_args()

    args.salida.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(args.salida / "clinsys.log", encoding="utf-8")])

    procedimientos_extra: List[ProcedimientoExtra] = []
    if args.procedimientos_unicos:
        ruta_extra = aqui / ARCHIVO_PROCEDIMIENTOS
        try:
            procedimientos_extra = leer_procedimientos_extra(aqui / ARCHIVO_PROCEDIMIENTOS)
        except ValueError as exc:
            log.error("%s", exc)
            return 2
        log.info("[MODO PROCEDIMIENTOS ÚNICOS] %d servicio(s) cargado(s) desde SQLite", len(procedimientos_extra))

    cred = leer_credenciales(args.credenciales)
    if not cred.usuario or not cred.password:
        log.error("Faltan usuario o contraseña en CREDENCIALES.txt (o variables de entorno CLINSYS_USER / CLINSYS_PASS).")
        return 2

    clave = norm(args.proveedor)
    coinc = [(n, nit) for n, nit in cred.proveedores.items() if clave in norm(n)]
    if len(coinc) != 1:
        log.error("El proveedor '%s' debe coincidir con exactamente uno de los configurados.", args.proveedor)
        return 2
    nombre_prov, nit = coinc[0]
    log.info("Proveedor seleccionado: %s (NIT %s)%s", nombre_prov, nit, "  [DRY-RUN]" if args.dry_run else "")

    with sync_playwright() as p:
        flags_chrome = list(dict.fromkeys(
            (["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox", "--disable-extensions"] if args.headless else [])
            + (["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-extensions", "--disable-infobars", "--disable-software-rasterizer",
                "--disable-notifications"] if args.optimizacion2 else [])
        ))

        browser = p.chromium.launch(
            headless=args.headless,
            slow_mo=150,
            args=flags_chrome  
        )
        if args.optimizacion2:
            ctx = browser.new_context(viewport={"width": 1280, "height": 720}, locale="es-419")
            page = ctx.new_page()
        else:
            page = browser.new_page()

        if args.headless:
            page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ico}", lambda route: route.abort())
            log.info("[OPTIMIZACIÓN] Modo Headless activo: Bloqueo de recursos multimedia y CSS habilitado.")

        if args.optimizacion2 and not args.headless:
            page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ico}", lambda route: route.abort())
            log.info("[OPTIMIZACIÓN 2] Bloqueo de imágenes, CSS y fuentes habilitado.")

        if args.procedimientos_unicos:
            bot = ClinsysBotProcedimientos(page, cred, nombre_prov, nit, args.dry_run, args.salida,
                                         procedimientos_extra)
        else:
            bot = ClinsysBot(page, cred, nombre_prov, nit, args.dry_run, args.salida)
        
        try:
            bot.login_automatico()          
            bot.abrir_modulo()
            if args.procedimientos_unicos:
                bot.iniciar_modo_procedimientos()
            else:
                bot.iniciar_modo_manual_asistido()
        except Exception as e:
            log.error("Error critico durante la ejecucion: %s", e)
            bot._captura("error_critico")
            raise
        finally:
            csv_path = bot.guardar_csv()
            log.info("Resultados guardados en: %s", csv_path)
            print(f"\nProceso finalizado. Archivo de resultados: {csv_path}")
            print("Puedes cerrar el navegador cuando gustes.")
            input("Presiona ENTER para cerrar el navegador...")
            browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())