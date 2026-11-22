<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>MOD465 - Asignar Precio - Proveedor</title>
  <style>
    body { font-family: "Segoe UI", Arial, sans-serif; margin: 18px; color: #1e293b; background: #fff; }
    h3 { margin: 0 0 14px; color: #1e3a8a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; }
    .toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
    input[type="text"], select { padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; }
    input[type="button"], button {
      padding: 7px 14px; background: #2563eb; color: #fff; border: none; border-radius: 4px;
      cursor: pointer; font-size: 13px; font-weight: 600;
    }
    input[type="button"]:hover, button:hover { background: #1d4ed8; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }
    th { background: #f1f5f9; color: #334155; }
    tr:hover { background: #f8fafc; }
    a { color: #2563eb; font-weight: 600; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .card { border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px; background: #f8fafc; max-width: 780px; }
    .field { margin-bottom: 12px; }
    .field label { display: block; font-weight: 600; font-size: 13px; margin-bottom: 4px; }
    .badge-ord { color: #b45309; font-weight: 700; }
    .badge-imp { color: #15803d; font-weight: 700; }
    .actions { display: flex; gap: 10px; margin-top: 16px; align-items: center; }
    .btn-green { background: #16a34a; }
    .btn-green:hover { background: #15803d; }
    .btn-cancel { color: #dc2626; margin-left: auto; }
  </style>
</head>
<body>

  <h3>Módulo MOD-465 — Asignar Precio y Proveedor</h3>

  <!-- VISTA 1: LISTADO -->
  <div id="vista-listado">
    <div class="toolbar">
      <label>Colegiado:</label>
      <input type="text" id="txtColegiado" value="10001" style="width: 110px;">
      <input type="button" value="Buscar" onclick="renderTabla()">
    </div>

    <table>
      <thead>
        <tr>
          <th>Acción</th>
          <th>No. Orden</th>
          <th>Origen</th>
          <th>Estado</th>
          <th>Descripción</th>
        </tr>
      </thead>
      <tbody id="tbody-ordenes"></tbody>
    </table>
  </div>

  <!-- VISTA 2: DETALLE DE ORDEN -->
  <div id="vista-detalle" style="display: none;">
    <div class="card">
      <div class="field">
        <b>Estudio solicitado:</b> <span id="lbl-estudio"></span>
      </div>

      <div class="field">
        <label>Tipo de compra:</label>
        <select id="sel-tipo-compra">
          <option value="">-- Seleccione --</option>
          <option value="CD">COMPRA DIRECTA</option>
          <option value="LIC">LICITACIÓN</option>
        </select>
      </div>

      <div class="field">
        <label>Proveedor:</label>
        <select id="sel-proveedor" onchange="actualizarNit()">
          <option value="">-- Seleccione proveedor --</option>
        </select>
      </div>

      <div class="field">
        <label>Nit del proveedor:</label>
        <input type="text" id="txt-nit" readonly>
      </div>

      <div class="actions">
        <input type="button" value="Arancelar documento" onclick="arancelar()">
        <input type="button" id="btnCambiarEstado" class="btn-green" value="Cambiar a estado impreso" onclick="cambiarEstado()">
        <a href="javascript:__doPostBack('RapCommand$Toolbar1','Cancelar')" class="btn-cancel">Cancelar / Volver</a>
      </div>
    </div>
  </div>

  <script>
    // Órdenes de prueba (sin datos reales)
    const ordenes = [
      { id: "465101", estado: "ORDENADO", estudio: "LABORATORIO CLINICO - HEMATOLOGIA COMPLETA" },
      { id: "465102", estado: "ORDENADO", estudio: "LABORATORIO - PERFIL LIPIDICO Y GLUCOSA" },
      { id: "465103", estado: "ORDENADO", estudio: "CONSULTA DE CARDIOLOGIA PEDIATRICA" },
      { id: "465104", estado: "ORDENADO", estudio: "EVALUACION DE GASTROENTEROLOGIA" },
      { id: "465105", estado: "ORDENADO", estudio: "RESONANCIA MAGNETICA CEREBRAL SIMPLE" },
      { id: "465106", estado: "ORDENADO", estudio: "CONSULTA GENERAL DE SEGUIMIENTO" }
    ];

    // Proveedores ficticios sincronizados con CREDENCIALES.txt y PROCEDIMIENTOS_EXTRA.txt
    const proveedores = [
      { nombre: "ALFALAB", nit: "123456789" },
      { nombre: "DELTALAB", nit: "44556677" },
      { nombre: "EDIFICIO MÉDICO LOS ROBLES", nit: "109876543" },
      { nombre: "SALUD INTEGRAL, SOCIEDAD ANONIMA", nit: "81234567" },
      { nombre: "DIAGNÓSTICOS MÉDICOS DEL NORTE, S.A.", nit: "41234571" }
    ];

    let ordenActual = null;

    function cargarProveedores() {
      const sel = document.getElementById("sel-proveedor");
      sel.innerHTML = '<option value="">-- Seleccione proveedor --</option>';
      proveedores.forEach((p, idx) => {
        const opt = document.createElement("option");
        opt.value = idx;
        opt.textContent = `Proveedor: ${p.nombre}; VIGENCIA: 01/01/2026 - 31/12/2026`;
        sel.appendChild(opt);
      });
    }

 function renderTabla() {
      const tbody = document.getElementById("tbody-ordenes");
      tbody.innerHTML = "";

      // Ajusta el rango aquí (mínimo y máximo de estudios)
      const min = 2;
      const max = Math.min(15, ordenes.length);
      const cantidad = Math.floor(Math.random() * (max - min + 1)) + min;

      // Mezcla la lista y toma solo la cantidad aleatoria
      const ordenesAleatorias = [...ordenes]
        .sort(() => 0.5 - Math.random())
        .slice(0, cantidad);

      ordenesAleatorias.forEach((o) => {
        const tr = document.createElement("tr");
        const claseEstado = o.estado === "ORDENADO" ? "badge-ord" : "badge-imp";
        tr.innerHTML = `
          <td><a href="#" onclick="abrirDetalle('${o.id}'); return false;">Seleccionar</a></td>
          <td>${o.id} SISTEMA</td>
          <td>ADM-DEMO</td>
          <td class="${claseEstado}">${o.estado}</td>
          <td>${o.estudio}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    function abrirDetalle(id) {
      ordenActual = ordenes.find(o => o.id === id);
      document.getElementById("lbl-estudio").textContent = ordenActual.estudio;
      document.getElementById("sel-tipo-compra").value = "";
      document.getElementById("sel-proveedor").value = "";
      document.getElementById("txt-nit").value = "";
      document.getElementById("vista-listado").style.display = "none";
      document.getElementById("vista-detalle").style.display = "block";
    }

    function actualizarNit() {
      const idx = document.getElementById("sel-proveedor").value;
      document.getElementById("txt-nit").value = idx !== "" ? proveedores[idx].nit : "";
    }

    function arancelar() {
      alert("Arancelamiento realizado con éxito.");
    }

    function cambiarEstado() {
      if (ordenActual) ordenActual.estado = "IMPRESO";
      alert("Documento cambiado a estado impreso.");
    }

    function __doPostBack(target, arg) {
      if (arg === "Cancelar") {
        document.getElementById("vista-detalle").style.display = "none";
        document.getElementById("vista-listado").style.display = "block";
        renderTabla();
      }
    }

    cargarProveedores();
    renderTabla();
  </script>
</body>
</html>