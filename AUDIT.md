# Audit du dépôt OCR-PDF-GUI-with-Tesseract — v2 (post étapes A & B)

Date : 2026-08-01
Périmètre : `ocr_pdf_gui.py` (722 lignes), `README.md`, `requirements_ocr.txt`, tel qu'après les commits :
- `00bf154` Étape A : fiabilise le traitement OCR long (thread-safety UI, sauvegarde incrémentale, bouton Annuler, fallback langue protégé, numpy ajouté)
- `8d63e00` Étape B : import direct de photos (dossier JPG/PNG…) + « Mode photo » (correction d'éclairage, deskew, seuillage adaptatif)

Contexte d'usage : OCRiser des **photographies prises au smartphone** d'articles et d'ouvrages universitaires (préparation à l'Agrégation) — pages simples ou doubles-pages de livre ouvert.

Cet audit revérifie le code réel ligne par ligne (pas un résumé de mémoire) : chaque point ci-dessous cite le fichier/la ligne concernée et, pour les points nouveaux, a été testé empiriquement.

---

## 1. Ce que les étapes A et B ont réellement corrigé (vérifié)

| # | Problème (audit v1) | Statut | Où |
|---|---|---|---|
| 3.1 | `numpy` manquant de `requirements_ocr.txt` | ✅ corrigé | `requirements_ocr.txt` |
| 3.2 | Écritures Tkinter depuis le thread worker | ✅ corrigé | `_q_put`/`_poll_queue`, `ocr_pdf_gui.py:358-381` — tout passe par une `queue.Queue` consommée via `self.after` |
| 3.3 | Pas de sauvegarde incrémentale (perte totale si crash tardif) | ✅ corrigé | TXT flush à chaque page (`:642-648`), DOCX/PDF sauvegardés tous les `SAVE_EVERY=10` (`:664-671`) et aussi en cas d'exception (`:703-708`) |
| 3.4 | Pas de bouton d'annulation | ✅ corrigé | `cancel_ocr`, `self._cancel_event`, vérifié à chaque page et sous-page (`:598`, `:612`) |
| — | Fallback langue non protégé | ✅ corrigé | `try/except` imbriqué autour du fallback `eng` (`:626-634`) |
| 2.1 | Aucun chemin image → OCR direct (PDF obligatoire) | ✅ corrigé | Sélecteur de source PDF / dossier de photos, `list_images_in_folder` (`:149-152`), `load_page_image` (`:553-559`) |
| 2.3 | Aucune correction d'éclairage non uniforme | ✅ corrigé (optionnel, « Mode photo ») | `normalize_illumination` (`:155-163`) |
| 2.4 | Aucun redressement (deskew) fin | ✅ corrigé (optionnel, « Mode photo ») | `estimate_skew_angle` / `deskew_image` (`:176-210`) |

Ces huit points sont vérifiés dans le code actuel, testés (compilation, tests unitaires ad hoc sur les fonctions pures, smoke-test UI) et fonctionnels.

---

## 2. Ce qui reste non traité ou insuffisamment traité (vérifié)

### 2.1 Aucune correction de perspective / courbure de reliure — **toujours absent**
Aucune trace de `cv2`, `getPerspectiveTransform`, `warpPerspective` ou logique équivalente dans le fichier (recherche vide). C'était le point le plus structurant de l'audit v1 (§2.2) et **il n'a pas été traité** par les étapes A/B — le deskew ne corrige qu'une rotation globale de quelques degrés, pas une déformation trapézoïdale ni la courbure de page près de la reliure. C'est toujours, de loin, le facteur qui limitera le plus la qualité d'OCR sur une vraie photo de livre ouvert à main levée.

### 2.2 EXIF non pris en compte à l'ouverture des photos — **bug réel, nouveau (introduit par l'étape B)**
`Image.open(image_paths[idx]).convert("RGB")` (`:555`, et `_load_first_page_image` `:449`) n'applique **pas** l'orientation EXIF. Vérifié empiriquement :
```python
img = Image.new("RGB", (100, 60), "white")
exif = img.getexif(); exif[0x0112] = 6  # Orientation
... img.save(buf, format="JPEG", exif=exif.tobytes())
Image.open(buf).size            # -> (100, 60)  — EXIF ignoré
ImageOps.exif_transpose(...).size  # -> (60, 100) — correction appliquée
```
De nombreux téléphones (notamment iPhone) enregistrent l'orientation réelle **dans les métadonnées EXIF** plutôt que de faire pivoter les pixels. Sans `ImageOps.exif_transpose()`, une photo prise en portrait peut être traitée à l'envers ou sur le côté : OCR catastrophique, et détection de gouttière (`find_gutter_x`) faussée puisqu'elle suppose une page verticale. C'est un **bug bloquant en pratique**, silencieux (pas d'erreur, juste un résultat mauvais), et probablement la cause la plus probable d'une déception si l'utilisateur teste le mode photo sur de vraies photos de smartphone.

**Correctif** : appliquer `img = ImageOps.exif_transpose(img)` juste après chaque `Image.open(...)` dans `load_page_image` et `_load_first_page_image`.

### 2.3 Le pipeline « Mode photo » ne corrige pas l'image *avant* la découpe des doubles pages — **bug de conception, nouveau (introduit par l'étape B)**
Dans `_do_ocr` :
- `:603` `img = load_page_image(i)` — image brute (pas de deskew, pas de correction d'éclairage).
- `:605-609` `split_double_page(img, ...)` — la détection de gouttière (`find_gutter_x`) tourne sur cette image **brute**, avec son propre mini-pipeline interne (Otsu + autocontrast + médiane, `:102-107`), indépendant du « Mode photo ».
- **Seulement ensuite**, `:617-623`, pour chaque **sous-image déjà découpée**, le deskew + normalisation d'éclairage + seuillage adaptatif sont appliqués.

Conséquence : sur une photo penchée et/ou mal éclairée, la détection de la gouttière (l'étape la plus sensible à ces deux défauts, cf. audit v1 §2.2) ne bénéficie d'aucune des améliorations du Mode photo. Le mode photo corrige la lisibilité du texte après coup, mais pas la fiabilité de la découpe elle-même.

**Correctif recommandé** : réordonner le pipeline pour la page entière **avant** la découpe : `deskew(page entière)` → `normalize_illumination(page entière)` → `split_double_page(image corrigée)` → `adaptive_threshold` par sous-image → OCR. Le deskew sur la double-page entière est aussi plus robuste (plus de texte = estimation d'angle plus stable) que sur chaque moitié séparément.

### 2.4 HEIC/HEIF non supporté — **gap probable pour l'usage réel**
`IMAGE_EXTENSIONS` (`:142`) ne liste pas `.heic`/`.heif`, et Pillow ne sait pas nativement décoder ce format (nécessite le paquet optionnel `pillow-heif`). Or c'est le **format par défaut des photos iPhone** depuis iOS 11. Si l'utilisateur ne change pas ses réglages d'appareil photo (Réglages → Appareil photo → Formats → « Le plus compatible »), le dossier de photos sera vide aux yeux de `list_images_in_folder`, sans message d'erreur explicite au moment du choix du dossier (l'erreur ne sera vue qu'au clic sur « Démarrer » : « Aucune image trouvée »).

**Correctif rapide** : documenter clairement dans le README (« exportez/prenez vos photos en JPEG, pas HEIC ») et/ou détecter les `.heic`/`.heif` présents pour avertir explicitement l'utilisateur plutôt que de les ignorer silencieusement. Ajout optionnel plus tard : dépendance `pillow-heif` + `pillow_heif.register_heif_opener()`.

### 2.5 Réglages du Mode photo non ajustables et non prévisualisables
`normalize_illumination` (rayon de flou = 31) et `adaptive_threshold` (rayon = 15, offset = 10) ont des paramètres **codés en dur** (`:155`, `:166`), contrairement à la découpe de double page qui expose `central_frac`/`smooth_px` réglables avec aperçu. Une photo avec un gradient de lumière plus fort ou plus doux, ou un papier plus jauni, demandera probablement un réglage différent. Il n'existe aucun moyen de voir le résultat du Mode photo avant de lancer un traitement complet (le bouton « Aperçu découpe » ne montre que la ligne de coupe sur l'image brute, jamais le résultat du prétraitement photo).

### 2.6 Résolution DPI trompeuse en mode photo (variante du point v1 §2.5)
Le champ « Résolution (DPI) » reste visible et modifiable même quand la source est un dossier de photos, alors qu'il n'a strictement aucun effet dans ce mode (`load_page_image` en mode images ignore `dpi`). Contrairement au champ PDF/dossier de photos (désactivé dynamiquement via `_on_input_mode_change`), le DPI n'est pas grisé — risque de faire perdre du temps à l'utilisateur pour rien.

### 2.7 « Mode photo » réimposé à chaque bascule de source
`_on_input_mode_change` (`:398-399`) force `photo_mode_var` à `True` **à chaque clic** sur le radiobouton « Dossier de photos », même si l'utilisateur l'avait explicitement décoché entre-temps (cas d'usage plausible : photos déjà pré-redressées par une autre app). Mineur, mais à corriger (ne l'activer par défaut qu'une fois, à la première sélection).

### 2.8 Toujours non traités depuis l'audit v1 (revérifiés, inchangés)
- **§2.6 / §5.11** — Reflow de paragraphes (`postprocess_text`, `:216`) toujours non désactivable ; problématique pour notes de bas de page/bibliographie.
- **§3.5** — Regex de dé-césure (`:215`) toujours limitée à `-` et `\xAD`.
- **§3.6** — Spinboxes (DPI, fenêtre centrale, lissage, et maintenant inclinaison max `:328`) toujours sans validation ; en pratique sans gravité car les erreurs de conversion (`int()`/`float()`) sont maintenant absorbées par le `try/except` global de `_do_ocr` et remontées proprement via `messagebox.showerror`, mais un message plus spécifique serait préférable.
- **§3.7** — Toujours **aucun test automatisé**, alors que le nombre de fonctions pures testables a augmenté (7 désormais : `otsu_thresh`, `find_gutter_x`, `split_double_page`, `postprocess_text`, `normalize_illumination`, `adaptive_threshold`, `estimate_skew_angle`/`deskew_image`, `natural_sort_key`). Le risque de régression silencieuse augmente avec la taille du pipeline.
- Nouveau, mineur : `doc = fitz.open(pdf_path)` (`:549`) n'est jamais fermé (`doc.close()` absent) — fuite de ressources mineure sur de gros PDF ou une longue session d'utilisation répétée de l'appli.

---

## 3. Plan priorisé pour la suite (Étape C et au-delà)

### Étape C — corrections ciblées, faible risque, fort impact ✅ fait (commit `16386b6`)
1. ✅ **EXIF orientation** (§2.2) — `open_photo()` applique `ImageOps.exif_transpose()` après chaque `Image.open()`. Testé (image EXIF Orientation=6 synthétique → dimensions correctement permutées).
2. ✅ **Réordonner le pipeline photo avant la découpe** (§2.3) — deskew + normalisation d'éclairage sur la page entière avant `split_double_page`, seuillage adaptatif seulement après découpe, par sous-image.
3. ✅ **Griser le champ DPI en mode photo** (§2.6) — `dpi_label`/`dpi_spinbox` désactivés dans `_on_input_mode_change`.
4. ✅ **Avertir sur les fichiers HEIC/HEIF ignorés** (§2.4) — `list_unsupported_images_in_folder` + message dans le journal + note README.
5. ✅ **Ne plus réimposer `photo_mode_var=True` à chaque bascule** (§2.7) — `_photo_mode_user_set` mémorise un choix manuel via le `command` du Checkbutton.

Tous testés (compilation, tests unitaires ciblés sur `open_photo`/`list_unsupported_images_in_folder`, smoke-test UI sur le grisage DPI et la non-réimposition du mode photo).

### Étape D — réglages & confiance utilisateur (impact moyen, effort modéré)
6. **Exposer `blur_radius`/`offset` du Mode photo dans l'UI** (§2.5), avec valeurs par défaut actuelles conservées.
7. **Ajouter un bouton « Aperçu prétraitement »** montrant le résultat du Mode photo (image après deskew + illumination + seuillage) sur la première page/photo, sur le même principe que « Aperçu découpe ».
8. **Rendre le reflow de paragraphes optionnel** (§2.8, hérité v1) — case à cocher, utile pour notes de bas de page/bibliographie/vers.
9. **Tests unitaires** (pytest) pour les fonctions pures du module, en priorité les fonctions ajoutées à l'étape B (`estimate_skew_angle` sur image synthétique inclinée d'angle connu, `normalize_illumination` sur gradient connu, `natural_sort_key`) — protège contre les régressions avant de toucher à l'étape E.

### Étape E — le vrai gain qualité restant (effort important, dépendance nouvelle)
10. **Correction de perspective/courbure** (§2.1, le point le plus structurant depuis l'audit v1) : nécessite `opencv-python` (absent du projet). Deux approches possibles, à trancher avec vous avant de coder :
    - **Détection automatique des 4 coins de page** (contour le plus grand détecté par `cv2.findContours` après un seuillage) + `cv2.getPerspectiveTransform`/`warpPerspective` — entièrement automatique mais fragile si le fond de la photo (table, tapis) a un contraste proche de la page.
    - **Recadrage manuel assisté** : l'utilisateur clique les 4 coins de la page sur l'aperçu (comme pour Aperçu découpe), l'appli calcule la transformation — moins « magique » mais beaucoup plus fiable et plus simple à implémenter/tester.
    Recommandation : commencer par l'option manuelle (moins de risque de régression, résultat prévisible), l'automatique pouvant venir en option plus tard.
11. Si la courbure de reliure (page qui se creuse près du pli, indépendamment de la perspective globale) reste un problème après le point 10, envisager une correction de courbure locale (plus complexe, à évaluer seulement si le besoin est confirmé sur des photos réelles).

---

## 4. Recommandation de méthode

Avant d'attaquer l'étape E (perspective/courbure), il serait utile de **tester le pipeline actuel (post étape C/D) sur un petit lot de vraies photos** prises dans vos conditions réelles (main levée, éclairage de bureau, livre ouvert) pour vérifier empiriquement :
- si le Mode photo (une fois les bugs §2.2/§2.3 corrigés) suffit déjà à obtenir un OCR exploitable ;
- ou si la déformation de perspective/courbure est effectivement le facteur limitant, auquel cas l'effort de l'étape E est justifié.

Cela évite d'investir dans OpenCV et une détection de coins si le gain réel s'avère faible une fois les bugs EXIF et l'ordre du pipeline corrigés.
