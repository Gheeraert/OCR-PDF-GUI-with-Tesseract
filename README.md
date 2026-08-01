# OCR-PDF-GUI-with-Tesseract
# (Tkinter) — TXT / DOCX / PDF interrogeable + découpe de doubles pages

# Application prête à l'emploi avec interface graphique pour l'OCRisation de fichiers PDF en mode image

Application **Tkinter** prête à l’emploi pour **OCRiser** des PDF scannés :
- export **texte (.txt)**, **Word (.docx)** et **PDF interrogeable** (calque texte) ;
- **découpe automatique des doubles pages** (pages scannées 2-en-1) avec **aperçu** ;
- réglages **Tesseract** (langues, DPI, PSM/OEM) et **prétraitement** image léger.

Scripts :
- `ocr_pdf_gui.py` (application principale)
- `requirements_ocr.txt` (dépendances Python)

---

## ✨ Fonctionnalités

- **Interface graphique** simple (sélection du PDF & du dossier de sortie).
- **OCR Tesseract** via `pytesseract` et rendu PDF → image avec **PyMuPDF**.
- **Sorties** : `.txt`, `.docx`, **PDF interrogeable** (texte copiable/recherchable).
- **Doubles pages** :
  - Mode **auto** (détection de la **gouttière** : seuillage Otsu + projection verticale lissée).
  - Mode **half** (50/50) en secours.
  - **Aperçu** de la coupe sur la première page (ligne rouge) pour ajuster avant OCR.
- **Réglages** : langues Tesseract (`fra`, `eng`, `fra+eng`…), **DPI**, plage de pages, **config Tesseract** (`--oem`, `--psm`), sauts de page, etc.
- **Prétraitement** automatique léger (niveaux + médiane) pour améliorer l’OCR.
- Bouton **“Ouvrir le dossier”** en fin de traitement.

---

## 🧩 Prérequis

- **Python** ≥ 3.9
- **Tesseract OCR** installé **sur le système** (binaire + données de langues)
- Accès à l’outil `pip`

---

## 📦 Installation

1) Installer les dépendances Python :

```bash
pip install -r requirements_ocr.txt
```

**Contenu recommandé de `requirements_ocr.txt`** :
```
pymupdf
pillow
pytesseract
python-docx
numpy
```

2) Installer **Tesseract OCR** (voir ci-dessous selon votre OS).

---

## 🔧 Installation de Tesseract & langues

### Windows
- Installeur recommandé : **UB Mannheim** (inclut des langues supplémentaires).
- Chemin d’installation typique : `C:\Program Files\Tesseract-OCR\`
- Pendant l’installation, cochez les langues nécessaires (ex. **français**).
- Après installation, **redémarrez** l’IDE/terminal si nécessaire.

### macOS (Homebrew)
```bash
brew install tesseract
# selon distribution, les langues supplémentaires peuvent être dans un paquet séparé :
brew install tesseract-lang   # si disponible
```

### Linux (Debian/Ubuntu)
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-fra  # + autres packs: tesseract-ocr-eng, -deu, etc.
```

---

## 🛣️ Vérifier l’installation & le PATH

- **Windows (PowerShell / CMD)** :
  ```bash
  where tesseract
  tesseract --version
  ```
- **macOS / Linux (Terminal)** :
  ```bash
  which tesseract
  tesseract --version
  ```

Si la commande n’est pas trouvée, ajoutez **le dossier** (pas le fichier) au **PATH** :

**Windows** → *Variables d’environnement* → `Path` → **Ajouter** :
```
C:\Program Files\Tesseract-OCR\
```

> Le script gère aussi un **fallback** : s’il ne trouve pas Tesseract dans le PATH, il essaie automatiquement `C:\Program Files\Tesseract-OCR\tesseract.exe` et `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`.  
> En dernier recours, vous pouvez **forcer** le chemin dans le code :
> ```python
> import pytesseract
> pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
> ```

---

## ▶️ Utilisation

```bash
python ocr_pdf_gui.py
```

1. **Choisir un PDF** et un **dossier de sortie**.  
2. Régler **Langues**, **DPI**, **Config Tesseract**, **Plage de pages**.  
3. (Optionnel) Cocher **PDF interrogeable**.  
4. (Si besoin) **Couper les doubles pages** (voir ci-dessous) et lancer **Aperçu découpe (p.1)**.  
5. **Démarrer l’OCR**.

Sorties : `NOMDUFICHIER_OCR.txt`, `NOMDUFICHIER_OCR.docx` et/ou `NOMDUFICHIER_OCR.pdf`.

---

## 📖 Doubles pages : réglages & aperçu

Pour les scans 2-en-1, activez **“Couper les doubles pages”**.

- **Mode** :
  - **auto** (par défaut) : détecte la **gouttière** (zone claire au pli) via :
    - seuillage **Otsu** (fond/texte),
    - **projection verticale** (densité d’encre par colonne),
    - **lissage** configurable (moyenne glissante).
  - **half** : coupe **50/50** (secours).

- **Paramètres** :
  - **Fenêtre centrale (0.2–0.8)** : portion autour du centre où chercher la gouttière.  
    *Astuce* : si la pliure est décentrée, **augmentez** (0.40 → 0.60) pour élargir la recherche.  
  - **Lissage (px)** : largeur du filtre de lissage (stabilise la vallée centrale).  
    *Astuce* : texte dense/bruité → **augmentez** (25 → 45). Texte fin → **diminuez** (25 → 15).
  - **Aperçu découpe (p.1)** : affiche une **ligne rouge** à l’endroit de coupe sur la page 1. Ajustez jusqu’à tomber pile sur le **pli**.

- **Ordre des sous-pages** : **gauche → droite** (ex. “p.12a”, “p.12b”).

---

## 🛠️ Réglages Tesseract — paramètres clés

Dans le champ **“Config Tesseract”**, vous pouvez passer les paramètres courants.

### `--oem` (OCR Engine Mode)
- `--oem 0` : moteur « legacy »
- `--oem 1` : **LSTM** (recommandé)
- `--oem 2` : legacy + LSTM
- `--oem 3` : auto (par défaut)

### `--psm` (Page Segmentation Mode) — usages fréquents
- `--psm 6` : **bloc de texte uniforme** (pages simples) ✅
- `--psm 4` : **une colonne** de texte de tailles variables
- `--psm 3` : **page entière** auto (sans OSD) — utile pour **maquettes complexes**
- `--psm 1` : auto **avec OSD** (orientation/script)
- `--psm 11` : **texte épars**
- `--psm 12` : texte épars **avec OSD**
- (`--psm 7/8/10/13` : ligne, mot, caractère, ligne brute — cas particuliers)

### Recos rapides
- Pages “propres” : `--oem 1 --psm 6`  
- Articles à colonnes/maquettes : `--oem 1 --psm 3` (ou `--psm 4`)  
- Orientation incertaine : `--psm 1`  
- Langues mixtes : `lang="fra+eng"` (assurez-vous que **fra** est installée)

---

## 🎛️ Autres réglages utiles

- **DPI** : `300–400` convient généralement. Plus haut = plus lent, pas toujours mieux.  
- **Plage de pages** : `all` · `1-5` · `1-3,6,8-` (jusqu’à la fin).  
- **Sauts de page** : conservez-les si vous devez recoller aux numéros de page.  
- **PDF interrogeable** : produit un PDF image **avec calque texte** (copiable/recherchable).

---

## 🧯 Dépannage

- **“tesseract is not installed or it’s not in your PATH”**  
  - Vérifiez dans **le même terminal/IDE** :
    ```
    tesseract --version
    ```
  - Sur Windows, ajoutez `C:\Program Files\Tesseract-OCR\` au **PATH** (le **dossier**, pas `tesseract.exe`).  
  - Redémarrez l’IDE/terminal après modification du PATH.  
  - Sinon, **forcer** le chemin via `pytesseract.pytesseract.tesseract_cmd`.

- **Langue manquante (ex. `fra`)**  
  - Installer le pack : Windows (UB Mannheim → cocher “French”); Linux (`tesseract-ocr-fra`); macOS (via Homebrew).  
  - Dans l’UI, mettre `fra` (ou `fra+eng`).

- **Découpe double page incorrecte**  
  - Cliquer **Aperçu** → ajuster **Fenêtre centrale** (0.40 → 0.60) et/ou **Lissage** (25 → 45).  
  - Sinon, passer **Mode = half** (50/50).

- **OCR brouillon / sauts de ligne bizarres**  
  - Essayer `--psm 6` (bloc uniforme) au lieu de `3`.  
  - Monter à **DPI 350–400**.  
  - Les scans sombres profitent du prétraitement (déjà activé).  
  - Post-traitement (décésure + reflow) intégré.

- **PDF interrogeable non généré**  
  - Requiert Tesseract ≥ 4 (LSTM).  
  - Vérifier permissions/volume d’écriture.

---

## 📂 Structure (suggestion)

```
.
├── ocr_pdf_gui.py
├── requirements_ocr.txt
└── README.md
```

---

## 📝 Licence

```
MIT License
```

---

## 🙏 Remerciements

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)  
- [PyMuPDF / fitz](https://pymupdf.readthedocs.io/)  
- [Pillow](https://python-pillow.org/)  
- [python-docx](https://python-docx.readthedocs.io/en/latest/)

