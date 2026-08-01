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

- **Interface graphique** simple (sélection de la source & du dossier de sortie).
- **Deux sources d'entrée** : un **PDF scanné**, ou directement un **dossier de photos** (JPG/PNG/TIFF/BMP/WEBP, triées par ordre naturel de nom de fichier) — pratique pour des pages photographiées au smartphone sans passer par une app de scan tierce.
- **OCR Tesseract** via `pytesseract` et rendu PDF → image avec **PyMuPDF**.
- **Sorties** : `.txt`, `.docx`, **PDF interrogeable** (texte copiable/recherchable).
- **Doubles pages** :
  - Mode **auto** (détection de la **gouttière** : seuillage Otsu + projection verticale lissée).
  - Mode **half** (50/50) en secours.
  - **Aperçu** de la coupe sur la première page/photo (ligne rouge) pour ajuster avant OCR.
- **Réglages** : langues Tesseract (`fra`, `eng`, `fra+eng`…), **DPI**, plage de pages, **config Tesseract** (`--oem`, `--psm`), sauts de page, etc.
- **Prétraitement** automatique léger (niveaux + médiane) pour améliorer l’OCR sur des scans propres.
- **Mode photo (smartphone)** optionnel : corrige un éclairage non uniforme (flat-fielding par soustraction d'un flou gaussien large), redresse une inclinaison fine (deskew, recherche d'angle par variance de projection) et applique un **seuillage adaptatif** local — plus robuste qu'un simple contraste global pour des photos prises à main levée. Réglages (rayon de flou, marge de seuillage) ajustables, avec **aperçu dédié** avant de lancer un traitement complet.
- **Reflow de paragraphes** désactivable — utile pour préserver la mise en page de notes de bas de page, bibliographies ou vers.
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

1. **Choisir la source** : un **fichier PDF**, ou un **dossier de photos** (JPG/PNG…), et un **dossier de sortie**.  
2. Régler **Langues**, **DPI** (PDF uniquement), **Config Tesseract**, **Plage de pages**.  
3. (Optionnel) Cocher **PDF interrogeable**.  
4. (Si besoin) **Couper les doubles pages** (voir ci-dessous) et lancer **Aperçu découpe (p.1)**.  
5. Pour des **photos prises au smartphone** : activer **Mode photo** (voir ci-dessous).  
6. **Démarrer l’OCR**.

Sorties : `NOM_OCR.txt`, `NOM_OCR.docx` et/ou `NOM_OCR.pdf` (`NOM` = nom du PDF, ou nom du dossier de photos).

---

## 📸 Mode photo (smartphone)

Quand la source est un **dossier de photos**, le **Mode photo** se coche automatiquement la première fois (vous pouvez le décocher, ce choix est ensuite respecté). Il remplace le prétraitement standard (contraste global + médiane) par, dans l'ordre :

1. **Redressement (deskew)** sur la page/photo entière : recherche l'angle (± *Inclinaison max.*, réglable, 5° par défaut) qui aligne le mieux les lignes de texte, par variance des projections horizontales.
2. **Correction d'éclairage** sur la page entière : divise l'image par une version très floutée d'elle-même (*flat-fielding*) pour atténuer un gradient de lumière (ombre de la main, fenêtre d'un côté).
3. **Découpe des doubles pages** (si activée) : sur l'image déjà redressée/corrigée — la détection de gouttière est ainsi plus fiable.
4. **Correction de courbure** (nécessite `opencv-python-headless`), par sous-page : détecte les vraies lignes de base du texte (regroupement de caractères par dilatation horizontale + composantes connexes), ajuste une courbe par ligne, puis redresse chaque ligne individuellement via un champ de déplacement (`cv2.remap`) — contrairement au redressement de l'étape 1 qui n'applique qu'une seule rotation globale et ne peut pas corriger une page qui gondole près de la reliure. Recadre aussi sur la zone de texte détectée pour exclure les bordures/le fond de la photo. Si moins de 4 lignes fiables sont détectées (page peu textuelle), l'image est laissée inchangée.
5. **Seuillage adaptatif**, par sous-image : binarise par comparaison à une moyenne locale plutôt qu'un seuil global (Otsu), plus robuste si l'éclairage reste légèrement inégal après l'étape 2.

**Orientation EXIF** : case « Appliquer l'orientation EXIF (iPhone) », **décochée par défaut**. Certains téléphones (iPhone notamment) stockent l'orientation réelle en métadonnée sans faire pivoter les pixels ; cocher cette case corrige alors l'affichage. **Mais d'autres appareils font l'inverse** (vérifié sur un Samsung Galaxy A54 5G) : les pixels sont déjà correctement orientés et la balise Orientation est obsolète — cocher la case tournerait alors vos photos à tort. Utilisez le bouton **Aperçu** pour vérifier avant de lancer un traitement complet.

**Réglages ajustables** (valeurs par défaut adaptées à la plupart des cas) :
- **Inclinaison max. corrigée (°)** : plage de recherche du redressement (5° par défaut). Montez-la si vos photos sont plus penchées.
- **Flou éclairage (px)** : rayon du flou utilisé pour estimer le fond lumineux (31 par défaut). Augmentez-le si l'ombre/le gradient couvre une grande partie de la photo ; diminuez-le si le texte est très dense (pour ne pas confondre le texte avec le "fond").
- **Seuillage — flou (px) / marge** : rayon de la moyenne locale et marge de tolérance du seuillage adaptatif (15 px / 10 par défaut). Une marge plus grande conserve plus de gris (texte fin, papier jauni) ; plus petite, un résultat plus contrasté mais plus dur.

**Aperçu prétraitement (p.1)** : affiche le résultat complet du Mode photo (redressement + éclairage + découpe + seuillage) sur la première page/photo avec les réglages actuels — permet d'ajuster les paramètres ci-dessus avant de lancer un traitement complet sur tout un livre/article.

**Format des photos** : JPG, PNG, TIFF, BMP, WEBP. Le format **HEIC/HEIF** (par défaut sur iPhone) n'est **pas supporté** par Pillow seul — l'appli le signale dans le journal si des fichiers `.heic`/`.heif` sont détectés mais ignorés. Solution : réglez votre téléphone sur « Le plus compatible » (JPEG) avant de photographier, ou exportez vos photos en JPEG avant de lancer l'OCR.

**Résultat sur photos réelles (validé, mais imparfait)** : testé sur 3 vraies photos de double-page dont le texte était visiblement courbe (pas juste penché). La correction de courbure améliore nettement l'OCR — plusieurs paragraphes entiers passent d'un résultat totalement inexploitable (sans elle) à un texte quasi parfait. Le résultat reste toutefois **inégal** : certaines zones d'une même page (notamment près des notes de bas de page, où les lignes sont plus courtes et plus resserrées) peuvent encore ressortir dégradées, la courbure y étant modélisée par interpolation entre les lignes du corps de texte plutôt que mesurée directement. Si la qualité reste insuffisante sur vos photos :
- **Palliatif immédiat, sans changement de code** : aplatissez mieux le livre (poids, main bien centrée sur la reliure) et/ou photographiez une page à la fois plutôt qu'une double-page.
- Réduisez la densité de lignes très courtes (notes, citations) dans le cadre si possible, ou testez avec **Aperçu prétraitement** pour repérer les zones encore problématiques avant un traitement complet.

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

## 🧪 Tests

Tests unitaires (pytest) pour les fonctions pures de traitement d'image/texte (découpe de double page, mode photo, post-traitement) :

```bash
pip install -r requirements-dev.txt
pytest
```

---

## 📂 Structure (suggestion)

```
.
├── ocr_pdf_gui.py
├── requirements_ocr.txt
├── requirements-dev.txt
├── tests/
│   └── test_processing.py
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

