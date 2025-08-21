#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR PDF → TXT / DOCX (+ PDF interrogeable), gestion des doubles pages, détection gouttière améliorée
- Gouttière : seuillage Otsu + projection verticale lissée
- Fenêtre centrale ajustable + lissage ajustable
- Bouton d'aperçu de la coupe sur la première page
"""

import io
import os
import sys
import threading
import shutil
import re
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import fitz  # PyMuPDF
except Exception as e:
    raise SystemExit("PyMuPDF (fitz) requis. Installez-le via 'pip install pymupdf'.") from e

try:
    from PIL import Image, ImageOps, ImageFilter, ImageTk, ImageDraw
except Exception as e:
    raise SystemExit("Pillow requis. Installez-le via 'pip install pillow'.") from e

try:
    import pytesseract
except Exception as e:
    raise SystemExit("pytesseract requis. Installez-le via 'pip install pytesseract'.") from e

try:
    from docx import Document
    from docx.shared import Pt
except Exception:
    Document = None


# ====== Utilitaires ======

def configure_tesseract(explicit_path=None):
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    which = shutil.which("tesseract")
    if which:
        candidates.append(which)
    candidates += [
        r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
    ]
    seen = set(); ordered = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c); ordered.append(c)
    for c in ordered:
        if os.path.isfile(c):
            pytesseract.pytesseract.tesseract_cmd = c
            return c
    return None


def pil_from_fitz_pixmap(pix):
    data = pix.tobytes("png")
    return Image.open(io.BytesIO(data)).convert("RGB")


def otsu_thresh(arr):
    import numpy as np
    hist, _ = np.histogram(arr.flatten(), bins=256, range=(0,255))
    total = arr.size
    sum_total = (hist * np.arange(256)).sum()
    sumB = 0.0; wB = 0.0; varMax = 0.0; thresh = 0
    for t in range(256):
        wB += hist[t]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sumB += t * hist[t]
        mB = sumB / wB
        mF = (sum_total - sumB) / wF
        var_between = wB * wF * (mB - mF) ** 2
        if var_between > varMax:
            varMax = var_between
            thresh = t
    return thresh


def find_gutter_x(img, central_frac=0.4, smooth_px=25):
    """Détecte la gouttière près du centre par projection verticale lissée.
    central_frac : proportion du centre utilisée (0.2-0.8)
    smooth_px    : largeur de lissage (en pixels) sur l'image de travail
    """
    import numpy as np
    g = img.convert("L")
    g = ImageOps.autocontrast(g)
    g = g.filter(ImageFilter.MedianFilter(3))
    a = np.array(g, dtype=np.uint8)
    t = otsu_thresh(a)
    bw = (a < t).astype(np.uint8)  # 1 = encre, 0 = fond
    h, w = bw.shape
    top = int(h * 0.05); bottom = int(h * 0.95)
    work = bw[top:bottom, :]
    col = work.sum(axis=0).astype(float)
    # lissage par convolution
    k = max(3, int(smooth_px) | 1)  # impair
    kern = np.ones(k, dtype=float) / k
    sm = np.convolve(col, kern, mode="same")
    # recherche dans une bande centrale
    cf = float(central_frac)
    cf = min(0.9, max(0.1, cf))
    left = int(w * (0.5 - cf/2))
    right = int(w * (0.5 + cf/2))
    idx = sm[left:right].argmin()
    cut_x = left + int(idx)
    margin = max(10, int(w * 0.01))
    cut_x = max(margin, min(w - margin, cut_x))
    return cut_x


def split_double_page(img, mode="auto", central_frac=0.4, smooth_px=25):
    w, h = img.size
    if mode == "half":
        gx = w // 2
    else:
        # Heuristique : seulement si largeur/hauteur >= 1.28
        if (w / h) < 1.28:
            return [img]
        gx = find_gutter_x(img, central_frac=central_frac, smooth_px=smooth_px)
    left = img.crop((0, 0, gx, h))
    right = img.crop((gx, 0, w, h))
    return [left, right]


def postprocess_text(txt: str) -> str:
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    txt = re.sub(r"(\w)[\-­]\n(\w)", r"\1\2", txt)
    txt = re.sub(r"(?<!\n)\n(?!\n)", " ", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    return txt.strip()


# ====== Application ======

class OCRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OCR PDF → TXT / DOCX (+ PDF interrogeable)")
        self.geometry("880x700")
        self.minsize(860, 680)

        self.pdf_path_var = tk.StringVar()
        self.out_dir_var = tk.StringVar()
        self.lang_var = tk.StringVar(value="fra+eng")
        self.res_dpi_var = tk.IntVar(value=300)
        self.format_txt_var = tk.BooleanVar(value=True)
        self.format_docx_var = tk.BooleanVar(value=True if Document is not None else False)
        self.format_pdf_var = tk.BooleanVar(value=False)
        self.keep_pagebreaks_var = tk.BooleanVar(value=True)
        self.page_range_var = tk.StringVar(value="all")
        self.tess_config_var = tk.StringVar(value="--oem 1 --psm 6")

        # Doublage
        self.split_doubles_var = tk.BooleanVar(value=True)
        self.split_mode_var = tk.StringVar(value="auto")
        self.central_frac_var = tk.DoubleVar(value=0.4)   # 40% du centre
        self.smooth_px_var = tk.IntVar(value=25)

        self._worker = None
        self._build_ui()

    def _build_ui(self):
        pad = {'padx': 10, 'pady': 6}
        frm = ttk.Frame(self); frm.pack(fill="both", expand=True)

        # Ligne PDF
        row1 = ttk.Frame(frm); row1.pack(fill="x", **pad)
        ttk.Label(row1, text="Fichier PDF :").pack(side="left")
        ttk.Entry(row1, textvariable=self.pdf_path_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row1, text="Parcourir…", command=self._browse_pdf).pack(side="left")

        # Dossier sortie
        row2 = ttk.Frame(frm); row2.pack(fill="x", **pad)
        ttk.Label(row2, text="Dossier de sortie :").pack(side="left")
        ttk.Entry(row2, textvariable=self.out_dir_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row2, text="Choisir…", command=self._browse_outdir).pack(side="left")

        # Paramètres OCR
        row3 = ttk.LabelFrame(frm, text="Paramètres OCR"); row3.pack(fill="x", **pad)
        ttk.Label(row3, text="Langues (Tesseract):").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(row3, textvariable=self.lang_var, width=20).grid(row=0, column=1, sticky="w")
        ttk.Label(row3, text="Config Tesseract :").grid(row=0, column=2, sticky="e", padx=8)
        ttk.Entry(row3, textvariable=self.tess_config_var, width=28).grid(row=0, column=3, sticky="w")
        ttk.Label(row3, text="Résolution (DPI) :").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Spinbox(row3, from_=150, to=600, increment=25, textvariable=self.res_dpi_var, width=7).grid(row=1, column=1, sticky="w")
        ttk.Label(row3, text="Pages (ex. 'all', '1-5', '1-3,6,8-') :").grid(row=1, column=2, sticky="e", padx=8)
        ttk.Entry(row3, textvariable=self.page_range_var, width=28).grid(row=1, column=3, sticky="w")
        ttk.Checkbutton(row3, text="Insérer des sauts de page", variable=self.keep_pagebreaks_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        # Formats
        row4 = ttk.LabelFrame(frm, text="Format de sortie"); row4.pack(fill="x", **pad)
        ttk.Checkbutton(row4, text="Texte (.txt)", variable=self.format_txt_var).pack(side="left", padx=8, pady=4)
        ttk.Checkbutton(row4, text="Word (.docx)", variable=self.format_docx_var, state=("normal" if Document is not None else "disabled")).pack(side="left", padx=8, pady=4)
        ttk.Checkbutton(row4, text="PDF interrogeable (.pdf)", variable=self.format_pdf_var).pack(side="left", padx=8, pady=4)

        # Doubles pages
        row4b = ttk.LabelFrame(frm, text="Doubles pages"); row4b.pack(fill="x", **pad)
        ttk.Checkbutton(row4b, text="Couper les doubles pages", variable=self.split_doubles_var).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(row4b, text="Méthode :").grid(row=0, column=1, sticky="e")
        ttk.Combobox(row4b, textvariable=self.split_mode_var, width=10, state="readonly", values=["auto", "half"]).grid(row=0, column=2, sticky="w")
        ttk.Label(row4b, text="Fenêtre centrale (0.2–0.8) :").grid(row=1, column=1, sticky="e")
        ttk.Spinbox(row4b, from_=0.2, to=0.8, increment=0.05, textvariable=self.central_frac_var, width=6).grid(row=1, column=2, sticky="w")
        ttk.Label(row4b, text="Lissage (px) :").grid(row=1, column=3, sticky="e")
        ttk.Spinbox(row4b, from_=5, to=101, increment=2, textvariable=self.smooth_px_var, width=6).grid(row=1, column=4, sticky="w")
        ttk.Button(row4b, text="Aperçu découpe (p.1)", command=self.preview_cut).grid(row=0, column=3, columnspan=2, padx=12)

        # Progression
        row5 = ttk.Frame(frm); row5.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(row5, mode="determinate"); self.progress.pack(fill="x", padx=4)
        self.status_var = tk.StringVar(value="Prêt.")
        ttk.Label(row5, textvariable=self.status_var).pack(anchor="w", padx=4, pady=2)

        # Boutons
        row6 = ttk.Frame(frm); row6.pack(fill="x", **pad)
        ttk.Button(row6, text="Démarrer l’OCR", command=self.start_ocr).pack(side="left", padx=4)
        ttk.Button(row6, text="Ouvrir le dossier", command=self._open_outdir).pack(side="left", padx=4)
        ttk.Button(row6, text="Quitter", command=self.destroy).pack(side="right", padx=4)

        # Journal
        row7 = ttk.LabelFrame(frm, text="Journal"); row7.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(row7, height=12, wrap="word"); self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def logln(self, text):
        self.log.insert("end", text + "\n"); self.log.see("end"); self.update_idletasks()

    def set_status(self, text):
        self.status_var.set(text); self.update_idletasks()

    def _browse_pdf(self):
        path = filedialog.askopenfilename(title="Choisir un PDF", filetypes=[("PDF", "*.pdf"), ("Tous les fichiers", "*.*")])
        if path:
            self.pdf_path_var.set(path); self.out_dir_var.set(os.path.dirname(path))

    def _browse_outdir(self):
        d = filedialog.askdirectory(title="Choisir un dossier de sortie")
        if d: self.out_dir_var.set(d)

    def _open_outdir(self):
        d = self.out_dir_var.get().strip()
        if not d:
            messagebox.showinfo("Dossier", "Aucun dossier de sortie défini."); return
        try:
            if sys.platform.startswith('win'): os.startfile(d)
            elif sys.platform == 'darwin': os.system(f'open "{d}"')
            else: os.system(f'xdg-open "{d}"')
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d’ouvrir le dossier:\n{e}")

    def _parse_page_ranges(self, pr_str, nb_pages):
        pr_str = pr_str.strip().lower()
        if pr_str in ("all", "", "*"): return list(range(nb_pages))
        indices = set()
        for p in [x.strip() for x in pr_str.split(",") if x.strip()]:
            if "-" in p:
                a, b = p.split("-", 1); a=a.strip(); b=b.strip()
                start = int(a) if a else 1; end = int(b) if b else nb_pages
                for i in range(max(1,start)-1, min(nb_pages,end)): indices.add(i)
            else:
                i = int(p)-1
                if 0 <= i < nb_pages: indices.add(i)
        return sorted(indices)

    def preview_cut(self):
        pdf_path = self.pdf_path_var.get().strip()
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showerror("Erreur", "Choisis d'abord un PDF."); return
        try:
            doc = fitz.open(pdf_path)
            page = doc.load_page(0)
            dpi = int(self.res_dpi_var.get())
            zoom = dpi / 72.0; mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = pil_from_fitz_pixmap(pix)
            if self.split_mode_var.get() == "half":
                gx = img.width // 2
            else:
                gx = find_gutter_x(img, self.central_frac_var.get(), self.smooth_px_var.get())
            prev = img.copy()
            draw = ImageDraw.Draw(prev)
            draw.line([(gx,0),(gx,prev.height)], fill=(255,0,0), width=6)
            # scale preview
            max_w = 1200
            scale = min(1.0, max_w / prev.width)
            show = prev.resize((int(prev.width*scale), int(prev.height*scale)))
            top = tk.Toplevel(self); top.title("Aperçu découpe (p.1)")
            tkimg = ImageTk.PhotoImage(show)
            lbl = ttk.Label(top, image=tkimg); lbl.image = tkimg
            lbl.pack()
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def start_ocr(self):
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("En cours", "Un traitement est déjà en cours."); return
        pdf_path = self.pdf_path_var.get().strip()
        out_dir = self.out_dir_var.get().strip()
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showerror("Erreur", "Veuillez choisir un PDF valide."); return
        if not out_dir or not os.path.isdir(out_dir):
            messagebox.showerror("Erreur", "Veuillez choisir un dossier de sortie valide."); return
        if not (self.format_txt_var.get() or self.format_docx_var.get() or self.format_pdf_var.get()):
            messagebox.showerror("Erreur", "Sélectionnez au moins un format (TXT, DOCX ou PDF)."); return
        if self.format_docx_var.get() and Document is None:
            messagebox.showerror("Erreur", "python-docx n'est pas installé. 'pip install python-docx' ou décochez DOCX."); return
        found = configure_tesseract()
        if not found:
            messagebox.showerror("Tesseract introuvable", "Je ne trouve pas tesseract.exe. Vérifie l’installation / PATH."); return

        try:
            langs_avail = pytesseract.get_languages(config="")
            self.logln(f"Langues Tesseract disponibles: {', '.join(sorted(langs_avail))}")
        except Exception:
            self.logln("Impossible d’énumérer les langues Tesseract." )

        self.log.delete("1.0", "end"); self.progress["value"] = 0
        self.set_status("Préparation…")
        self.logln(f"PDF : {pdf_path}"); self.logln(f"Dossier de sortie : {out_dir}"); self.logln(f"Tesseract : {found}")
        self._worker = threading.Thread(target=self._do_ocr, daemon=True); self._worker.start()

    def _do_ocr(self):
        try:
            pdf_path = self.pdf_path_var.get().strip()
            out_dir = self.out_dir_var.get().strip()
            dpi = int(self.res_dpi_var.get())
            langs = self.lang_var.get().strip() or "fra"
            pr_str = self.page_range_var.get().strip()
            tess_cfg = self.tess_config_var.get().strip()
            base = os.path.splitext(os.path.basename(pdf_path))[0]
            txt_out = os.path.join(out_dir, f"{base}_OCR.txt")
            docx_out = os.path.join(out_dir, f"{base}_OCR.docx")
            pdf_out = os.path.join(out_dir, f"{base}_OCR.pdf")
            self.logln(f"Langues Tesseract : {langs}")
            self.logln(f"Résolution rendu : {dpi} DPI")
            self.logln(f"Pages : {pr_str}")
            self.logln(f"Config Tesseract : {tess_cfg or '(par défaut)'}")

            doc = fitz.open(pdf_path)
            nb_pages = doc.page_count
            pages_idx = self._parse_page_ranges(pr_str, nb_pages)
            if not pages_idx: raise ValueError("Aucune page à traiter.")
            self.progress["maximum"] = len(pages_idx)
            all_pages_text = []; self.set_status("OCR en cours…")
            final_pdf = fitz.open() if self.format_pdf_var.get() else None
            suffixes = "abcdefghijklmnopqrstuvwxyz"

            for k, i in enumerate(pages_idx, start=1):
                page = doc.load_page(i)
                zoom = dpi / 72.0; mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = pil_from_fitz_pixmap(pix)

                images_to_ocr = [img]
                if self.split_doubles_var.get():
                    images_to_ocr = split_double_page(img, mode=self.split_mode_var.get(),
                                                      central_frac=self.central_frac_var.get(),
                                                      smooth_px=int(self.smooth_px_var.get()))

                for sub_idx, sub_img in enumerate(images_to_ocr):
                    proc = sub_img.convert("L"); proc = ImageOps.autocontrast(proc); proc = proc.filter(ImageFilter.MedianFilter(3))
                    try:
                        txt = pytesseract.image_to_string(proc, lang=langs, config=tess_cfg or None)
                    except Exception as e:
                        self.logln(f"[Page {i+1}] Erreur OCR: {e}. Fallback 'eng'.")
                        txt = pytesseract.image_to_string(proc, lang="eng", config=tess_cfg or None)

                    txt = postprocess_text(txt)
                    suffix = suffixes[sub_idx] if len(images_to_ocr) > 1 else ""
                    page_header = f"\n===== Page {i+1}{suffix}/{nb_pages} =====\n"
                    all_pages_text.append(page_header + txt + "\n")
                    self.logln(f"[Page {i+1}{suffix}] {len(txt)} caractères extraits")

                    if final_pdf is not None:
                        try:
                            pdf_bytes = pytesseract.image_to_pdf_or_hocr(proc, lang=langs, config=tess_cfg or None, extension='pdf')
                            page_pdf = fitz.open(stream=pdf_bytes, filetype='pdf')
                            final_pdf.insert_pdf(page_pdf)
                        except Exception as e:
                            self.logln(f"[Page {i+1}{suffix}] PDF interrogeable impossible : {e}")

                self.progress["value"] = k; self.set_status(f"Page {k} / {len(pages_idx)} traitée"); self.update_idletasks()

            if self.format_txt_var.get():
                with open(txt_out, "w", encoding="utf-8") as f:
                    if self.keep_pagebreaks_var.get():
                        f.write("\n\f\n".join(p.strip() for p in all_pages_text))
                    else:
                        f.write("\n\n".join(p.strip() for p in all_pages_text))
                self.logln(f"TXT enregistré : {txt_out}")

            if self.format_docx_var.get() and Document is not None:
                docx = Document()
                try:
                    style = docx.styles["Normal"]; font = style.font; font.name = "Calibri"; font.size = Pt(11)
                except Exception: pass
                docx.add_heading(f"OCR de {os.path.basename(pdf_path)}", level=1)
                docx.add_paragraph(f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                for idx, ptxt in enumerate(all_pages_text, start=1):
                    lines = ptxt.splitlines()
                    if lines and lines[0].startswith("===== Page "):
                        docx.add_heading(lines[0].strip("= ").strip(), level=2)
                        body = "\n".join(lines[1:]).strip()
                    else:
                        body = ptxt.strip()
                    docx.add_paragraph(body)
                    if self.keep_pagebreaks_var.get() and idx < len(all_pages_text):
                        docx.add_page_break()
                docx.save(docx_out); self.logln(f"DOCX enregistré : {docx_out}")

            if final_pdf is not None:
                final_pdf.save(pdf_out); self.logln(f"PDF interrogeable enregistré : {pdf_out}")

            self.set_status("Terminé ✅"); self.logln("Terminé."); messagebox.showinfo("OCR", "Traitement terminé.")
        except Exception as e:
            self.set_status("Erreur ❌"); self.logln(f"ERREUR : {e}"); messagebox.showerror("Erreur OCR", str(e))


def main():
    app = OCRApp(); app.mainloop()


if __name__ == "__main__":
    main()
