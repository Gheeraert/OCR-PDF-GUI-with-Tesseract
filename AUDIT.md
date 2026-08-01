# Audit du dépôt OCR-PDF-GUI-with-Tesseract

Date : 2026-08-01
Périmètre : `ocr_pdf_gui.py` (439 lignes, application unique), `README.md`, `requirements_ocr.txt`.
Contexte d'usage communiqué : numériser, avec un smartphone, des photos de pages et de doubles-pages d'articles/ouvrages (préparation à l'Agrégation), puis en tirer un OCR exploitable (TXT/DOCX/PDF interrogeable).

---

## 1. Résumé

Le code est un script Tkinter monofichier, propre et lisible pour ce qu'il fait : il rend des pages PDF en image via PyMuPDF, détecte optionnellement une gouttière de reliure pour scinder les doubles pages, prétraite légèrement l'image (niveaux de gris, autocontraste, filtre médian) puis lance Tesseract. C'est un outil solide **pour des PDF déjà issus d'un scanner à plat**.

Le problème principal n'est pas dans la qualité du code, mais dans l'**adéquation stratégique** : l'outil est conçu pour des scans plats et propres, alors que l'usage visé — photos prises à main levée avec un smartphone — produit des images avec des défauts (perspective, courbure de reliure, éclairage non uniforme, rotation) qu'aucune étape du pipeline ne corrige. Sans une app de scan côté téléphone qui fait déjà ce travail en amont, la qualité d'OCR sera décevante quel que soit le réglage Tesseract choisi côté PC.

Un second point structurel : l'outil n'accepte que des **PDF** en entrée. Un usage "photo de smartphone" produit typiquement des JPEG page par page ; il n'y a aucun chemin direct image → OCR, il faut d'abord assembler un PDF par un autre moyen.

Enfin, il y a un bug de dépendance réel (`numpy` manquant dans `requirements_ocr.txt`) et un problème de thread-safety Tkinter qui peut provoquer des plantages/gels aléatoires en cours de traitement long — précisément le scénario "scanner un chapitre entier".

---

## 2. Adéquation stratégique à l'usage visé (photos smartphone)

### 2.1 Aucun chemin image → OCR direct (bloquant en pratique)
`start_ocr()`/`_do_ocr()` n'acceptent qu'un fichier `.pdf` (`fitz.open(pdf_path)`, ligne 353). Si vous photographiez des pages avec l'appareil photo natif, vous obtenez des `.jpg`, pas un PDF. Il faut donc :
- soit utiliser une app de scan tierce (Apple Notes/Scan, Google Drive scan, Adobe Scan, CamScanner…) qui exporte en PDF — auquel cas cette app tierce fait déjà l'essentiel du travail de correction de perspective et d'éclairage, ce qui change beaucoup l'évaluation du reste de l'audit ;
- soit assembler manuellement les JPEG en PDF (aucun outil fourni dans ce dépôt pour cela).

**Recommandation** : soit documenter explicitement dans le README quelle app de scan utiliser en amont (et pourquoi), soit ajouter un import direct de JPG/PNG (glob de dossier → tri naturel des fichiers → traitement comme des "pages"), ce qui est un ajout raisonnable dans `_do_ocr` (remplacer la boucle `fitz` par une liste de chemins images quand l'entrée n'est pas un PDF).

### 2.2 Aucune correction de perspective / déformation de reliure
Une photo de livre ouvert à main levée n'est presque jamais un rectangle parfaitement plan : la page proche de la reliure se courbe, et l'angle de prise de vue introduit une perspective (trapèze). `find_gutter_x()` (ligne 95) suppose une image déjà "plate" : elle cherche une simple vallée verticale de faible densité d'encre par projection de colonnes. Sur une photo courbée :
- le texte proche de la reliure est distordu/flou, donc l'OCR y sera mauvais indépendamment de la coupe ;
- la "gouttière" elle-même peut ne pas être une ligne verticale nette, ce qui dégradera la détection automatique.

Il n'y a aucune étape de type "détection des 4 coins de page + correction de perspective" (`cv2.getPerspectiveTransform` / `warpPerspective` seraient l'approche standard avec OpenCV, absent des dépendances).

### 2.3 Aucune correction d'éclairage non uniforme
Une photo au smartphone a très souvent un gradient d'éclairage (ombre portée de la main/du téléphone, lumière de fenêtre d'un côté). Le prétraitement actuel (`ImageOps.autocontrast` + `MedianFilter(3)`, ligne 375) est un simple étirement global de contraste : il ne corrige pas un gradient local. Un scan plat classique n'a généralement pas ce problème (éclairage du scanner uniforme), donc cette lacune est spécifique à l'usage smartphone.

**Recommandation concrète** : ajouter une correction d'illumination par division par une version très floutée de l'image ("flat-fielding" / normalisation d'arrière-plan), par exemple :
```python
bg = gray.filter(ImageFilter.GaussianBlur(radius=large))
normalized = divide(gray, bg) * 255  # via numpy
```
puis seuillage adaptatif (Sauvola/Niblack ou `cv2.adaptiveThreshold`) plutôt qu'Otsu global, qui est sensible aux gradients.

### 2.4 Aucun redressement (deskew) de petite amplitude
Une photo à main levée est rarement parfaitement droite (quelques degrés d'inclinaison typiques). Tesseract avec `--psm 1` détecte l'orientation (rotations de 90°/180°/270° via OSD) mais **ne corrige pas une inclinaison fine** de quelques degrés, qui dégrade sensiblement la reconnaissance ligne par ligne. Aucune étape de deskew (recherche de l'angle qui maximise la variance des projections horizontales, ou transformée de Hough) n'est présente.

### 2.5 Le réglage DPI est trompeur pour une entrée "photo"
Le champ "Résolution (DPI)" (ligne 200) et le rendu `zoom = dpi/72.0` (ligne 364) n'ont de sens que pour un PDF vectoriel ou un PDF-scan dont on connaît la résolution d'origine. Si le PDF contient en réalité une photo JPEG déjà rastérisée, augmenter le DPI ne fait qu'agrandir l'image sans apporter d'information (upscaling), ce qui peut donner une fausse impression de contrôle qualité. Cela mérite au moins une note dans le README pour ne pas faire perdre du temps à l'utilisateur à monter le DPI sans effet réel.

### 2.6 Le reflow de texte peut nuire aux usages académiques
`postprocess_text()` (ligne 141) transforme systématiquement tout saut de ligne simple en espace (`re.sub(r"(?<!\n)\n(?!\n)", " ", txt)`) pour recoller les lignes en paragraphes. C'est excellent pour du texte courant, mais problématique pour :
- des notes de bas de page (numérotation, structure en colonnes séparée du corps de texte) ;
- des citations en vers, des références bibliographiques, des tableaux — fréquents dans des articles/ouvrages académiques.

Il n'y a pas d'option pour désactiver ce reflow. Idéalement, ce comportement devrait être un choix dans l'UI ("recoller les lignes en paragraphes : oui/non"), avec `oui` par défaut pour du texte suivi et `non` pour un article à notes/bibliographie.

---

## 3. Bugs et risques techniques (indépendants de l'usage photo)

### 3.1 `numpy` manquant de `requirements_ocr.txt` — bug réel
`otsu_thresh()` (ligne 73) et `find_gutter_x()` (ligne 100) font `import numpy as np`, mais `requirements_ocr.txt` ne liste que `pymupdf`, `pillow`, `pytesseract`, `python-docx`. Sur une installation propre suivant strictement le README (`pip install -r requirements_ocr.txt`), l'app plante dès qu'on active "Couper les doubles pages" (activé par défaut, `split_doubles_var = True` ligne 170) ou qu'on clique "Aperçu découpe". `numpy` n'est garanti par aucune des quatre dépendances déclarées.

**Correctif** : ajouter `numpy` à `requirements_ocr.txt`.

### 3.2 Écritures Tkinter depuis un thread worker — thread-safety
`_do_ocr()` tourne dans un `threading.Thread` (ligne 334) et appelle directement `self.logln(...)`, `self.progress["value"] = k`, `self.set_status(...)`, `self.update_idletasks()` (lignes 386-396) depuis ce thread. Tkinter n'est pas thread-safe : les mises à jour de widgets doivent passer par le thread principal (typiquement via une queue consommée par `self.after(...)`). En pratique, ça "marche souvent" mais peut provoquer des gels ou plantages aléatoires, plus probables sur un traitement long (nombreuses pages) — exactement le cas d'usage visé (scanner un chapitre entier).

**Recommandation** : faire communiquer le worker via une `queue.Queue`, et consommer cette queue côté thread principal avec `self.after(50, poll_queue)`.

### 3.3 Aucune sauvegarde incrémentale → perte totale en cas d'échec tardif
Le texte de toutes les pages est accumulé en mémoire (`all_pages_text`, ligne 358) et les fichiers de sortie ne sont écrits qu'**après** la boucle complète (lignes 398-426). Si une exception non rattrapée survient à la page 150 sur 200 (page corrompue, erreur Tesseract sur une page particulière suivie d'un échec du fallback "eng" lui-même — le `except` interne ligne 378 ne protège que le premier essai, pas le fallback ligne 380), tout le travail déjà fait est perdu : rien n'est écrit sur disque.

**Recommandation** : écrire le TXT de façon incrémentale (au fur et à mesure, ou au moins par blocs de N pages), et/ou envelopper aussi l'appel de fallback dans un `try/except` qui log l'erreur et passe à la page suivante plutôt que d'interrompre tout le traitement.

### 3.4 Pas de bouton d'annulation
Pour un traitement long (livre entier), il n'existe aucun moyen d'interrompre proprement le worker une fois lancé (ligne 334, `daemon=True` seulement — le thread continue jusqu'à la fin ou jusqu'à fermeture de l'appli). Un simple flag `threading.Event` vérifié à chaque itération de la boucle (ligne 362) réglerait ça facilement.

### 3.5 Regex de dé-césure incomplète
`postprocess_text()` (ligne 143) : `re.sub(r"(\w)[\-­]\n(\w)", r"\1\2", txt)` ne traite que le trait d'union ASCII (`-`) et le trait d'union conditionnel (`\xAD`). Les OCR de textes imprimés en français produisent parfois un tiret typographique différent selon la police/l'OCR (rare mais possible). Impact mineur, à surveiller si vous constatez des mots coupés non recollés.

### 3.6 Robustesse des entrées utilisateur (mineure)
Les `Spinbox` pour DPI, fenêtre centrale et lissage (lignes 201, 218, 220) ne valident pas leur contenu : un utilisateur peut taper une valeur non numérique ou vide, ce qui lèvera une exception `ValueError`/`TclError` non gérée avec un message peu clair au moment du `int(...)`/`float(...)` (lignes 340, 372). Impact faible (erreur visible, pas de corruption de données) mais expérience utilisateur dégradée.

### 3.7 Absence de tests
Aucun test automatisé n'existe pour `otsu_thresh`, `find_gutter_x`, `split_double_page` ou `postprocess_text` — ce sont pourtant des fonctions pures, facilement testables unitairement (entrée image/texte connue → sortie attendue), et ce sont précisément les fonctions les plus sensibles à un changement de type d'entrée (photo vs scan). Des tests couvriraient utilement une régression si vous ajustez l'algo de gouttière pour mieux gérer les photos.

---

## 4. Ce qui est bien fait

- Détection de Tesseract multiplateforme avec repli sur les chemins Windows standards (`configure_tesseract`, ligne 45) : pragmatique.
- Aperçu visuel de la coupe avant de lancer tout le traitement (`preview_cut`, ligne 279) : bonne UX, permet de valider le réglage de gouttière page par page avant un run long.
- Séparation claire des réglages Tesseract exposés (`--oem`, `--psm`) avec recommandations dans le README : utile et pédagogique, notamment la distinction `--psm 3` (maquette complexe, pertinent pour des articles à colonnes) vs `--psm 6` (page simple).
- Gestion des plages de pages avec syntaxe `1-3,6,8-` (ligne 265) : couvre bien le besoin de ne traiter qu'un sous-ensemble d'un PDF.
- Fallback de langue Tesseract (`eng`) en cas d'échec (ligne 378) : bonne intention, même si son implémentation devrait être plus défensive (cf. 3.3).
- README très complet et didactique sur l'installation de Tesseract par OS.

---

## 5. Recommandations priorisées

**Corrections rapides (peu de risque, fort impact) :**
1. Ajouter `numpy` à `requirements_ocr.txt` (bug bloquant à l'usage par défaut).
2. Protéger le fallback de langue (ligne 378-380) dans un `try/except` qui log et continue plutôt que de laisser remonter l'exception et perdre tout le batch.
3. Écrire le TXT de façon incrémentale (ou sauvegarder un fichier partiel toutes les N pages) pour ne pas perdre un long traitement en cas d'erreur tardive.
4. Documenter dans le README que l'app attend un PDF déjà "plat" et recommander explicitement une app de scan smartphone (avec recadrage/correction de perspective automatique) en amont — évite une déception à l'usage.

**Améliorations structurantes pour l'usage "photo smartphone" (plus de travail, gain qualité important) :**
5. Ajouter un import direct de photos (dossier de JPG/PNG triés) sans passer par un PDF intermédiaire.
6. Ajouter une correction d'éclairage non uniforme (normalisation par flou gaussien large) avant seuillage, et passer à un seuillage adaptatif plutôt qu'Otsu global pour les images de type "photo".
7. Ajouter un deskew (redressement fin, quelques degrés) avant OCR — gain de qualité significatif et peu coûteux à implémenter (recherche d'angle par variance de projection).
8. Si la déformation de perspective/courbure est un problème constaté en pratique (à vérifier sur vos propres photos), envisager une détection des bords de page + correction de perspective (nécessiterait `opencv-python`, actuellement absent des dépendances).

**Confort / fiabilité :**
9. Rendre thread-safe les mises à jour d'UI depuis le worker (queue + `after`).
10. Ajouter un bouton "Annuler" pour les traitements longs.
11. Rendre le reflow de paragraphes (`postprocess_text`) optionnel via une case à cocher, utile pour les textes avec notes de bas de page/bibliographie.

---

## 6. Conclusion

Le code est correct et bien organisé pour ce qu'il fait — un pipeline PDF-scanné → OCR avec découpe de double page. Le vrai risque pour votre usage n'est pas un bug caché mais un **écart entre l'hypothèse implicite du pipeline (page plate, bien éclairée, déjà en PDF) et la réalité d'une photo de smartphone prise à main levée sur un livre ouvert**. Avant d'investir dans les réglages fins Tesseract (`--psm`, DPI), le plus gros gain de qualité viendra probablement d'une meilleure image en entrée : soit via une app de scan mobile qui fait déjà la correction de perspective/éclairage, soit en ajoutant ces étapes dans ce pipeline. Le bug `numpy` (§3.1) doit être corrigé indépendamment, car il bloque la fonctionnalité de découpe de double page activée par défaut.
