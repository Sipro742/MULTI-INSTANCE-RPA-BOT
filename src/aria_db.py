import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fpdf import FPDF

DB_PATH = Path(__file__).resolve().parent / "aria_data.db"


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def _pdf_safe(texto: str) -> str:
    return (texto or "").encode("latin-1", "replace").decode("latin-1")


def get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    with get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS credenciales (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                usuario TEXT NOT NULL,
                password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS colegiados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                numero TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proveedores_lab (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                nit TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS procedimientos_extra (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                servicio TEXT NOT NULL UNIQUE,
                proveedor TEXT NOT NULL,
                nit TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reportes_pdf (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_inicio TEXT NOT NULL,
                fecha_fin TEXT NOT NULL,
                duracion_texto TEXT NOT NULL,
                proveedor TEXT NOT NULL,
                modo TEXT NOT NULL,
                total_exito INTEGER NOT NULL,
                detalle_json TEXT NOT NULL,
                nombre_archivo TEXT NOT NULL,
                pdf_blob BLOB NOT NULL
            );
        """)
    migrar_desde_txt_si_vacio(db_path)


def migrar_desde_txt_si_vacio(db_path: Path = DB_PATH) -> None:
    """Importa automáticamente CREDENCIALES.txt y PROCEDIMIENTOS_EXTRA.txt si la BD está vacía."""
    base_dir = db_path.parent
    with get_conn(db_path) as conn:
        # 1. Migrar CREDENCIALES.txt
        tiene_cred = conn.execute("SELECT COUNT(*) FROM credenciales").fetchone()[0] > 0
        ruta_cred = base_dir / "CREDENCIALES.txt"
        if not tiene_cred and ruta_cred.is_file():
            raw = ruta_cred.read_bytes()
            try:
                texto = raw.decode("utf-8")
            except UnicodeDecodeError:
                texto = raw.decode("cp1252", errors="replace")

            usuario, password, seccion = "", "", None
            for linea in texto.splitlines():
                l = linea.strip()
                if not l:
                    continue
                bajo = _norm(l)
                if "COLEGIADOS" in bajo:
                    seccion = "col"
                    continue
                if "LABORATORIOS PROVEEDORES" in bajo:
                    seccion = "prov"
                    continue
                if m := re.match(r"USUARIO\s*:\s*(\S+)", l, re.I):
                    usuario = m.group(1)
                elif m := re.match(r"CONTRASE.A\s*:\s*(\S+)", l, re.I):
                    password = m.group(1)
                elif seccion == "col" and (m := re.match(r"^(.*?)\s+(\d{3,7})$", l)):
                    conn.execute(
                        "INSERT OR IGNORE INTO colegiados (nombre, numero) VALUES (?, ?)",
                        (m.group(1).strip(), m.group(2)),
                    )
                elif seccion == "prov" and (m := re.match(r"^(.*?)\s+NIT\s+(\d+)$", l, re.I)):
                    conn.execute(
                        "INSERT OR IGNORE INTO proveedores_lab (nombre, nit) VALUES (?, ?)",
                        (m.group(1).strip(), m.group(2)),
                    )
            if usuario or password:
                conn.execute(
                    "INSERT OR REPLACE INTO credenciales (id, usuario, password) VALUES (1, ?, ?)",
                    (usuario, password),
                )

        # 2. Migrar PROCEDIMIENTOS_EXTRA.txt
        tiene_proc = conn.execute("SELECT COUNT(*) FROM procedimientos_extra").fetchone()[0] > 0
        ruta_proc = base_dir / "PROCEDIMIENTOS_EXTRA.txt"
        if not tiene_proc and ruta_proc.is_file():
            raw = ruta_proc.read_bytes()
            try:
                texto = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                texto = raw.decode("cp1252", errors="replace")

            for linea in texto.splitlines():
                l = linea.strip()
                if not l or l.startswith("#"):
                    continue
                partes = [p.strip() for p in l.split("|")]
                if len(partes) == 3 and all(partes):
                    conn.execute(
                        "INSERT OR IGNORE INTO procedimientos_extra (servicio, proveedor, nit) VALUES (?, ?, ?)",
                        (partes[0], partes[1], partes[2]),
                    )


# ---------------- CRUD CREDENCIALES ----------------
def obtener_credenciales(db_path: Path = DB_PATH) -> Tuple[str, str]:
    init_db(db_path)
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT usuario, password FROM credenciales WHERE id = 1").fetchone()
        return (row["usuario"], row["password"]) if row else ("", "")


def guardar_credenciales(usuario: str, password: str, db_path: Path = DB_PATH) -> None:
    init_db(db_path)
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO credenciales (id, usuario, password) VALUES (1, ?, ?)",
            (usuario.strip(), password.strip()),
        )


# ---------------- CRUD COLEGIADOS ----------------
def listar_colegiados(db_path: Path = DB_PATH) -> Dict[str, str]:
    init_db(db_path)
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT nombre, numero FROM colegiados ORDER BY nombre").fetchall()
        return {r["nombre"]: r["numero"] for r in rows}


# ---------------- CRUD PROVEEDORES LAB ----------------
def listar_proveedores_lab(db_path: Path = DB_PATH) -> Dict[str, str]:
    init_db(db_path)
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT nombre, nit FROM proveedores_lab ORDER BY nombre").fetchall()
        return {r["nombre"]: r["nit"] for r in rows}


def guardar_proveedor_lab(nombre: str, nit: str, db_path: Path = DB_PATH) -> None:
    init_db(db_path)
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO proveedores_lab (nombre, nit) VALUES (?, ?)",
            (nombre.strip().upper(), nit.strip()),
        )


def eliminar_proveedor_lab(nombre: str, db_path: Path = DB_PATH) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM proveedores_lab WHERE nombre = ?", (nombre,))


# ---------------- CRUD PROCEDIMIENTOS EXTRA ----------------
def listar_procedimientos_extra(db_path: Path = DB_PATH) -> List[Tuple[str, str, str]]:
    init_db(db_path)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT servicio, proveedor, nit FROM procedimientos_extra ORDER BY servicio"
        ).fetchall()
        return [(r["servicio"], r["proveedor"], r["nit"]) for r in rows]


def guardar_procedimiento_extra(servicio: str, proveedor: str, nit: str, db_path: Path = DB_PATH) -> None:
    init_db(db_path)
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO procedimientos_extra (servicio, proveedor, nit) VALUES (?, ?, ?)",
            (servicio.strip().upper(), proveedor.strip(), nit.strip()),
        )


def eliminar_procedimiento_extra(servicio: str, db_path: Path = DB_PATH) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM procedimientos_extra WHERE servicio = ?", (servicio,))


# ---------------- GENERACIÓN Y ALMACENAMIENTO DE REPORTES PDF ----------------
def generar_y_guardar_reporte_pdf(
    fecha_inicio: datetime,
    fecha_fin: datetime,
    proveedor: str,
    modo: str,
    total_exito: int,
    desglose_por_tipo: Dict[str, int],
    desglose_por_estado: Dict[str, int],
    db_path: Path = DB_PATH,
) -> Tuple[int, str]:
    """Construye el PDF con resumen + subdivisión por tipo y lo guarda en SQLite."""
    init_db(db_path)
    segundos = max(0, int((fecha_fin - fecha_inicio).total_seconds()))
    horas, resto = divmod(segundos, 3600)
    minutos, segs = divmod(resto, 60)
    duracion_texto = f"{horas:02d}h {minutos:02d}m {segs:02d}s"

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Encabezado
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 10, _pdf_safe("A.R.I.A. - Reporte Operativo de Arancelamiento"), ln=True)
    pdf.set_draw_color(37, 99, 235)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # BLOQUE 1: Resumen de tiempo y órdenes exitosas
    pdf.set_fill_color(240, 244, 255)
    pdf.set_text_color(20, 20, 20)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe("1. Resumen de Ejecución"), ln=True, fill=True)
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    filas_resumen = [
        ("Hora de inicio:", fecha_inicio.strftime("%Y-%m-%d %H:%M:%S")),
        ("Hora de finalización:", fecha_fin.strftime("%Y-%m-%d %H:%M:%S")),
        ("Tiempo total de trabajo:", duracion_texto),
        ("Proveedor principal:", proveedor),
        ("Modo de ejecución:", modo),
        ("Órdenes aranceladas con éxito:", str(total_exito)),
    ]
    for etiqueta, valor in filas_resumen:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(65, 7, _pdf_safe(etiqueta), border=0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, _pdf_safe(valor), ln=True, border=0)

    pdf.ln(6)

    # BLOQUE 2: Subdivisión detallada de cuántas órdenes fueron en cada cosa
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe("2. Subdivisión y Detalle por Categoría / Servicio"), ln=True, fill=True)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(140, 7, _pdf_safe("Categoría / Servicio"), border=1)
    pdf.cell(50, 7, _pdf_safe("Cantidad"), border=1, ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    if desglose_por_tipo:
        for categoria, cant in sorted(desglose_por_tipo.items(), key=lambda x: (-x[1], x[0])):
            pdf.cell(140, 7, _pdf_safe(categoria[:75]), border=1)
            pdf.cell(50, 7, str(cant), border=1, ln=True, align="C")
    else:
        pdf.cell(190, 7, _pdf_safe("Sin órdenes registradas en esta sesión."), border=1, ln=True, align="C")

    pdf.ln(5)

    # Subtabla de estados generales (ARANCELADA, SIMULADA, OMITIDA, ERROR)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(140, 7, _pdf_safe("Estado del Registro"), border=1)
    pdf.cell(50, 7, _pdf_safe("Total"), border=1, ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    for estado, cant in desglose_por_estado.items():
        pdf.cell(140, 7, _pdf_safe(estado), border=1)
        pdf.cell(50, 7, str(cant), border=1, ln=True, align="C")

    pdf_bytes = bytes(pdf.output())
    nombre_archivo = f"reporte_aria_{fecha_inicio:%Y%m%d_%H%M%S}.pdf"
    detalle_json = json.dumps(
        {"por_tipo": desglose_por_tipo, "por_estado": desglose_por_estado},
        ensure_ascii=False,
    )

    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO reportes_pdf (
                fecha_inicio, fecha_fin, duracion_texto, proveedor, modo,
                total_exito, detalle_json, nombre_archivo, pdf_blob
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fecha_inicio.strftime("%Y-%m-%d %H:%M:%S"),
                fecha_fin.strftime("%Y-%m-%d %H:%M:%S"),
                duracion_texto,
                proveedor,
                modo,
                total_exito,
                detalle_json,
                nombre_archivo,
                sqlite3.Binary(pdf_bytes),
            ),
        )
        reporte_id = cur.lastrowid

    return reporte_id, nombre_archivo


def listar_reportes_pdf(db_path: Path = DB_PATH) -> List[sqlite3.Row]:
    init_db(db_path)
    with get_conn(db_path) as conn:
        return conn.execute(
            """
            SELECT id, fecha_inicio, fecha_fin, duracion_texto, proveedor, modo, total_exito, nombre_archivo
            FROM reportes_pdf
            ORDER BY id DESC
            """
        ).fetchall()


def exportar_reporte_pdf(reporte_id: int, carpeta_destino: Path, db_path: Path = DB_PATH) -> Optional[Path]:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT nombre_archivo, pdf_blob FROM reportes_pdf WHERE id = ?",
            (reporte_id,),
        ).fetchone()
        if not row:
            return None
        carpeta_destino.mkdir(parents=True, exist_ok=True)
        destino = carpeta_destino / row["nombre_archivo"]
        destino.write_bytes(row["pdf_blob"])
        return destino