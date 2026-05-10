# Snehin Check Request Helper

> **Production Python RPA tool built for Associated Students, Inc. (ASI) at California State University, Long Beach.**  
> Reduces invoice processing time by **~96%** — live in production with zero API integration.

---

## What It Does

The Snehin Check Request Helper is a desktop application that reads vendor invoice PDFs submitted through ASI's check request workflow, parses all relevant financial data from the document, validates it, and automatically enters it into **Microsoft Dynamics 365 Business Central** — field by field — through UI automation.

Previously, a staff member would manually read each invoice and type every field into Business Central. This tool eliminates that entirely.

**It is live in production at ASI CSULB today.**

---

## Impact

| Metric | Before | After |
|---|---|---|
| Time per invoice | 3–5 minutes | 3–10 seconds |
| Processing time reduction | — | **~96%** |
| API / ERP credentials required | — | **None** |
| Manual keystrokes per invoice | 200–400+ | ~3 (load, verify, run) |

---

## Features

- **PDF Parsing** — Extracts vendor name, invoice number, date, line items, and totals from check request PDFs using layout-preserving extraction (`pdfplumber`, `PyMuPDF`)
- **Duplicate Detection** — Flags invoices that have already been entered to prevent double-processing
- **Account Code Normalization** — Cleans and standardizes GL account codes before entry
- **Pre-Entry Validation Panel** — Displays all parsed fields for staff review before any automation runs
- **One-Click PDF Rename Workflow** — Renames the source file to a standardized naming convention after successful entry
- **CSV Audit Trail** — Exports a log of every processed invoice for reconciliation and audit purposes
- **Custom Dark-Mode GUI** — Steam/Discord-inspired dark interface built for non-technical staff
- **Live Status Log** — Color-coded in-app activity log for every parse, entry, and error event
- **Hotkey Trigger** — ALT+F8 starts or stops Business Central entry from anywhere on screen

---

## Tech Stack

| Layer | Tools |
|---|---|
| Language | Python 3.11+ |
| UI Framework | `customtkinter` (dark theme) |
| PDF Parsing | `pdfplumber`, `PyMuPDF (fitz)`, `pypdf` |
| UI Automation | `pyautogui`, `keyboard` |
| Clipboard | `pyperclip` |
| Image Rendering | `Pillow` |
| Target System | Microsoft Dynamics 365 Business Central |

---

## Business Central Entry Flow

For each parsed invoice, the bot executes this sequence automatically:

```
Vendor Name → [TAB] → Invoice Number → [TAB] → Invoice Date → [TAB]
→ GL Account → [TAB] → Department → [TAB] → Amount → [TAB]
→ Description → [TAB] → ... (configurable field order)
```

---

## How to Run

**Requirements:** Python 3.11 or newer, Windows

```bash
# Clone the repo
git clone https://github.com/wasimahin/snehin-check-request-helper.git
cd snehin-check-request-helper

# Run the launcher (installs dependencies automatically)
run.bat
```

The launcher detects your Python installation, verifies the version, auto-installs all required libraries, and launches the app.

**Manual install:**
```bash
pip install customtkinter pdfplumber pyautogui pyperclip pymupdf pillow pypdf keyboard
python snehin_bot.py
```

---

## Hotkeys

| Key | Action |
|---|---|
| `ALT+F8` | Start / Stop BC entry |

---

## Troubleshooting

| Issue | Check |
|---|---|
| App doesn't open | `startup_error.log` |
| Parsing fails | `snehin_errors.log` |
| ALT+F8 not working | Install `keyboard` package; run as admin if needed |
| Wrong field populated | Adjust field tab order in Settings |

---

## Project Context

Built independently as part of my role as **Lead Business Office Representative at ASI CSULB**, where I oversee financial documentation for 500+ registered campus organizations. This tool is one of two production Python automation systems I engineered for the office — the other being the **[BC Journal Entry Bot](https://github.com/wasimahin/bc-journal-entry-bot)**.

Both tools run live with zero API integration, operating entirely through UI automation against Microsoft Dynamics 365 Business Central.

---

## Author

**Wasi Mahin**  
Dual-Major: Management Information Systems & Accountancy | CSULB  
[LinkedIn](https://linkedin.com/in/wasi-mahin) · [GitHub](https://github.com/wasimahin) · wasimahin@gmail.com
