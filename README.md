# Multi-Instance RPA Bot (A.R.I.A.)

Python and Playwright browser automation engine with a CustomTkinter control panel supporting up to 5 concurrent instances, headless mode, dry-run simulation, and SQLite/PDF reporting.

## 🚀 Key Features

* **Multi-Instance Execution:** Run and manage 1 to 5 concurrent browser workers via subprocess IPC from a single GUI.
* **CustomTkinter Control Panel:** Clean desktop interface to configure instances, toggle headless mode, and monitor execution.
* **Dry-Run & Mock Environment:** Includes a local mock web server (`test_page/`) to safely test automation workflows without touching production portals.
* **Data Persistence & Reporting:** Logs processed records in a local SQLite database with a built-in viewer and automated PDF report generation.
* **Flexible Rule Engine:** Supports standard workflows and custom procedural rules via external configuration files.

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Automation:** Playwright
* **GUI:** CustomTkinter
* **Database:** SQLite3
* **Reporting:** FPDF2

## 📂 Project Structure

```text
MULTI-INSTANCE-RPA-BOT/
├── src/
│   ├── aria_launcher_ui.py        # Main GUI launcher (CustomTkinter)
│   ├── clinsys_arancelar_...py    # Core Playwright RPA engine
│   ├── aria_db.py                 # SQLite database handler
│   ├── aria_db_ui.py              # Database viewer & reporting UI
│   ├── CREDENCIALES.example.txt   # Dummy credentials template for testing
│   └── PROCEDIMIENTOS_EXTRA.txt   # Custom procedural rules
├── test_page/
│   ├── run_mock.py                # Local HTTP server for testing
│   ├── index.html                 # Mock login portal
│   └── MOD465_ASIGNA...           # Mock orders table with randomized rows
├── requirements.txt
└── README.md