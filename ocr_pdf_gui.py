#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR PDF → TXT / DOCX via Tkinter
Auteur : Tony Gheeraert
Dépendances : PyMuPDF (fitz), Pillow, pytesseract, python-docx
Tesseract OCR doit être installé sur la machine (binaire + data/tesstrained).
- Windows : installeur recommandé (UB Mannheim) ou tesseract-ocr officiel, puis ajouter tesseract.exe au PATH.
- macOS : `brew install tesseract tesseract-lang`
- Linux : `sudo apt-get install tesseract-ocr tesseract-ocr-fra` (et autres langues au besoin)

Usage : Lancez le script → choisissez un PDF → configurez (langue, format sortie) → OCR.
"""

import io
import os
import sys
import threading
from datetime import datetime
from PIL import ImageOps, ImageFilter

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Dépendances OCR / PDF
try:
    import fitz  # PyMuPDF
except Exception as e:
    raise SystemExit("PyMuPDF (fitz) requis. Installez-le via 'pip install pymupdf'.") from e

try:
    from PIL import Image
except Exception as e:
    raise SystemExit("Pillow requis. Installez-le via 'pip install pillow'.") from e

try:
    import pytesseract
except Exception as e:
    raise SystemExit("pytesseract requis. Installez-le via 'pip install pytesseract'.") from e

# Sortie .docx
try:
    from docx import Document
    from docx.shared import Pt
except Exception as e:
    Document = None  # Autoriser l'utilisation sans python-docx si l'utilisateur ne veut que .txt


def pil_from_fitz_pixmap(pix):
    """Convertit un fitz.Pixmap en PIL.Image sans écrire sur disque."""
    # On passe par PNG en mémoire pour préserver le rendu
    data = pix.tobytes("png")
    return Image.open(io.BytesIO(data)).convert("RGB")

def _is_potential_double(img):
    # Heuristique simple : très large par rapport à la hauteur
    w, h = img.size
    return (w / h) >= 1.28  # ajuste si besoin

def _find_gutter_x(img):
    """
    Cherche la 'gouttière' (zone de moindre encre) près du centre.
    Retourne un x (int) dans les coordonnées de l'image d'origine, ou None.
    """
    w, h = img.size
    # Vignette pour aller vite
    target_w = 1000
    scale = target_w / float(w)
    thumb = img.convert("L").resize((target_w, max(1, int(h * scale))), Image.LANCZOS)
    # Amélioration légère
    thumb = ImageOps.autocontrast(thumb)
    thumb = thumb.filter(ImageFilter.MedianFilter(3))
    # Binarisation simple (fond clair)
    bw = thumb.point(lambda p: 255 if p > 200 else 0).convert("1")
    pix = bw.load()
    tw, th = bw.size

    # Projection verticale (somme de pixels noirs par colonne)
    sums = []
    for x in range(tw):
        black = 0
        for y in range(th):
            if pix[x, y] == 0:  # noir
                black += 1
        sums.append(black)

    center = tw // 2
    left = max(0, int(center - tw * 0.2))
    right = min(tw, int(center + tw * 0.2))

    # Colonne la plus "vide" près du centre
    candidate = min(range(left, right), key=lambda x: sums[x])

    # Vérification de "profondeur de vallée"
    med = sorted(sums)[len(sums) // 2]
    if sums[candidate] <= max(1, int(med * 0.5)):
        # Recalage sur l'image d'origine
        cut_x = int(candidate / scale)
        # Un peu de marge (éviter couper dans le texte)
        margin = max(10, int(w * 0.01))
        cut_x = max(margin, min(w - margin, cut_x))
        return cut_x
    return None

def split_double_page(img, mode="auto"):
    """
    Retourne [img] si pas double, sinon [gauche, droite].
    mode='auto' : essaie la gouttière ; 'half' : coupe au milieu.
    """
    if not _is_potential_double(img):
        return [img]

    w, h = img.size
    if mode == "auto":
        gx = _find_gutter_x(img)
        if gx is None:
            gx = w // 2
    else:
        gx = w // 2

    left_box = (0, 0, gx, h)
    right_box = (gx, 0, w, h)
    left_img = img.crop(left_box)
    right_img = img.crop(right_box)

    # Optionnel : léger recadrage marges après coupe (désactivé par défaut)
    # left_img = ImageOps.crop(left_img, border=2)
    # right_img = ImageOps.crop(right_img, border=2)

    return [left_img, right_img]

class OCRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OCR PDF → TXT / DOCX")
        self.geometry("720x560")
        self.minsize(700, 540)

        # Variables Tk
        self.pdf_path_var = tk.StringVar()
        self.out_dir_var = tk.StringVar()
        self.lang_var = tk.StringVar(value="fra+eng")  # ex. 'fra', 'eng', 'fra+eng'
        self.res_dpi_var = tk.IntVar(value=300)
        self.format_txt_var = tk.BooleanVar(value=True)
        self.format_docx_var = tk.BooleanVar(value=True)
        self.keep_pagebreaks_var = tk.BooleanVar(value=True)
        self.page_range_var = tk.StringVar(value="all")  # ex. 'all', '1-5', '1-3,6,8-'
        self.tess_config_var = tk.StringVar(value="--oem 1 --psm 6")  # bloc de texte uniforme par page
        self.split_doubles_var = tk.BooleanVar(value=True)  # activer par défaut si tu veux
        self.split_mode_var = tk.StringVar(value="auto")  # "auto" ou "half"

        # UI
        self._build_ui()

        # État
        self._worker = None

    def _build_ui(self):
        pad = {'padx': 10, 'pady': 6}

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)

        # Ligne : sélectionner PDF
        row1 = ttk.Frame(frm); row1.pack(fill="x", **pad)
        ttk.Label(row1, text="Fichier PDF :").pack(side="left")
        ttk.Entry(row1, textvariable=self.pdf_path_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row1, text="Parcourir…", command=self._browse_pdf).pack(side="left")

        # Ligne : dossier de sortie
        row2 = ttk.Frame(frm); row2.pack(fill="x", **pad)
        ttk.Label(row2, text="Dossier de sortie :").pack(side="left")
        ttk.Entry(row2, textvariable=self.out_dir_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row2, text="Choisir…", command=self._browse_outdir).pack(side="left")


        # Ligne : paramètres Tesseract
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

        # Ligne : formats de sortie
        row4 = ttk.LabelFrame(frm, text="Format de sortie"); row4.pack(fill="x", **pad)
        ttk.Checkbutton(row4, text="Texte (.txt)", variable=self.format_txt_var).pack(side="left", padx=8, pady=4)
        ttk.Checkbutton(row4, text="Word (.docx)", variable=self.format_docx_var).pack(side="left", padx=8, pady=4)

        row4b = ttk.LabelFrame(frm, text="Doubles pages");
        row4b.pack(fill="x", padx=10, pady=6)
        ttk.Checkbutton(row4b, text="Couper les doubles pages", variable=self.split_doubles_var) \
            .pack(side="left", padx=8, pady=4)

        ttk.Label(row4b, text="Méthode :").pack(side="left", padx=(16, 6))
        split_combo = ttk.Combobox(row4b, textvariable=self.split_mode_var, width=18, state="readonly",
                                   values=["auto", "half"])
        split_combo.pack(side="left", padx=4)
        split_combo.set(self.split_mode_var.get())

        # Progression
        row5 = ttk.Frame(frm); row5.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(row5, mode="determinate")
        self.progress.pack(fill="x", padx=4)
        self.status_var = tk.StringVar(value="Prêt.")
        ttk.Label(row5, textvariable=self.status_var).pack(anchor="w", padx=4, pady=2)

        # Boutons action
        row6 = ttk.Frame(frm); row6.pack(fill="x", **pad)
        ttk.Button(row6, text="Démarrer l’OCR", command=self.start_ocr).pack(side="left", padx=4)
        ttk.Button(row6, text="Quitter", command=self.destroy).pack(side="right", padx=4)

        # Journal
        row7 = ttk.LabelFrame(frm, text="Journal"); row7.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(row7, height=12, wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def _browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Choisir un PDF",
            filetypes=[("PDF", "*.pdf"), ("Tous les fichiers", "*.*")]
        )
        if path:
            self.pdf_path_var.set(path)
            # Définir dossier de sortie par défaut = dossier du PDF
            self.out_dir_var.set(os.path.dirname(path))

    def _browse_outdir(self):
        d = filedialog.askdirectory(title="Choisir un dossier de sortie")
        if d:
            self.out_dir_var.set(d)

    def _parse_page_ranges(self, pr_str, nb_pages):
        """Parse 'all' ou séquences '1-3,5,7-' en liste d'index (0-based)."""
        pr_str = pr_str.strip().lower()
        if pr_str in ("all", "", "*"):
            return list(range(nb_pages))

        indices = set()
        parts = [p.strip() for p in pr_str.split(",") if p.strip()]
        for p in parts:
            if "-" in p:
                a, b = p.split("-", 1)
                a = a.strip()
                b = b.strip()
                start = int(a) if a else 1
                end = int(b) if b else nb_pages
                start = max(1, start)
                end = min(nb_pages, end)
                for i in range(start-1, end):
                    indices.add(i)
            else:
                i = int(p) - 1
                if 0 <= i < nb_pages:
                    indices.add(i)
        return sorted(indices)

    def logln(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.update_idletasks()

    def set_status(self, text):
        self.status_var.set(text)
        self.update_idletasks()

    def start_ocr(self):
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("En cours", "Un traitement est déjà en cours.")
            return

        pdf_path = self.pdf_path_var.get().strip()
        out_dir = self.out_dir_var.get().strip()
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showerror("Erreur", "Veuillez choisir un PDF valide.")
            return
        if not out_dir or not os.path.isdir(out_dir):
            messagebox.showerror("Erreur", "Veuillez choisir un dossier de sortie valide.")
            return
        if not self.format_txt_var.get() and not self.format_docx_var.get():
            messagebox.showerror("Erreur", "Sélectionnez au moins un format de sortie (TXT ou DOCX).")
            return
        if self.format_docx_var.get() and Document is None:
            messagebox.showerror("Erreur", "python-docx n'est pas installé. Installez-le avec 'pip install python-docx' ou décochez DOCX.")
            return

        self.log.delete("1.0", "end")
        self.progress["value"] = 0
        self.set_status("Préparation…")
        self.logln(f"PDF : {pdf_path}")
        self.logln(f"Dossier de sortie : {out_dir}")

        # Lancer dans un thread pour garder l'UI réactive
        self._worker = threading.Thread(target=self._do_ocr, daemon=True)
        self._worker.start()

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

            self.logln(f"Langues Tesseract : {langs}")
            self.logln(f"Résolution rendu : {dpi} DPI")
            self.logln(f"Pages : {pr_str}")
            self.logln(f"Config Tesseract : {tess_cfg or '(par défaut)'}")

            # Ouvrir PDF
            doc = fitz.open(pdf_path)
            nb_pages = doc.page_count
            pages_idx = self._parse_page_ranges(pr_str, nb_pages)

            if not pages_idx:
                raise ValueError("Aucune page à traiter (vérifiez la plage).")

            self.progress["maximum"] = len(pages_idx)

            # OCR loop
            all_pages_text = []
            self.set_status("OCR en cours…")

            for k, i in enumerate(pages_idx, start=1):
                page = doc.load_page(i)
                zoom = dpi / 72.0  # résolution de rendu
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = pil_from_fitz_pixmap(pix)

                # OCR
                try:
                    txt = pytesseract.image_to_string(img, lang=langs, config=tess_cfg or None)
                except Exception as e:
                    # Fallback sur 'eng' si la langue n'est pas installée
                    self.logln(f"[Page {i+1}] Erreur OCR avec langues='{langs}': {e}. Fallback 'eng'.")
                    txt = pytesseract.image_to_string(img, lang="eng", config=tess_cfg or None)

                # Nettoyage léger
                txt = txt.replace("\r\n", "\n").replace("\r", "\n")
                txt = "\n".join(line.rstrip() for line in txt.split("\n"))

                # Marqueurs de page
                page_header = f"\n===== Page {i+1}/{nb_pages} =====\n"
                all_pages_text.append(page_header + txt.strip() + "\n")

                self.logln(f"[Page {i+1}] {len(txt)} caractères extraits")
                self.progress["value"] = k
                self.set_status(f"Page {k} / {len(pages_idx)} traitée")
                self.update_idletasks()

            # Écriture TXT
            if self.format_txt_var.get():
                with open(txt_out, "w", encoding="utf-8") as f:
                    if self.keep_pagebreaks_var.get():
                        f.write("\n\f\n".join(p.strip() for p in all_pages_text))
                    else:
                        f.write("\n\n".join(p.strip() for p in all_pages_text))
                self.logln(f"TXT enregistré : {txt_out}")

            # Écriture DOCX
            if self.format_docx_var.get() and Document is not None:
                docx = Document()
                style = docx.styles["Normal"]
                try:
                    font = style.font
                    font.name = "Calibri"
                    font.size = Pt(11)
                except Exception:
                    pass

                docx.add_heading(f"OCR de {os.path.basename(pdf_path)}", level=1)
                docx.add_paragraph(f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                for idx, ptxt in enumerate(all_pages_text, start=1):
                    # Enlever l'en-tête pour le corps, le mettre comme titre
                    lines = ptxt.splitlines()
                    if lines and lines[0].startswith("===== Page "):
                        docx.add_heading(lines[0].strip("= ").strip(), level=2)
                        body = "\n".join(lines[1:]).strip()
                    else:
                        body = ptxt.strip()
                    docx.add_paragraph(body)
                    if self.keep_pagebreaks_var.get() and idx < len(all_pages_text):
                        docx.add_page_break()

                docx.save(docx_out)
                self.logln(f"DOCX enregistré : {docx_out}")

            self.set_status("Terminé ✅")
            self.logln("Terminé.")

            messagebox.showinfo("OCR", "Traitement terminé.")
        except Exception as e:
            self.set_status("Erreur ❌")
            self.logln(f"ERREUR : {e}")
            messagebox.showerror("Erreur OCR", str(e))


def main():
    app = OCRApp()
    app.mainloop()


if __name__ == "__main__":
    main()
