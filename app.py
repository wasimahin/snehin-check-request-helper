#!/usr/bin/env python3
"""
Snehin Check Request Helper — V2.0.0
Modern dark UI. Core engine unchanged from v16.2.
"""

import os, re, sys, time, json, csv, traceback, threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import pdfplumber
import fitz
from PIL import Image, ImageTk


# ── Python guard ──────────────────────────────────────────────────────────────
if sys.version_info[:2] != (3, 13):
    raise RuntimeError(
        "Snehin Check Request Helper V2.0.0 requires Python 3.13.\n"
        "Please run: py -3.13 app.py"
    )

# ── App constants ─────────────────────────────────────────────────────────────
APP_NAME     = "Snehin Check Request Helper"
APP_VERSION  = "3.0.0"
APP_TITLE    = f"{APP_NAME}  ·  V{APP_VERSION}"
ERROR_LOG    = "last_error.log"
HISTORY_FILE = "invoice_history.json"
HOTKEY_NAME  = "f8"

@dataclass
class LineItem:
    raw_account: str = ''
    account_no:  str = ''
    department:  str = ''
    description: str = ''
    quantity:    str = '1'
    unit_cost:   str = ''
    object_code: str = ''


@dataclass
class InvoiceData:
    business:            str = 'ASI'
    vendor_name:         str = ''
    vendor_address:      str = ''
    city_state_zip:      str = ''
    request_date:        str = ''
    posting_date:        str = ''
    vendor_invoice_no:   str = ''
    due_date:            str = ''
    summary:             str = ''
    posting_description: str = ''
    lines: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  PARSER  (unchanged from v16.2)
# ─────────────────────────────────────────────────────────────────────────────

class Parser:
    @staticmethod
    def parse(pdf_path: str) -> InvoiceData:
        path = Path(pdf_path)
        with pdfplumber.open(str(path)) as pdf:
            first = pdf.pages[0]
            page1_text  = first.extract_text(x_tolerance=2, y_tolerance=2) or ''
            page1_words = first.extract_words(x_tolerance=1.5, y_tolerance=2,
                                              use_text_flow=True, keep_blank_chars=False)
            page_texts  = [pg.extract_text(x_tolerance=2, y_tolerance=2) or ''
                           for pg in pdf.pages]
        inv = InvoiceData()
        inv.business = Parser._detect_business(page1_words, page1_text)
        inv.vendor_name     = Parser._upper(Parser._extract_vendor_name(page1_words, first))
        inv.vendor_address  = Parser._upper(Parser._extract_vendor_address(page1_words, first))
        city     = Parser._upper(Parser._extract_city(page1_words, first))
        state    = Parser._upper(Parser._extract_state(page1_words, first))
        zip_code = Parser._upper(Parser._extract_zip(page1_words, first))
        inv.city_state_zip  = ', '.join(
            [x for x in [city, (' '.join([s for s in [state, zip_code] if s])).strip()] if x]
        ).strip(', ')
        inv.request_date        = Parser._normalize_date(Parser._extract_request_date(page1_words, first))
        inv.posting_date        = f"{datetime.now().month}/{datetime.now().day}/{datetime.now().year}".upper()
        inv.due_date            = Parser._find_due_date(page1_text).upper()
        inv.summary             = Parser._upper(Parser._extract_summary(page1_words, first, page_texts))
        # Vendor invoice no: prefer extracted invoice number, fall back to date-formatted string
        if inv.summary.startswith('INV #'):
            # Capture primary invoice number: first token after 'INV # '
            m = re.match(r'INV\s*#\s*([A-Z0-9][A-Z0-9\-]*)', inv.summary)
            inv.vendor_invoice_no = m.group(1) if m else Parser._make_invoice_no(inv.request_date).upper()
        else:
            inv.vendor_invoice_no = Parser._make_invoice_no(inv.request_date).upper()
        inv.posting_description = Parser._upper(Parser._build_posting_description(inv.vendor_name, inv.summary, page_texts))
        inv.lines               = Parser._extract_lines(first, page1_words, inv.posting_description)
        return inv

    @staticmethod
    def _upper(s):
        return (s or '').upper().strip()

    @staticmethod
    def _clean_plain(s):
        s = s or ''
        s = s.replace('\n', ' ')
        s = re.sub(r'\s+', ' ', s)
        return s.strip(' :\t')

    @staticmethod
    def _last_meaningful_line(text):
        SKIP = ('PAYABLE TO', 'PHONE NUMBER', 'E-MAIL TO CONTACT',
                'CONTACT FOR PICK', 'HOLD -', 'MAIL TO ABOVE', 'CHECK ONE', 'DEPOSIT TO')
        lines = [Parser._clean_plain(x) for x in (text or '').splitlines()]
        lines = [x for x in lines
                 if x
                 and not any(s in x.upper() for s in SKIP)
                 and not x.upper().startswith('NAME')
                 and not x.upper().startswith('DATE')]
        return lines[-1] if lines else Parser._clean_plain(text)

    @staticmethod
    def _clean_address_field(s):
        if not s: return s
        s = re.sub(r'^.*?(?:CONTACT\s+FOR\s+PICK-?UP:|CONTACT\s+FOR\s*)\s*', '', s, flags=re.I)
        s = re.sub(r'^(ONE:|HOLD\s*[-]|PHONE\s+NUMBER|E-MAIL)\s*', '', s, flags=re.I)
        s = re.sub(r'\S+@\S+\s*', '', s)
        return s.strip()

    @staticmethod
    def _detect_business(page1_words, page1_text):
        asi_marks = [w for w in page1_words
                     if w.get('text', '').strip().upper() == 'X'
                     and 210 <= float(w.get('x0', 0)) <= 320
                     and 90  <= float(w.get('top', 0)) <= 140]
        usu_marks = [w for w in page1_words
                     if w.get('text', '').strip().upper() in ('X', 'XX', '☒')
                     and 300 <= float(w.get('x0', 0)) <= 560
                     and 75  <= float(w.get('top', 0)) <= 155]
        if usu_marks and not asi_marks:
            return 'USU'
        if asi_marks and not usu_marks:
            return 'ASI'
        t = (page1_text or '').upper()
        if re.search(r'ASSOCIATED\s+STUDENTS\s+X\s+UNIVERSITY\s+STUDENT\s+UNION', t):
            return 'ASI'
        if re.search(r'ASSOCIATED\s+STUDENTS\s+UNIVERSITY\s+STUDENT\s+UNION\s+X', t):
            return 'USU'
        if 'UNIVERSITY STUDENT UNION' in t and 'ASSOCIATED STUDENTS' not in t:
            return 'USU'
        return 'ASI'

    @staticmethod
    def _find_word(words, text, x_max=None, x_min=None, top_min=None, top_max=None):
        for w in words:
            if w['text'].upper() == text.upper():
                if x_max is not None and w['x0'] > x_max: continue
                if x_min is not None and w['x0'] < x_min: continue
                if top_min is not None and w['top'] < top_min: continue
                if top_max is not None and w['top'] > top_max: continue
                return w
        return None

    @staticmethod
    def _anchors(words):
        return {
            'name':      Parser._find_word(words, 'Name',      x_max=130, top_min=105, top_max=180),
            'mailing':   Parser._find_word(words, 'Mailing',   x_max=130, top_min=125, top_max=220),
            'city':      Parser._find_word(words, 'City',      x_max=130, top_min=150, top_max=250),
            'state':     Parser._find_word(words, 'State',     x_min=300, top_min=150, top_max=250),
            'zip':       Parser._find_word(words, 'Zip',       x_min=400, top_min=150, top_max=250),
            'date':      Parser._find_word(words, 'Date',      x_min=360, top_min=100, top_max=215),
            'purpose':   Parser._find_word(words, 'Please',    x_max=130, top_min=370, top_max=475),
            'requested': Parser._find_word(words, 'Requested', x_max=130, top_min=450, top_max=580),
        }

    @staticmethod
    def _extract_crop_words(words, x0, top, x1, bottom):
        selected = [
            w['text'] for w in words
            if float(w['x0']) >= x0 and float(w['x1']) <= x1
            and float(w['top']) >= top and float(w['top']) <= bottom  # use top for lower bound (tolerates descenders)
        ]
        return Parser._clean_plain(' '.join(selected))

    @staticmethod
    def _extract_crop_text(page, bbox):
        try:
            return Parser._clean_plain(
                page.crop(bbox).extract_text(x_tolerance=1, y_tolerance=2) or '')
        except Exception:
            return ''

    @staticmethod
    def _extract_vendor_name(words, page):
        a = Parser._anchors(words)
        if a['name'] and a['mailing']:
            right = a['date']['x0'] - 6 if a.get('date') else 390
            txt = Parser._extract_crop_words(
                words, a['name']['x1'] + 4, a['name']['top'] - 2, right, a['mailing']['top'] - 2)
            txt = re.sub(r'^.*?PAYABLE TO[^:]+:', '', txt, flags=re.I).strip()
            if txt:
                return txt
        txt = Parser._extract_crop_text(page, (80, 108, 460, 180))
        txt = re.sub(r'^.*?PAYABLE TO[^:]+:', '', txt, flags=re.I).strip()
        return Parser._last_meaningful_line(txt)

    @staticmethod
    def _extract_vendor_address(words, page):
        a = Parser._anchors(words)
        if a['mailing'] and a['city']:
            txt = Parser._extract_crop_words(
                words, a['mailing']['x1'] + 4, a['mailing']['top'] - 2, 430, a['city']['top'] - 2)
            if txt:
                return txt
        return Parser._clean_address_field(Parser._last_meaningful_line(Parser._extract_crop_text(page, (80, 138, 440, 210))))

    @staticmethod
    def _extract_city(words, page):
        a = Parser._anchors(words)
        if a['city'] and a['state']:
            # Tight bottom boundary: stay within the city row (avoid "Check One:" below)
            y_bot = a['city']['bottom'] + 10
            txt = Parser._extract_crop_words(
                words, a['city']['x1'] + 4, a['city']['top'] - 2, a['state']['x0'] - 6, y_bot)
            if txt:
                return Parser._clean_address_field(txt)
        return Parser._clean_address_field(Parser._last_meaningful_line(Parser._extract_crop_text(page, (80, 162, 350, 245))))

    @staticmethod
    def _extract_state(words, page):
        a = Parser._anchors(words)
        if a['state'] and a['zip']:
            txt = Parser._extract_crop_words(
                words, a['state']['x1'] + 3, a['state']['top'] - 2, a['zip']['x0'] - 4, 220)
            if txt:
                return txt
        return Parser._clean_address_field(Parser._last_meaningful_line(Parser._extract_crop_text(page, (330, 162, 420, 245))))

    @staticmethod
    def _extract_zip(words, page):
        a = Parser._anchors(words)
        if a['zip']:
            txt = Parser._extract_crop_words(words, a['zip']['x1'] + 3, a['zip']['top'] - 2, 560, 220)
            if txt:
                return txt
        return Parser._clean_address_field(Parser._last_meaningful_line(Parser._extract_crop_text(page, (415, 162, 560, 245))))

    @staticmethod
    def _extract_request_date(words, page):
        a = Parser._anchors(words)
        if a['date'] and a['mailing'] and a['name']:
            txt = Parser._extract_crop_words(
                words, a['date']['x1'] + 4, a['name']['top'] - 2, 560, a['mailing']['top'] - 2)
            if txt:
                return txt
        return Parser._extract_crop_text(page, (400, 108, 565, 185))

    @staticmethod
    def _normalize_date(s):
        m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', s or '')
        if not m:
            return ''
        mm, dd, yy = m.groups()
        if len(yy) == 2:
            yy = '20' + yy
        return f'{int(mm):02d}/{int(dd):02d}/{int(yy):04d}'

    @staticmethod
    def _make_invoice_no(date_str):
        if not date_str:
            return ''
        mm, dd, yy = date_str.split('/')
        return f'{yy[-2:]}{mm}{dd}'

    @staticmethod
    def _find_due_date(page1_text):
        m = re.search(r'\bDUE\s+(\d{1,2}/\d{1,2}/\d{2,4})\b', page1_text, re.I)
        return Parser._normalize_date(m.group(1)) if m else ''

    @staticmethod
    def _clean_summary(s):
        s = Parser._clean_plain(s)
        s = re.sub(r'\bVOTE ON THE MOTION PASSES.*$', '', s, flags=re.I)
        s = re.sub(r'\bPLEASE\s+EXPEDITE\s+ASAP!?\b', '', s, flags=re.I)
        s = re.sub(r'\bASAP!?\b', '', s, flags=re.I)
        s = re.sub(r'\b-?\s*DUE\s+\d{1,2}/\d{1,2}/\d{2,4}\.?', '', s, flags=re.I)
        s = re.sub(r'\s+', ' ', s).strip(' .;:-')
        return s

    @staticmethod
    def _extract_summary(words, page, page_texts):
        purpose = Parser._extract_crop_text(page, (40, 375, 595, 515))
        purpose = re.sub(r'^.*?PLEASE DESCRIBE THE PURPOSE AND/OR USE OF THIS PURCHASE\.?',
                         '', purpose, flags=re.I)
        purpose = purpose.split('I certify', 1)[0].strip()
        purpose = Parser._clean_summary(purpose)
        refs = Parser._find_page1_invoice_refs(words, page)
        if refs:
            unique_refs = []
            bad_tokens = {'INVOICE', 'NUMBER', 'NO', 'DATE', 'AMOUNT', 'DUE'}
            for ref in refs:
                ref = Parser._clean_plain(ref).upper()
                compact = re.sub(r'[^A-Z0-9]', '', ref)
                if not ref: continue
                if ref in bad_tokens or compact in bad_tokens: continue
                if ref not in unique_refs:
                    unique_refs.append(ref)
            if unique_refs:
                return 'INV # ' + ', '.join(unique_refs)
        if purpose:
            return purpose
        return 'PAYMENT'

    @staticmethod
    def _scan_bottom_table_invoice_no(words) -> list:
        """Word-coordinate scan for invoice numbers in the bottom invoice table.
        Groups adjacent words on the same row (handles '07 - 2221133' split tokens).
        """
        BAD = {'INVOICE','NO','DATE','AMOUNT','DUE','FOR','OFFICE','USE','ONLY',
               'BALANCE','VERIFIED','PICKED','RELEASED','MAILED','BY','UP','DOWN',
               'DOCUMENTATION','RECEIPTS','INVOICES','CONTRACTS','COPIES','REVISED',
               'PRINT','NAME','PHONE','SIGNATURE'}
        # Collect candidate tokens in the Invoice No. column (leftmost, bottom table)
        cands = []
        for w in words:
            x0  = float(w['x0'])
            top = float(w['top'])
            text = w['text'].strip()
            if not (570 <= top <= 700 and 40 <= x0 <= 165):
                continue
            upper = text.upper()
            compact = re.sub(r'[^A-Z0-9]', '', upper)
            if upper in BAD or compact in BAD:
                continue
            if re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', text):   # date
                continue
            if re.match(r'^\$?[\d,]+\.\d{2}$', text):            # amount
                continue
            if not any(c.isdigit() for c in text):                 # pure alpha
                continue
            if not re.match(r'^[A-Z0-9\-]+$', upper):
                continue
            cands.append(w)

        if not cands:
            return []

        # Sort by (row, x) and group words within 8 px vertically
        cands.sort(key=lambda w: (float(w['top']), float(w['x0'])))
        results, row_toks, last_top = [], [], -99
        for w in cands:
            top = float(w['top'])
            if abs(top - last_top) > 8 and row_toks:
                # Commit completed row: join adjacent tokens with '-' separator
                joined  = '-'.join(t.strip('-') for t in row_toks)
                compact = re.sub(r'[^A-Z0-9]', '', joined.upper())
                if len(compact) >= 4 and joined.upper() not in results:
                    results.append(joined.upper())
                row_toks = [w['text'].strip()]
            else:
                row_toks.append(w['text'].strip())
            last_top = top

        if row_toks:
            joined  = '-'.join(t.strip('-') for t in row_toks)
            compact = re.sub(r'[^A-Z0-9]', '', joined.upper())
            if len(compact) >= 4 and joined.upper() not in results:
                results.append(joined.upper())

        return results

    @staticmethod
    def _find_page1_invoice_refs(words, page):
        refs = []
        # Word-based scan first (robust across all form variants)
        refs.extend(Parser._scan_bottom_table_invoice_no(words))
        # Crop-based regex scan as supplement (may fail on non-standard mediaboxes)
        for region in [(45, 580, 590, 760), (40, 375, 595, 515)]:
            try:
                refs.extend(Parser._extract_invoice_tokens(Parser._extract_crop_text(page, region)))
            except Exception:
                pass
        unique = []
        for ref in refs:
            ref = Parser._clean_plain(ref).upper()
            if ref and ref not in unique:
                unique.append(ref)
        return unique

    @staticmethod
    def _extract_invoice_tokens(text):
        text = text or ''
        found = []
        bad = {'INVOICE', 'NUMBER', 'NO', 'DATE', 'AMOUNT', 'DUE',
               'INVOICENO', 'INVOICENUMBER', 'INVOICEDATE'}
        patterns = [
            r'INVOICE\s*NO\.?\s*[:#-]?\s*([A-Z0-9\-]{4,})',
            r'INVOICE\s*NUMBER\s*[:#-]?\s*([A-Z0-9\-]{4,})',
            r'INV\s*#\s*([A-Z0-9\-]{4,})',
            r'INV\s*NO\.?\s*[:#-]?\s*([A-Z0-9\-]{4,})',
        ]
        for pat in patterns:
            for m in re.finditer(pat, text, re.I):
                token = Parser._clean_plain(m.group(1)).upper()
                compact = re.sub(r'[^A-Z0-9]', '', token)
                if not token: continue
                if token in bad or compact in bad: continue
                if any(token.startswith(x) for x in ('INVOICE', 'DATE', 'AMOUNT', 'DUE')): continue
                if token not in found:
                    found.append(token)
        return found

    @staticmethod
    def _build_posting_description(vendor, summary, page_texts):
        vendor = Parser._clean_plain(vendor).upper()
        chosen = Parser._clean_summary(summary or 'PAYMENT').upper().replace(':', '')
        prefix = f'{vendor} ; ' if vendor else ''
        max_len = max(0, 100 - len(prefix))
        if len(chosen) > max_len:
            trimmed = chosen[:max_len].rstrip()
            if ' ' in trimmed:
                trimmed = trimmed.rsplit(' ', 1)[0]
            chosen = trimmed
        return (prefix + chosen)[:100]

    @staticmethod
    def _cluster_word_rows(words, x0, x1, top0, top1, amount_only=False):
        selected = []
        for w in words:
            if not (x0 <= float(w['x0']) <= x1 and top0 <= float(w['top']) <= top1):
                continue
            txt = Parser._clean_plain(w['text'])
            if not txt: continue
            if txt.upper() in {'LINE', 'ACCOUNT', 'NUMBER', 'TOTAL', 'AMOUNT',
                                'TO', 'CHARGE', 'OF', 'THIS', 'PURCHASE.', 'PURCHASE'}:
                continue
            if amount_only and not re.search(r'\$?\d+[.,]\d{2}', txt): continue
            selected.append({'top': float(w['top']), 'x0': float(w['x0']), 'text': txt})
        selected.sort(key=lambda w: (w['top'], w['x0']))
        rows = []
        for w in selected:
            if rows and abs(rows[-1]['top'] - w['top']) <= 7:
                rows[-1]['items'].append(w['text'])
            else:
                rows.append({'top': w['top'], 'items': [w['text']]})
        return [(row['top'], Parser._clean_plain(' '.join(row['items']))) for row in rows]

    @staticmethod
    def _sanitize_line_account(raw):
        s = Parser._clean_plain(raw).upper()
        s = re.sub(r'LINE\s*[1-4]\s*ACCOUNT\s*NUMBER', '', s, flags=re.I)
        s = re.sub(r'AMOUNT\s*TO\s*CHARGE', '', s, flags=re.I)
        s = re.sub(r'TOTAL\s*AMOUNT\s*TO\s*CHARGE', '', s, flags=re.I)
        s = re.sub(r'\$[0-9,]+(?:\.\d{2})?', '', s)
        s = re.sub(r'[^A-Z0-9\- ]', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if re.fullmatch(r'(?:\d\s+){6,}\d', s):
            s = s.replace(' ', '')
        elif re.fullmatch(r'(?:[A-Z]\s+)?\d+(?:\s+\d+)+', s):
            s = s.replace(' ', '')
        s = s.replace(' ', '')
        return s.strip('-')

    @staticmethod
    def _extract_amount(s):
        m = re.search(r'([0-9,]+\.\d{2})', s or '')
        return m.group(1).replace(',', '') if m else ''

    @staticmethod
    def _looks_like_account_code(raw):
        s = (raw or '').upper().strip()
        if not s or 'TOTAL' in s or 'AMOUNT' in s:
            return False
        patterns = [
            r'^370-\d{4}-0\d$', r'^A-?\d{4}-\d$', r'^2850-A-?\d{4}-\d$',
            r'^8\d{2}-\d{4}-0\d$', r'^G\d{2}-\d{4}-\d$',
            r'^\d{4}-\d{4}(?:-\d{2})?$', r'^\d{8,10}$',
            r'^370\d{4}0\d$', r'^8\d{2}\d{4}0\d$',
        ]
        return any(re.fullmatch(p, s) for p in patterns)

    @staticmethod
    def _page1_line_rows(page, words):
        acct_rows = [Parser._sanitize_line_account(txt)
                     for _, txt in Parser._cluster_word_rows(words, 170, 445, 265, 395)]
        acct_rows = [a for a in acct_rows if a and Parser._looks_like_account_code(a)]
        amt_rows  = [Parser._extract_amount(txt)
                     for _, txt in Parser._cluster_word_rows(words, 440, 600, 265, 395, amount_only=True)]
        amt_rows  = [a for a in amt_rows if a]
        if not acct_rows or not amt_rows:
            fb_a, fb_m = [], []
            for y0, y1 in [(270, 298), (295, 322), (312, 338), (330, 355), (348, 375), (365, 395)]:
                raw = Parser._sanitize_line_account(Parser._extract_crop_text(page, (170, y0, 445, y1)))
                amt = Parser._extract_amount(Parser._extract_crop_text(page, (440, y0, 600, y1)))
                if raw and Parser._looks_like_account_code(raw): fb_a.append(raw)
                if amt: fb_m.append(amt)
            if fb_a: acct_rows = fb_a
            if fb_m: amt_rows  = fb_m
        total_amt = Parser._extract_amount(Parser._extract_crop_text(page, (490, 375, 600, 420)))
        if total_amt and amt_rows and len(amt_rows) > 1 and amt_rows[-1] == total_amt:
            amt_rows = amt_rows[:-1]
        # Also remove any amount equal to total if it appears (some forms repeat total inline)
        if total_amt and amt_rows and total_amt in amt_rows[1:]:
            amt_rows = [a for a in amt_rows if a != total_amt]
        if len(acct_rows) == 1 and len(amt_rows) > 1:
            acct_rows = acct_rows * len(amt_rows)
        rows = []
        n = min(max(len(acct_rows), len(amt_rows)), 4)
        carry = acct_rows[0] if len(set(acct_rows)) == 1 and acct_rows else ''
        for i in range(n):
            acct = acct_rows[i] if i < len(acct_rows) else carry
            amt  = amt_rows[i]  if i < len(amt_rows)  else ''
            if acct and amt:
                rows.append((acct, amt))
        return rows

    @staticmethod
    def _normalize_account(raw, amount, posting_description):
        s = raw.upper().replace('_', '-').replace('--', '-')
        if re.fullmatch(r'370\d{4}0\d', s):
            s = f'{s[:3]}-{s[3:7]}-{s[7:]}'
        elif re.fullmatch(r'8\d{2}\d{4}0\d', s):
            s = f'{s[:3]}-{s[3:7]}-{s[7:]}'
        elif re.fullmatch(r'\d{10}', s):
            s = f'{s[:4]}-{s[4:8]}-{s[8:]}'
        m = re.fullmatch(r'370-(\d{4})-(0\d)', s)
        if m:
            return LineItem(raw_account=s, account_no='2850', department='',
                            description=posting_description, unit_cost=amount,
                            object_code=f'A{m.group(1)}-{m.group(2)[1]}')
        m = re.fullmatch(r'A-?(\d{4})-(\d)', s)
        if m:
            return LineItem(raw_account=s, account_no='2850', department='',
                            description=posting_description, unit_cost=amount,
                            object_code=f'A{m.group(1)}-{m.group(2)}')
        m = re.fullmatch(r'2850-A-?(\d{4})-(\d)', s)
        if m:
            return LineItem(raw_account=s, account_no='2850', department='',
                            description=posting_description, unit_cost=amount,
                            object_code=f'A{m.group(1)}-{m.group(2)}')
        m = re.fullmatch(r'8(\d{2})-(\d{4})-(0\d)', s)
        if m:
            dept = '7101' if m.group(2).startswith('8') else '7103'
            return LineItem(raw_account=s, account_no='6440', department=dept,
                            description=posting_description, unit_cost=amount,
                            object_code=f'G{m.group(1)}-{m.group(2)}-{m.group(3)[1]}')
        m = re.fullmatch(r'G(\d{2})-(\d{4})-(\d)', s)
        if m:
            dept = '7101' if m.group(2).startswith('8') else '7103'
            return LineItem(raw_account=s, account_no='6440', department=dept,
                            description=posting_description, unit_cost=amount,
                            object_code=f'G{m.group(1)}-{m.group(2)}-{m.group(3)}')
        digits = re.sub(r'\D', '', s)
        if len(digits) >= 8:
            return LineItem(raw_account=s, account_no=digits[:4], department=digits[4:8],
                            description=posting_description, unit_cost=amount, object_code='')
        parts = [p for p in s.split('-') if p]
        if len(parts) >= 2:
            return LineItem(raw_account=s, account_no=parts[0], department=parts[1],
                            description=posting_description, unit_cost=amount, object_code='')
        return LineItem(raw_account=s, account_no=s, department='',
                        description=posting_description, unit_cost=amount, object_code='')

    @staticmethod
    def _extract_lines(first_page, words, posting_description):
        from collections import Counter
        results = []
        seen_count = Counter()
        for raw, amount in Parser._page1_line_rows(first_page, words):
            ln = Parser._normalize_account(raw, amount, posting_description)
            if not ln.account_no or ln.raw_account.upper().startswith('TOTAL'):
                continue
            key = (ln.raw_account, ln.account_no, ln.department, ln.unit_cost, ln.object_code)
            if seen_count[key] < 4:   # form has max 4 lines; allow duplicates up to 4
                seen_count[key] += 1
                results.append(ln)
        return results


# ─────────────────────────────────────────────────────────────────────────────
#  BC ENTRY  (unchanged from v16.2)
# ─────────────────────────────────────────────────────────────────────────────

class BCEntry:
    def __init__(self, invoice: InvoiceData, stop_event=None):
        import pyautogui
        self.pg = pyautogui
        self.pg.FAILSAFE = True
        self.pg.PAUSE = 0.03
        self.invoice   = invoice
        self.stop_event = stop_event

    def run(self):
        self._release_modifiers()
        self._check_stop()
        self._paste(self.invoice.vendor_name)
        self._check_stop()
        self.pg.press('enter')
        self._pause(2.25)
        self._press('tab', presses=6, interval=0.08)
        self._paste(self.invoice.vendor_invoice_no)
        self._press('tab')
        self._pause(0.08)
        self._paste(self.invoice.posting_description)
        self._pause(0.08)
        self._press('tab', presses=8, interval=0.08)
        for idx, line in enumerate(self.invoice.lines):
            self._paste(line.account_no);  self._check_stop(); self._press('enter'); self._pause(0.08)
            if line.department:
                self._paste(line.department)
            self._check_stop(); self._press('enter'); self._pause(0.08)
            self._paste(line.description);  self._check_stop(); self._press('enter'); self._pause(0.08)
            self._paste(line.quantity or '1'); self._check_stop(); self._press('enter'); self._pause(0.08)
            self._paste(line.unit_cost);   self._check_stop(); self._press('enter'); self._pause(0.08)
            if line.object_code:
                self._paste(line.object_code)
            if idx < len(self.invoice.lines) - 1:
                self._pause(1.0); self._press('enter'); self._pause(1.0); self._press('enter'); self._pause(1.0)

    def _paste(self, text):
        text = (text or '').upper()
        self._release_modifiers()
        if text:
            self.pg.write(text, interval=0.008)

    def _pause(self, secs=0.5):
        secs = max(0.0, float(secs))
        if secs == 0:
            self._check_stop(); return
        end = time.time() + secs
        while True:
            self._check_stop()
            remaining = end - time.time()
            if remaining <= 0: break
            time.sleep(min(0.05, remaining))

    def _press(self, key, presses=1, interval=0.0):
        self._check_stop()
        self.pg.press(key, presses=presses, interval=interval)
        self._check_stop()

    def _release_modifiers(self):
        for k in ('shift', 'ctrl', 'alt'):
            try: self.pg.keyUp(k)
            except Exception: pass

    def _check_stop(self):
        self._release_modifiers()
        if self.stop_event is not None and self.stop_event.is_set():
            raise RuntimeError('AUTOMATION STOPPED BY USER.')


# ─────────────────────────────────────────────────────────────────────────────
#  VENDOR ENTRY  (unchanged from v16.2)
# ─────────────────────────────────────────────────────────────────────────────

class VendorEntry:
    def __init__(self, invoice: InvoiceData):
        import pyautogui
        self.pg = pyautogui
        self.pg.FAILSAFE = True
        self.pg.PAUSE    = 0.03
        self.invoice     = invoice

    def run(self):
        vendor_name    = (self.invoice.vendor_name    or '').upper().strip()
        vendor_address = (self.invoice.vendor_address or '').upper().strip()
        zip_code       = self._extract_zip(self.invoice.city_state_zip)
        if not vendor_name:
            raise RuntimeError('NO VENDOR NAME AVAILABLE.')
        self.pg.write(vendor_name, interval=0.008)
        self.pg.press('tab', presses=7, interval=0.08)
        if vendor_address:
            self.pg.write(vendor_address, interval=0.008)
        self.pg.press('tab', presses=4, interval=0.08)
        if zip_code:
            self.pg.write(zip_code, interval=0.008)
        self.pg.press('enter')

    @staticmethod
    def _extract_zip(city_state_zip):
        m = re.search(r'\b(\d{5}(?:-\d{4})?)\b', city_state_zip or '')
        return m.group(1).upper() if m else ''


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_filename(value, fallback='UNKNOWN'):
    value = (value or '').strip().upper()
    value = re.sub(r'[\\/:*?"<>|]+', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value or fallback

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_history():
    try:
        if Path(HISTORY_FILE).exists():
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_history(entries):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(entries[-500:], f, indent=2)
    except Exception:
        pass

def _sanitize_filename(value, fallback='UNKNOWN'):
    value = (value or '').strip().upper()
    value = re.sub(r'[\\/:*?"<>|]+', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value or fallback

def _lerp_hex(c1, c2, t):
    """Interpolate between two hex colours (t: 0→1)."""
    def _p(h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    r1,g1,b1 = _p(c1); r2,g2,b2 = _p(c2)
    r = int(r1+(r2-r1)*t); g = int(g1+(g2-g1)*t); b = int(b1+(b2-b1)*t)
    return f'#{r:02x}{g:02x}{b:02x}'


# ─────────────────────────────────────────────────────────────────────────────
#  DESIGN TOKENS  V3
# ─────────────────────────────────────────────────────────────────────────────

D   = '#07070f'   # app background (deepest)
P   = '#0c0c18'   # panel / header / footer
S   = '#111122'   # surface — card/row bg
E   = '#171730'   # elevated surface
H   = '#1e1e38'   # hover
BD  = '#1a1a30'   # border
BDH = '#2a2a4a'   # border highlighted

G   = '#d4a829'   # gold — primary accent
GH  = '#eec040'   # gold hover
GD  = '#6a510d'   # gold dim
GG  = '#1a1408'   # gold glow bg

W   = '#eaeaf4'   # primary text
M   = '#8080aa'   # secondary text
DM  = '#38385a'   # muted / label text
HIT = '#c8c8e8'   # interactive text hover

OK  = '#22c55e'   # success green
OKD = '#0a2010'   # success bg
WN  = '#f59e0b'   # warning amber
WND = '#1e1500'   # warning bg
ER  = '#f87171'   # error red
ERD = '#1e0808'   # error bg

MULTI_LINE_KEYS = {'vendor_address', 'summary', 'posting_description'}

FIELD_DEFS = [
    ('Business',            'business'),
    ('Vendor name',         'vendor_name'),
    ('Mailing address',     'vendor_address'),
    ('City / State / ZIP',  'city_state_zip'),
    ('Request date',        'request_date'),
    ('Posting date',        'posting_date'),
    ('Invoice number',      'vendor_invoice_no'),
    ('Due date',            'due_date'),
    ('Summary',             'summary'),
    ('Posting description', 'posting_description'),
]

TREE_COLS  = ('raw_account','account_no','department','description',
              'quantity','unit_cost','object_code')
TREE_HEADS = {'raw_account':'RAW ACCOUNT','account_no':'ACCT',
              'department':'DEPT','description':'DESCRIPTION',
              'quantity':'QTY','unit_cost':'UNIT COST','object_code':'OBJ CODE'}
TREE_WIDTHS = {'raw_account':130,'account_no':70,'department':70,
               'description':280,'quantity':44,'unit_cost':80,'object_code':88}


# ─────────────────────────────────────────────────────────────────────────────
#  BASE FRAME / LABEL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fr(parent, bg=None, **kw):
    return tk.Frame(parent, bg=bg or P, bd=0, highlightthickness=0, **kw)

def sep(parent, bg=None, h=1):
    return tk.Frame(parent, bg=bg or BD, height=h, bd=0, highlightthickness=0)

def lbl(parent, text='', fg=None, bg=None, font=None, **kw):
    return tk.Label(parent, text=text, fg=fg or M, bg=bg or P,
                    font=font or ('Segoe UI', 9), bd=0, **kw)


# ─────────────────────────────────────────────────────────────────────────────
#  WIDGETS
# ─────────────────────────────────────────────────────────────────────────────

class Btn(tk.Canvas):
    """Rounded-rectangle button with hover, press, and style-switching."""

    _STYLES = {
        'primary':   (G,   GH,  D,   D  ),
        'secondary': (E,   H,   W,   HIT),
        'ghost':     (P,   E,   M,   W  ),
        'hotkey':    (GG,  H,   G,   GH ),
        'danger':    (ERD, ER,  ER,  D  ),
    }

    def __init__(self, parent, text, cmd=None, style='secondary',
                 w=110, h=28, parent_bg=None, **kw):
        self._cmd  = cmd
        self._text = text
        self._style = style
        pbg = parent_bg or parent.cget('bg')

        super().__init__(parent, width=w, height=h, bg=pbg,
                         bd=0, highlightthickness=0, cursor='hand2', **kw)

        self._w, self._h = w, h
        self._apply_style(style, hover=False)

        r = 5
        def rr(x1,y1,x2,y2):
            pts=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,
                 x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
            return self.create_polygon(pts, smooth=True,
                                       fill=self._bn, outline='')
        self._bgid = rr(1,1,w-1,h-1)
        self._txid = self.create_text(w//2, h//2, text=text,
                                      font=('Segoe UI', 9, 'bold'),
                                      fill=self._fn, anchor='center')

        self.bind('<Enter>',    lambda _: self._hover(True))
        self.bind('<Leave>',    lambda _: self._hover(False))
        self.bind('<Button-1>', self._press)

    def _apply_style(self, style, hover):
        bn,bh,fn,fh = self._STYLES.get(style, self._STYLES['secondary'])
        self._bn, self._bh, self._fn, self._fh = bn, bh, fn, fh

    def _hover(self, on):
        self.itemconfig(self._bgid, fill=self._bh if on else self._bn)
        self.itemconfig(self._txid, fill=self._fh if on else self._fn)

    def _press(self, _):
        # Brief flash: darken slightly then release
        self.itemconfig(self._bgid, fill=_lerp_hex(self._bn, D, 0.3))
        self.after(80, lambda: self.itemconfig(self._bgid, fill=self._bn))
        if self._cmd: self.after(10, self._cmd)

    def set_text(self, t):
        self._text = t
        self.itemconfig(self._txid, text=t)

    def set_style(self, style):
        self._style = style
        self._apply_style(style, False)
        self.itemconfig(self._bgid, fill=self._bn)
        self.itemconfig(self._txid, fill=self._fn)


class Spinner(tk.Canvas):
    """Rotating arc — shown while PDF is parsing."""

    def __init__(self, parent, size=36, bg=S, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=bg, bd=0, highlightthickness=0, **kw)
        self._angle = 0
        self._running = False
        self._arc = self.create_arc(5, 5, size-5, size-5,
                                     start=0, extent=250,
                                     outline=G, width=3, style='arc')
        self._after_id = None

    def start(self):
        self._running = True; self._tick()

    def stop(self):
        self._running = False
        if self._after_id:
            try: self.after_cancel(self._after_id)
            except: pass

    def _tick(self):
        if not self._running: return
        self._angle = (self._angle + 12) % 360
        self.itemconfig(self._arc, start=self._angle)
        self._after_id = self.after(18, self._tick)   # ~55 fps


class PulsingDot(tk.Canvas):
    """Status indicator dot with sinusoidal pulse animation."""

    def __init__(self, parent, bg=P, **kw):
        super().__init__(parent, width=10, height=10, bg=bg,
                         bd=0, highlightthickness=0, **kw)
        self._oval  = self.create_oval(1, 1, 9, 9, fill=DM, outline='')
        self._color = (DM, DM)      # (base, dim) — set by set_mode()
        self._pulsing  = False
        self._phase    = 0.0
        self._after_id = None

    def set_mode(self, color, pulse=False):
        """Set colour and start/stop pulse."""
        dim = _lerp_hex(color, D, 0.65)
        self._color = (color, dim)
        if pulse and not self._pulsing:
            self._pulsing = True
            self._animate()
        elif not pulse:
            self._pulsing = False
            self.itemconfig(self._oval, fill=color)

    def _animate(self):
        if not self._pulsing: return
        import math, time
        t   = time.time()
        a   = 0.5 + 0.5 * math.sin(2 * math.pi * t / 1.2)   # period 1.2 s
        c   = _lerp_hex(self._color[1], self._color[0], a)
        self.itemconfig(self._oval, fill=c)
        self._after_id = self.after(30, self._animate)        # ~33 fps

    def stop_pulse(self):
        self._pulsing = False


class ValBadge(tk.Frame):
    """Compact validation chip: LABEL above VALUE with flash animation."""

    def __init__(self, parent, label, **kw):
        super().__init__(parent, bg=S, padx=10, pady=5, **kw)
        self._bg = S
        tk.Label(self, text=label, fg=DM, bg=S,
                 font=('Segoe UI', 7, 'bold')).pack(anchor='w')
        self._v = tk.Label(self, text='—', fg=M, bg=S,
                           font=('Consolas', 9, 'bold'))
        self._v.pack(anchor='w')

    def set(self, text, ok=None):
        c = OK if ok is True else (ER if ok is False else WN)
        self._v.config(text=text, fg=c)
        # Brief background flash
        flash_bg = OKD if ok is True else (ERD if ok is False else WND)
        self.config(bg=flash_bg)
        for child in self.winfo_children():
            child.config(bg=flash_bg)
        self.after(220, self._reset_bg)

    def _reset_bg(self):
        self.config(bg=self._bg)
        for child in self.winfo_children():
            child.config(bg=self._bg)


class EditableField(tk.Frame):
    """Editable field row: label | entry (or text).
    Supports text selection, copy, paste. Gold border on focus.
    on_commit(value) is called when focus leaves.
    """

    def __init__(self, parent, label, multiline=False, shade=False,
                 on_commit=None, gold_value=False, **kw):
        bg = E if shade else S
        super().__init__(parent, bg=bg, **kw)
        self._bg_base   = bg
        self._multiline = multiline
        self._on_commit = on_commit
        self._gold_val  = gold_value
        self.configure(highlightthickness=1, highlightbackground=BD,
                        highlightcolor=G)

        # ── Label ─────────────────────────────────────────────────────────
        tk.Label(self, text=label, fg=DM, bg=bg,
                 font=('Segoe UI', 8), anchor='e',
                 width=18, padx=6, pady=5 if not multiline else 3
                 ).pack(side='left')
        tk.Frame(self, bg=BD, width=1).pack(side='left', fill='y', pady=3)

        # ── Value widget ───────────────────────────────────────────────────
        kw_w = dict(font=('Consolas', 9), fg=G if gold_value else W,
                    bg=bg, insertbackground=G, bd=0, relief='flat',
                    highlightthickness=0, selectbackground=GD,
                    selectforeground=W)
        if multiline:
            self._w = tk.Text(self, height=2, wrap='word',
                               padx=8, pady=4, **kw_w)
        else:
            self._w = tk.Entry(self, **kw_w)

        self._w.pack(side='left', fill='both', expand=True, padx=(0, 2))
        self._w.bind('<FocusIn>',  self._on_focus_in)
        self._w.bind('<FocusOut>', self._on_focus_out)
        if on_commit:
            self._w.bind('<KeyRelease>', lambda _: on_commit(self.get()))
            if multiline:
                self._w.bind('<<Modified>>', lambda _: on_commit(self.get()))

    # ── Focus ring ────────────────────────────────────────────────────────

    def _on_focus_in(self, _):
        self.configure(highlightbackground=G)

    def _on_focus_out(self, _):
        self.configure(highlightbackground=BD)
        if self._on_commit:
            self._on_commit(self.get())

    # ── Public API ────────────────────────────────────────────────────────

    def get(self):
        if self._multiline:
            return self._w.get('1.0', 'end-1c').strip()
        return self._w.get().strip()

    def set(self, text):
        val = (text or '').upper()
        if self._multiline:
            self._w.delete('1.0', 'end')
            self._w.insert('1.0', val)
        else:
            self._w.delete(0, 'end')
            self._w.insert(0, val)

    def flash(self, from_color=G, steps=14, interval=22):
        """Cascade shimmer: bg interpolates from_color → base over steps."""
        def _step(i):
            if i >= steps:
                self.set_bg(self._bg_base); return
            t  = i / steps
            t2 = 1 - (1-t)**2          # ease-out
            bg = _lerp_hex(from_color, self._bg_base, t2)
            self.set_bg(bg)
            self.after(interval, lambda: _step(i+1))
        _step(0)

    def set_bg(self, bg):
        self.config(bg=bg)
        self._w.config(bg=bg)
        for child in self.winfo_children():
            try: child.config(bg=bg)
            except: pass

    def reset_bg(self):
        self.set_bg(self._bg_base)


# ─────────────────────────────────────────────────────────────────────────────
#  APP — V3.0.0
# ─────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):

    # ──────────────────────────────────────────────────────────────── init ──

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=D)
        self.geometry('1620x1000')
        self.minsize(1320, 840)

        # state
        self.pdf_path       = tk.StringVar()
        self.status_var     = tk.StringVar(value='Ready')
        self.is_running     = False
        self.hotkey_enabled = True
        self._hotkey_mod    = None
        self.stop_event     = threading.Event()
        self.invoice        = InvoiceData()
        self._parsed_snap   = InvoiceData()   # snapshot for Reset
        self.username       = ''
        self._images        = []
        self._activity      = []
        self._history       = _load_history()

        # widget refs
        self._fedits    = {}          # key → EditableField
        self._badges    = {}          # label → ValBadge
        self._tree      = None
        self._pv_canvas = None
        self._pv_frame  = None
        self._pv_label  = None
        self._pv_img    = None
        self._pv_win    = None
        self._spinner   = None
        self._log_text  = None
        self._sdot      = None
        self._slabel    = None
        self._f8btn     = None
        self._user_lbl  = None
        self._total_lbl = None
        self._empty_lbl = None
        self._tree_edit = None    # active inline edit entry

        self._setup_tree_style()
        self._build()
        self.after(80, self._post_init)

    def _post_init(self):
        self.username = self._ask_username()
        self._setup_hotkey()
        self._log('Snehin V3.0.0 started')

    # ──────────────────────────────────────────────────── treeview style ──

    def _setup_tree_style(self):
        st = ttk.Style()
        try: st.theme_use('clam')
        except: pass
        st.configure('V3.Treeview',
                     background=S, foreground=W, rowheight=26,
                     fieldbackground=S, borderwidth=0,
                     font=('Consolas', 8))
        st.configure('V3.Treeview.Heading',
                     background=E, foreground=G, borderwidth=0,
                     font=('Segoe UI', 8, 'bold'), relief='flat', padding=(5,3))
        st.map('V3.Treeview',
               background=[('selected', H)], foreground=[('selected', W)])
        st.map('V3.Treeview.Heading', background=[('active', H)])
        st.layout('V3.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])

    # ─────────────────────────────────────────────────────────── BUILD ─────

    def _build(self):
        self._build_header()
        sep(self).pack(fill='x')
        self._build_actionbar()
        sep(self).pack(fill='x')
        self._build_filebar()
        sep(self).pack(fill='x')
        self._build_main()
        self._build_footer()

    # ── HEADER ──────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = fr(self, bg=P, height=64)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        # Gold left stripe
        tk.Frame(hdr, bg=G, width=4).pack(side='left', fill='y')

        # Brand block
        brand = fr(hdr, bg=P)
        brand.pack(side='left', padx=(14, 0), fill='y')
        tk.Label(brand, text='SNEHIN', fg=G, bg=P,
                 font=('Trebuchet MS', 22, 'bold')).pack(anchor='sw', pady=(10,0))
        tk.Label(brand, text='CHECK REQUEST HELPER', fg=GD, bg=P,
                 font=('Segoe UI', 7)).pack(anchor='nw', pady=(0,2))

        sep(hdr, bg=BD, h=1)   # not useful here; use a vertical frame
        fr(hdr, bg=BD, width=1).pack(side='left', fill='y', padx=14, pady=10)

        # Status cluster
        sc = fr(hdr, bg=P)
        sc.pack(side='left', fill='y')
        dot_row = fr(sc, bg=P)
        dot_row.pack(anchor='w', pady=(14, 0))
        self._sdot = PulsingDot(dot_row, bg=P)
        self._sdot.pack(side='left')
        self._slabel = tk.Label(dot_row, textvariable=self.status_var,
                                fg=M, bg=P, font=('Segoe UI', 9))
        self._slabel.pack(side='left', padx=5)
        tk.Label(sc, text=f'V{APP_VERSION}  ·  {datetime.now().strftime("%A, %B %d, %Y")}',
                 fg=DM, bg=P, font=('Segoe UI', 7)).pack(anchor='w', pady=(2,0))

        # Right — user + branding
        rc = fr(hdr, bg=P)
        rc.pack(side='right', padx=18, fill='y')
        self._user_lbl = tk.Label(rc, text='', fg=G, bg=P,
                                   font=('Segoe UI', 10, 'bold'))
        self._user_lbl.pack(anchor='e', pady=(10,0))
        tk.Label(rc, text='A Project by Wasi Mahin', fg=G, bg=P,
                 font=('Segoe UI', 9, 'italic')).pack(anchor='e', pady=(3,0))

    # ── ACTION BAR (left: BC/Vendor/Export/Log/F8) ──────────────────────────

    def _build_actionbar(self):
        bar = fr(self, bg=P, height=46)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        inner = fr(bar, bg=P)
        inner.pack(fill='both', expand=True, padx=14, pady=8)

        self._f8btn = Btn(inner, '⚡  BC Entry  (F8)',   self._action_bc,
                          style='primary', w=154, h=28, parent_bg=P)
        self._f8btn.pack(side='left', padx=(0, 4))

        self._v8btn = Btn(inner, '⚡  Vendor  (Alt+F8)',  self._action_vendor,
                          style='primary', w=154, h=28, parent_bg=P)
        self._v8btn.pack(side='left', padx=(0, 12))

        for text, cmd, w in [
            ('Export CSV', self.export_data,   80),
            ('Error Log',  self.open_error_log, 72),
        ]:
            Btn(inner, text, cmd, w=w, h=28, parent_bg=P).pack(side='left', padx=(0,4))

        fr(inner, bg=BD, width=1).pack(side='left', fill='y', padx=8, pady=2)

        self._hk_btn = Btn(inner, 'F8  ON', self.toggle_hotkey,
                           style='hotkey', w=72, h=28, parent_bg=P)
        self._hk_btn.pack(side='left')

    # ── FILE BAR (path left, all file buttons right) ────────────────────────

    def _build_filebar(self):
        bar = fr(self, bg=P, height=46)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        inner = fr(bar, bg=P)
        inner.pack(fill='both', expand=True, padx=14, pady=8)

        tk.Label(inner, text='PDF', fg=DM, bg=P,
                 font=('Segoe UI', 8, 'bold'), width=3).pack(side='left')

        # Path entry with animated focus ring
        ef = tk.Frame(inner, bg=BD, bd=0)
        ef.pack(side='left', fill='x', expand=True, padx=(6, 14))
        def _fi(_): ef.config(bg=G)
        def _fo(_): ef.config(bg=BD)
        self._path_entry = tk.Entry(ef, textvariable=self.pdf_path,
                                    font=('Consolas', 8), fg=M, bg=S,
                                    insertbackground=G, bd=0, relief='flat')
        self._path_entry.pack(fill='x', ipady=5, padx=1, pady=1)
        self._path_entry.bind('<FocusIn>',  _fi)
        self._path_entry.bind('<FocusOut>', _fo)

        # Right-side file buttons
        for text, cmd, w, style in [
            ('Browse',       self.choose_pdf,        62, 'primary'),
            ('Open PDF',     self.open_current_pdf,  70, 'secondary'),
            ('Rename',       self.rename_current_pdf,62, 'secondary'),
            ('Print',        self.print_first_page,  50, 'secondary'),
            ('Rename+Print', self.rename_then_print, 94, 'secondary'),
        ]:
            Btn(inner, text, cmd, style=style, w=w, h=28, parent_bg=P).pack(
                side='left', padx=(0, 4))

    # ── MAIN CONTENT ────────────────────────────────────────────────────────

    def _build_main(self):
        pane = tk.PanedWindow(self, orient='horizontal',
                              bg=D, sashwidth=4, sashrelief='flat',
                              bd=0, handlesize=0)
        pane.pack(fill='both', expand=True)
        self._build_data_pane(pane)
        self._build_preview_pane(pane)

    # ── DATA PANE ───────────────────────────────────────────────────────────

    def _build_data_pane(self, pane):
        outer = fr(pane, bg=D)
        pane.add(outer, minsize=720, stretch='always')

        # ── Validation strip + total chip ─────────────────────────────────
        vbar = fr(outer, bg=D)
        vbar.pack(fill='x', padx=12, pady=(10, 4))
        for label in ['Business', 'Vendor', 'Address', 'Lines', 'Total']:
            b = ValBadge(vbar, label)
            b.pack(side='left', padx=(0, 3))
            self._badges[label] = b

        # Computed total chip
        chip = tk.Frame(vbar, bg=S, highlightthickness=1,
                        highlightbackground=GD, highlightcolor=G)
        chip.pack(side='right')
        tk.Label(chip, text='COMPUTED TOTAL', fg=DM, bg=S,
                 font=('Segoe UI', 7, 'bold'), padx=8, pady=3).pack()
        self._total_lbl = tk.Label(chip, text='—', fg=G, bg=S,
                                    font=('Trebuchet MS', 14, 'bold'), padx=8, pady=2)
        self._total_lbl.pack()

        # ── Editable fields grid ──────────────────────────────────────────
        fbox = fr(outer, bg=D)
        fbox.pack(fill='x', padx=12, pady=(0, 6))
        fbox.configure(highlightthickness=1, highlightbackground=BD)

        fhdr = fr(fbox, bg=E)
        fhdr.pack(fill='x')
        tk.Label(fhdr, text='EXTRACTED FIELDS', fg=DM, bg=E,
                 font=('Segoe UI', 7, 'bold'), padx=10, pady=4).pack(side='left')
        # Reset to parsed button
        Btn(fhdr, '↺ Reset', self.reset_to_parsed,
            style='ghost', w=68, h=22, parent_bg=E).pack(side='right', padx=6, pady=3)
        sep(fbox).pack(fill='x')

        grid = fr(fbox, bg=D)
        grid.pack(fill='x')
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        half = len(FIELD_DEFS) // 2

        def _make_commit(key):
            def _commit(val):
                setattr(self.invoice, key, val.upper())
                if key == 'vendor_invoice_no': self._refresh_validation()
            return _commit

        for i, (label, key) in enumerate(FIELD_DEFS):
            col  = 0 if i < half else 1
            row  = i if i < half else i - half
            multi = key in MULTI_LINE_KEYS
            gold  = key in ('vendor_invoice_no', 'summary')
            ef = EditableField(grid, label,
                               multiline=multi,
                               shade=(row % 2 == 0),
                               on_commit=_make_commit(key),
                               gold_value=gold)
            ef.grid(row=row, column=col, sticky='ew',
                    padx=(0, 1 if col == 0 else 0))
            self._fedits[key] = ef

        # ── Line items (inline-editable treeview) ─────────────────────────
        lbox = fr(outer, bg=D)
        lbox.pack(fill='both', expand=True, padx=12, pady=(0, 10))
        lbox.configure(highlightthickness=1, highlightbackground=BD)

        lhdr = fr(lbox, bg=E)
        lhdr.pack(fill='x')
        tk.Label(lhdr, text='LINE ITEMS — double-click any cell to edit',
                 fg=DM, bg=E, font=('Segoe UI', 7, 'bold'),
                 padx=10, pady=4).pack(side='left')
        sep(lbox).pack(fill='x')

        tf = fr(lbox, bg=S)
        tf.pack(fill='both', expand=True)

        self._tree = ttk.Treeview(tf, columns=TREE_COLS, show='headings',
                                   height=7, style='V3.Treeview', selectmode='browse')
        for c in TREE_COLS:
            self._tree.heading(c, text=TREE_HEADS[c])
            self._tree.column(c, width=TREE_WIDTHS[c], anchor='w', minwidth=36)
        self._tree.tag_configure('odd',  background=S)
        self._tree.tag_configure('even', background=E)
        self._tree.bind('<Double-1>', self._tree_inline_edit)

        vsb = tk.Scrollbar(tf, orient='vertical', command=self._tree.yview,
                           bg=P, troughcolor=S, activebackground=GD,
                           bd=0, highlightthickness=0)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

    # ── PREVIEW PANE ────────────────────────────────────────────────────────

    def _build_preview_pane(self, pane):
        outer = fr(pane, bg=D)
        pane.add(outer, minsize=340, stretch='never')

        wrap = fr(outer, bg=D)
        wrap.pack(fill='both', expand=True, padx=(4,12), pady=(10,10))
        wrap.configure(highlightthickness=1, highlightbackground=BD)

        phdr = fr(wrap, bg=E)
        phdr.pack(fill='x')
        tk.Label(phdr, text='PAGE 1 PREVIEW', fg=DM, bg=E,
                 font=('Segoe UI', 7, 'bold'), padx=10, pady=4).pack(side='left')
        sep(wrap).pack(fill='x')

        # Spinner placeholder — shown while parsing
        self._spinner_frame = fr(wrap, bg=S)
        self._spinner_frame.pack(fill='x', pady=(6,0))
        self._spinner = Spinner(self._spinner_frame, size=36, bg=S)
        self._spinner.pack(pady=8)
        self._spinner_frame.pack_forget()   # hidden by default

        self._pv_canvas = tk.Canvas(wrap, bg=S, bd=0, highlightthickness=0)
        pvs = tk.Scrollbar(wrap, orient='vertical',
                           command=self._pv_canvas.yview,
                           bg=P, troughcolor=S, activebackground=GD,
                           bd=0, highlightthickness=0)
        self._pv_canvas.configure(yscrollcommand=pvs.set)
        self._pv_canvas.pack(side='left', fill='both', expand=True)
        pvs.pack(side='right', fill='y')

        self._pv_frame = fr(self._pv_canvas, bg=S)
        self._empty_lbl = tk.Label(self._pv_frame,
                                    text='Load a PDF to see preview',
                                    fg=DM, bg=S, font=('Segoe UI', 9))
        self._empty_lbl.pack(pady=60)
        self._pv_label = tk.Label(self._pv_frame, bg=S, bd=0, highlightthickness=0)
        self._pv_label.pack(fill='both', expand=True)
        self._pv_win = self._pv_canvas.create_window((0,0), window=self._pv_frame, anchor='nw')
        self._pv_frame.bind('<Configure>',  self._pv_cfg)
        self._pv_canvas.bind('<Configure>', self._pv_canvas_cfg)
        self._pv_canvas.bind('<MouseWheel>',
            lambda e: self._pv_canvas.yview_scroll(-1*(e.delta//120), 'units'))

    # ── FOOTER ──────────────────────────────────────────────────────────────

    def _build_footer(self):
        sep(self).pack(fill='x')
        foot = fr(self, bg=P, height=90)
        foot.pack(fill='x', side='bottom')
        foot.pack_propagate(False)

        top = fr(foot, bg=P)
        top.pack(fill='x', padx=14, pady=(5,0))
        tk.Label(top, text='ACTIVITY LOG', fg=DM, bg=P,
                 font=('Segoe UI', 7, 'bold')).pack(side='left')
        tk.Label(top, text='A Project by Wasi Mahin', fg=G, bg=P,
                 font=('Segoe UI', 8, 'italic')).pack(side='right')

        def _clear():
            if self._log_text:
                self._log_text.config(state='normal')
                self._log_text.delete('1.0', 'end')
                self._log_text.config(state='disabled')
            self._activity.clear()

        tk.Button(top, text='clear', fg=DM, bg=P, bd=0, cursor='hand2',
                  command=_clear, activebackground=P, activeforeground=W,
                  font=('Segoe UI', 7), relief='flat').pack(side='right', padx=8)

        la = fr(foot, bg=P)
        la.pack(fill='both', expand=True, padx=14, pady=(2,6))
        self._log_text = tk.Text(la, bg=P, fg=DM,
                                  font=('Consolas', 8), bd=0,
                                  highlightthickness=0, state='disabled',
                                  wrap='none', height=4, insertbackground=G)
        lsb = tk.Scrollbar(la, orient='vertical', command=self._log_text.yview,
                            bg=P, troughcolor=P, activebackground=GD,
                            bd=0, highlightthickness=0)
        self._log_text.configure(yscrollcommand=lsb.set)
        self._log_text.pack(side='left', fill='both', expand=True)
        lsb.pack(side='right', fill='y')
        for tag, fg in [('ts',DM),('ok',OK),('warn',WN),('err',ER),('msg',M)]:
            self._log_text.tag_configure(tag, foreground=fg)

    # ──────────────────────────────────────────────────── STATUS / LOG ──────

    def _setstatus(self, text, mode='idle'):
        self.status_var.set(text)
        palette = {'idle':OK, 'busy':G, 'warn':WN, 'err':ER}
        c = palette.get(mode, DM)
        if self._sdot:
            self._sdot.set_mode(c, pulse=(mode == 'busy'))
            if mode != 'busy':
                self._sdot.stop_pulse()

    def _log(self, msg, level='msg'):
        ts = datetime.now().strftime('%H:%M:%S')
        self._activity.append(f'[{ts}]  {msg}')
        if not self._log_text: return
        self._log_text.config(state='normal')
        self._log_text.insert('end', f'[{ts}]  ', 'ts')
        self._log_text.insert('end', msg + '\n', level)
        self._log_text.see('end')
        self._log_text.config(state='disabled')

    def _logerr(self, title, exc):
        with open(ERROR_LOG, 'w', encoding='utf-8') as f:
            f.write(f'{title}: {exc}\n\n{traceback.format_exc()}')

    # ──────────────────────────────────────────────────────── USERNAME ──────

    def _ask_username(self):
        name = ''
        while not name:
            v = simpledialog.askstring(APP_TITLE, 'Enter your username:', parent=self)
            if v is None: name = 'UNKNOWNUSER'; break
            name = _sanitize_filename(v, 'UNKNOWNUSER')
        if self._user_lbl:
            self._user_lbl.config(text=f'USER: {name}')
        self._setstatus(f'Ready  ·  {name}', 'idle')
        return name

    # ──────────────────────────────────────────────────────── HOTKEYS ───────

    def _setup_hotkey(self):
        # tkinter bindings (work when window focused)
        self.bind('<F8>',    lambda _: self._action_bc())
        self.bind('<Alt-F8>', lambda _: self._action_vendor())
        try:
            import keyboard
            self._hotkey_mod = keyboard
            keyboard.add_hotkey('f8',     self._action_bc)
            keyboard.add_hotkey('alt+f8', self._action_vendor)
            self._log('F8 / Alt+F8 hotkeys registered', 'ok')
        except Exception:
            self._hotkey_mod = None
            self._log('Global hotkeys unavailable (run as Administrator)', 'warn')

    def toggle_hotkey(self):
        if not self._hotkey_mod:
            messagebox.showwarning(APP_TITLE, 'Hotkey support unavailable.'); return
        self.hotkey_enabled = not self.hotkey_enabled
        st = 'ON' if self.hotkey_enabled else 'OFF'
        if self._hk_btn: self._hk_btn.set_text(f'F8  {st}')
        self._log(f'Hotkey F8 {st}')

    # ──────────────────────────────────────────────────── FILE ACTIONS ──────

    def choose_pdf(self):
        p = filedialog.askopenfilename(
            title='Select Check Request PDF',
            filetypes=[('PDF files', '*.pdf'), ('All files', '*.*')])
        if not p: return
        self.pdf_path.set(p)
        self._log(f'Loaded: {Path(p).name}')
        self.parse_current_pdf()

    def parse_current_pdf(self):
        p = self.pdf_path.get().strip()
        if not p: messagebox.showwarning(APP_TITLE, 'No PDF selected.'); return
        self._setstatus('Parsing…', 'busy')
        self._show_spinner(True)
        threading.Thread(target=self._parse_worker, args=(p,), daemon=True).start()

    def _parse_worker(self, p):
        try:
            inv = Parser.parse(p)
            self.after(0, lambda: self._on_parse_done(inv))
        except Exception as e:
            self.after(0, lambda: self._on_parse_error(e))

    def _on_parse_done(self, inv):
        import copy
        self.invoice      = inv
        self._parsed_snap = copy.deepcopy(inv)    # snapshot for reset
        self._refresh_fields(animate=True)
        self._refresh_lines()
        self._refresh_validation()
        self._check_duplicate()
        self.render_preview()
        self._show_spinner(False)
        self._setstatus(f'Parsed  ·  {inv.vendor_name or "—"}', 'idle')
        self._log(f'OK — {inv.vendor_name}', 'ok')

    def _on_parse_error(self, e):
        self._logerr('Parse failed', e)
        self._show_spinner(False)
        self._setstatus('Parse failed', 'err')
        self._log(f'Parse failed: {e}', 'err')
        messagebox.showerror(APP_TITLE, f'Failed to parse PDF:\n{e}')

    def _show_spinner(self, show):
        if not self._spinner: return
        if show:
            self._spinner_frame.pack(fill='x', pady=(6,0))
            self._spinner.start()
        else:
            self._spinner.stop()
            self._spinner_frame.pack_forget()

    def open_current_pdf(self):
        p = self.pdf_path.get().strip()
        if not p or not Path(p).exists():
            messagebox.showwarning(APP_TITLE, 'No PDF loaded.'); return
        os.startfile(str(Path(p).resolve()))
        self._log('Opened PDF')

    def rename_current_pdf(self):
        p = self.pdf_path.get().strip()
        if not p or not Path(p).exists():
            messagebox.showwarning(APP_TITLE, 'No PDF loaded.'); return
        biz    = _sanitize_filename(self.invoice.business,    'ASI')
        vendor = _sanitize_filename(self.invoice.vendor_name, 'UNKNOWN VENDOR')
        user   = _sanitize_filename(self.username,            'UNKNOWNUSER')
        now    = datetime.now()
        base   = f"{biz} {now.strftime('%Y-%m-%d')} {vendor} {now.strftime('%H-%M-%S')} {user}.pdf"
        dest = Path(p).with_name(base); ctr = 2
        while dest.exists():
            dest = Path(p).with_name(base.replace('.pdf', f' ({ctr}).pdf')); ctr += 1
        Path(p).rename(dest)
        self.pdf_path.set(str(dest))
        self._log(f'Renamed → {dest.name}', 'ok')
        self._setstatus(f'Renamed  ·  {dest.name}', 'idle')
        return dest

    def print_first_page(self, path=None):
        """Render page 1 as PNG and send to printer (no PDF viewer needed)."""
        p = path or self.pdf_path.get().strip()
        if not p or not Path(p).exists():
            messagebox.showwarning(APP_TITLE, 'No PDF loaded.'); return
        try:
            import tempfile, subprocess
            doc = fitz.open(p)
            pg  = doc.load_page(0)
            pix = pg.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            doc.close()
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False,
                                              prefix='snehin_p1_')
            tmp_path = tmp.name; tmp.close()
            img.save(tmp_path, 'PNG')
            printed = False
            try:
                safe = tmp_path.replace("'", "''")
                res  = subprocess.run(
                    ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive',
                     '-Command', f"Start-Process -FilePath '{safe}' -Verb Print -Wait"],
                    timeout=12, capture_output=True)
                if res.returncode == 0: printed = True
            except Exception: pass
            if not printed:
                try: os.startfile(tmp_path, 'print'); printed = True
                except OSError: pass
            if not printed:
                os.startfile(tmp_path)
                messagebox.showinfo(APP_TITLE, 'Page 1 opened.\nPress Ctrl+P to print.')
            self._log(f'Print sent  ·  {Path(p).name}', 'ok')
        except Exception as e:
            self._logerr('Print failed', e)
            self._log(f'Print failed: {e}', 'err')
            messagebox.showerror(APP_TITLE, f'Print failed:\n{e}')

    def rename_then_print(self):
        """Rename the PDF first, then print the renamed file."""
        p = self.pdf_path.get().strip()
        if not p or not Path(p).exists():
            messagebox.showwarning(APP_TITLE, 'No PDF loaded.'); return
        renamed = self.rename_current_pdf()
        if renamed:
            self.print_first_page(path=str(renamed))

    def render_preview(self):
        cur = self.pdf_path.get().strip()
        if not cur or not Path(cur).exists(): return
        try:
            doc  = fitz.open(cur)
            page = doc.load_page(0)
            pix  = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            img  = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            mw = 460
            if img.width > mw:
                img = img.resize((mw, int(img.height*mw/img.width)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._pv_img = photo
            if self._empty_lbl: self._empty_lbl.pack_forget()
            self._pv_label.config(image=photo)
            doc.close(); self._pv_cfg()
            self._log('Preview rendered', 'ok')
        except Exception as e:
            self._logerr('Preview failed', e)
            self._log(f'Preview error: {e}', 'warn')

    def export_data(self):
        if not self.invoice.vendor_name:
            messagebox.showwarning(APP_TITLE, 'No invoice loaded.'); return
        dest = filedialog.asksaveasfilename(
            defaultextension='.csv', filetypes=[('CSV','*.csv')],
            initialfile=f"export_{self.invoice.vendor_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        if not dest: return
        try:
            with open(dest, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['FIELD','VALUE'])
                for a in ['business','vendor_name','vendor_address','city_state_zip',
                           'request_date','posting_date','vendor_invoice_no',
                           'due_date','summary','posting_description']:
                    w.writerow([a.upper(), getattr(self.invoice, a, '')])
                w.writerow([]); w.writerow(['RAW_ACCOUNT','ACCT','DEPT','DESC','QTY','COST','OBJ'])
                for ln in self.invoice.lines:
                    w.writerow([ln.raw_account,ln.account_no,ln.department,
                                ln.description,ln.quantity,ln.unit_cost,ln.object_code])
                w.writerow([]); w.writerow(['ACTIVITY LOG'])
                for e in self._activity: w.writerow([e])
            self._log(f'Exported → {Path(dest).name}', 'ok')
            messagebox.showinfo(APP_TITLE, f'Exported:\n{Path(dest).name}')
        except Exception as e:
            self._log(f'Export failed: {e}', 'err')
            messagebox.showerror(APP_TITLE, f'Export failed:\n{e}')

    def open_error_log(self):
        if not Path(ERROR_LOG).exists():
            messagebox.showinfo(APP_TITLE, 'No error log yet.'); return
        os.startfile(str(Path(ERROR_LOG).resolve()))

    # ──────────────────────────────────────────── INLINE TREE EDITING ───────

    def _tree_inline_edit(self, event):
        """Double-click: open a floating Entry over the clicked cell."""
        row = self._tree.identify_row(event.y)
        col = self._tree.identify_column(event.x)
        if not row or not col: return

        # Destroy any existing inline editor
        if self._tree_edit:
            try: self._tree_edit.destroy()
            except: pass

        bbox = self._tree.bbox(row, col)
        if not bbox: return
        x, y, w, h = bbox
        col_idx  = int(col[1:]) - 1
        row_idx  = self._tree.index(row)
        cur_vals = list(self._tree.item(row, 'values'))
        cur_val  = cur_vals[col_idx] if col_idx < len(cur_vals) else ''

        entry = tk.Entry(self._tree, font=('Consolas', 8),
                         bg=H, fg=W, insertbackground=G,
                         bd=0, relief='flat', selectbackground=GD,
                         highlightthickness=1, highlightcolor=G)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, str(cur_val))
        entry.select_range(0, 'end')
        entry.focus_set()
        self._tree_edit = entry

        def _commit(e=None):
            new_val = entry.get()
            cur_vals[col_idx] = new_val
            self._tree.item(row, values=cur_vals)
            if row_idx < len(self.invoice.lines):
                setattr(self.invoice.lines[row_idx],
                        list(TREE_COLS)[col_idx], new_val)
            entry.destroy()
            self._tree_edit = None

        def _cancel(e=None):
            entry.destroy()
            self._tree_edit = None

        entry.bind('<Return>',   _commit)
        entry.bind('<Tab>',      _commit)
        entry.bind('<Escape>',   _cancel)
        entry.bind('<FocusOut>', _commit)

    # ──────────────────────────────────────────────────────── RESET ─────────

    def reset_to_parsed(self):
        """Restore all fields to the last parsed values."""
        import copy
        self.invoice = copy.deepcopy(self._parsed_snap)
        self._refresh_fields(animate=False)
        self._refresh_lines()
        self._refresh_validation()
        self._log('Fields reset to parsed values', 'warn')

    # ────────────────────────────────────────────────── DUPLICATE CHECK ─────

    def _check_duplicate(self):
        key = f"{self.invoice.vendor_name}|{self.invoice.vendor_invoice_no}"
        hits = [e for e in self._history if e.get('key') == key]
        if hits:
            last = hits[-1].get('timestamp', '?')
            self._log(f'Duplicate detected — last seen {last}', 'warn')
            messagebox.showwarning(APP_TITLE,
                f'Duplicate Invoice Detected\n\n'
                f'Vendor:  {self.invoice.vendor_name}\n'
                f'Invoice: {self.invoice.vendor_invoice_no}\n\n'
                f'Last processed: {last}\n\nVerify before entering.')
        else:
            self._history.append({'key': key,
                'vendor': self.invoice.vendor_name,
                'invoice': self.invoice.vendor_invoice_no,
                'timestamp': datetime.now().isoformat(timespec='seconds')})
            _save_history(self._history)

    # ─────────────────────────────────────────────────── AUTOMATION ─────────

    def _action_bc(self):
        if self.is_running:
            self.stop_event.set(); self._setstatus('Stop requested', 'warn'); return
        if not self.invoice.vendor_name:
            messagebox.showwarning(APP_TITLE, 'No invoice loaded.'); return
        self.stop_event.clear()
        threading.Thread(target=self._worker_bc, daemon=True).start()

    def _worker_bc(self):
        self.is_running = True
        try:
            self.after(0, lambda: self._setstatus('BC entry running  ·  F8 to stop', 'busy'))
            self.after(0, lambda: self._log('BC Entry started', 'ok'))
            BCEntry(self.invoice, stop_event=self.stop_event).run()
            self.after(0, lambda: self._setstatus('BC entry complete', 'idle'))
            self.after(0, lambda: self._log('BC Entry complete', 'ok'))
        except Exception as e:
            self._logerr('BC Entry failed', e)
            self.after(0, lambda: self._setstatus('BC entry failed', 'err'))
            self.after(0, lambda: self._log(f'BC Entry failed: {e}', 'err'))
            self.after(0, lambda: messagebox.showerror(APP_TITLE, f'Automation failed:\n{e}'))
        finally:
            self.is_running = False

    def _action_vendor(self):
        """Vendor entry — immediate, no delay, no popup."""
        if self.is_running: return
        if not self.invoice.vendor_name: return
        self.stop_event.clear()
        threading.Thread(target=self._worker_vendor, daemon=True).start()

    def _worker_vendor(self):
        self.is_running = True
        try:
            self.after(0, lambda: self._setstatus('Vendor entry running…', 'busy'))
            self.after(0, lambda: self._log('Vendor entry started', 'ok'))
            VendorEntry(self.invoice).run()
            self.after(0, lambda: self._setstatus('Vendor entry complete', 'idle'))
            self.after(0, lambda: self._log('Vendor entry complete', 'ok'))
        except Exception as e:
            self._logerr('Vendor entry failed', e)
            self.after(0, lambda: self._setstatus('Vendor entry failed', 'err'))
            self.after(0, lambda: self._log(f'Vendor entry failed: {e}', 'err'))
            self.after(0, lambda: messagebox.showerror(APP_TITLE, f'Vendor entry failed:\n{e}'))
        finally:
            self.is_running = False

    # ─────────────────────────────────────────────────────── UI REFRESH ─────

    def _refresh_fields(self, animate=True):
        inv = self.invoice
        items = list(self._fedits.items())

        def _set_one(idx):
            if idx >= len(items): return
            key, ef = items[idx]
            ef.set(getattr(inv, key, '') or '')
            if animate:
                ef.flash(from_color=G)
            if animate:
                self.after(40, lambda: _set_one(idx + 1))

        if animate:
            _set_one(0)
        else:
            for key, ef in items:
                ef.set(getattr(inv, key, '') or '')

    def _refresh_lines(self):
        for item in self._tree.get_children(): self._tree.delete(item)
        for i, ln in enumerate(self.invoice.lines):
            tag = 'even' if i % 2 == 0 else 'odd'
            self._tree.insert('', 'end', tags=(tag,),
                              values=(ln.raw_account, ln.account_no, ln.department,
                                      ln.description, ln.quantity, ln.unit_cost,
                                      ln.object_code))

    def _refresh_validation(self):
        inv = self.invoice
        biz_ok = inv.business in ('ASI','USU')
        self._badges['Business'].set(inv.business if biz_ok else 'CHECK', ok=biz_ok)
        v_ok = bool(inv.vendor_name)
        self._badges['Vendor'].set('OK' if v_ok else 'MISSING', ok=v_ok)
        a_ok = bool(inv.vendor_address and inv.city_state_zip)
        self._badges['Address'].set('OK' if a_ok else 'MISSING', ok=a_ok)
        n = len(inv.lines)
        self._badges['Lines'].set(str(n) if n else '0', ok=(n > 0))
        try:
            total = sum(float((ln.unit_cost or '0').replace(',','')) for ln in inv.lines)
            self._badges['Total'].set(f'${total:,.2f}', ok=(total > 0))
            if self._total_lbl: self._total_lbl.config(text=f'${total:,.2f}')
        except Exception:
            self._badges['Total'].set('ERROR', ok=False)

    # ──────────────────────────────────────────────────── PREVIEW ───────────

    def _pv_cfg(self, _=None):
        if self._pv_canvas:
            self._pv_canvas.configure(scrollregion=self._pv_canvas.bbox('all'))

    def _pv_canvas_cfg(self, e=None):
        if self._pv_canvas and self._pv_win and e:
            self._pv_canvas.itemconfigure(self._pv_win, width=e.width)


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    App().mainloop()
