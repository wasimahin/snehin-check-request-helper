# Snehin Check Request Helper

A production Python desktop automation tool that eliminates manual data entry of vendor invoices into Microsoft Dynamics 365 Business Central.

> **Built at Associated Students, Inc. — California State University, Long Beach**  
> Deployed and running in production · March–April 2026

---

## The Problem

Every vendor invoice required opening a PDF, reading it, and manually typing every field into Business Central — vendor name, address, invoice number, account codes, line items — one field at a time, TAB-navigating through the ERP. **3–5 minutes per invoice. Error-prone. Repetitive.**

## The Solution

Snehin parses the PDF, extracts and normalizes all fields, validates the data, and enters everything into Business Central automatically via keystroke UI automation. No API. No ERP credentials required.

| | Before | After |
|---|---|---|
| Time per invoice | 3–5 minutes | 3–10 seconds |
| Reduction | — | **~96%** |
| API required | — | None |
| Validation | Manual | Pre-entry validation panel |
| Status | — | **Live in production** |

---

## Features

| Feature | Description |
|---|---|
| PDF Parsing | pdfplumber + PyMuPDF extract vendor details, account codes, line items, and totals from real-world inconsistently formatted invoices |
| Account Code Normalization | Deterministic mapping (e.g. `370-XXXX-0X` to Account 2850 + Code `AXXXX-X`) |
| Pre-entry Validation Panel | Flags anomalies before any data touches the ERP |
| Duplicate Invoice Detection | Persistent invoice history log prevents double entries |
| CSV Audit Trail | Every entry logged for accounting compliance |
| One-click File Rename | Stamps PDF with business unit, vendor, date, and user |
| Dark-mode GUI | Built with CustomTkinter — designed for non-technical financial staff |
| Page-1-only Parsing | Prevents data bleed from attached multi-page invoices |
| Zero API Required | Operates entirely through UI automation, no ERP credentials needed |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| PDF Extraction | pdfplumber, PyMuPDF (fitz) |
| UI Automation | pyautogui, keyboard |
| GUI Framework | CustomTkinter |
| ERP Target | Microsoft Dynamics 365 Business Central |
| Date Handling | python-dateutil |
| Clipboard | pyperclip |
| Image Processing | Pillow |

---

## Impact Metrics

- **~96%** processing time reduction — 3–5 minutes down to 3–10 seconds per invoice
- **Zero** API integrations required — pure UI automation
- **100%** deterministic — same parsing and normalization rules applied every time
- Handles **multi-line invoices** with automatic account code normalization
- Used daily by **non-technical financial staff** with zero training required

---

## Project Background

This tool was born from a real operational bottleneck. As Lead Business Office Representative at ASI CSULB, I noticed that check request processing consumed a significant portion of the team's time — not because the work was complex, but because it was entirely manual and repetitive.

The solution required:
- Reverse-engineering the exact TAB/ENTER navigation sequence Business Central requires
- Writing robust PDF parsers that handle real-world formatting inconsistencies
- Building a validation layer so errors are caught before they reach the ERP
- Designing a UI that non-technical staff could use without any training

---

## Author

**Wasi Mahin**  
Dual-major in MIS & Accountancy — California State University, Long Beach  
GPA: 3.87 · President's List every semester

[LinkedIn](https://linkedin.com/in/wasi-mahin) · [Portfolio](https://datacamp.com/portfolio/wasimahin)
