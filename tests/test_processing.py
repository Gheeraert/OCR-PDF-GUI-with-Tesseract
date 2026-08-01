"""Tests unitaires des fonctions pures de ocr_pdf_gui.py (traitement d'image / texte).

Ne couvre pas l'interface Tkinter elle-même (OCRApp), seulement les fonctions
de module utilisées par le pipeline OCR : ce sont celles qui bougent le plus
souvent (réglages de découpe, mode photo) et les plus faciles à casser en
silence lors d'un futur ajustement.
"""
import io
import os
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ocr_pdf_gui import (
    adaptive_threshold,
    configure_tesseract,
    cv2,
    deskew_image,
    dewarp_page,
    estimate_skew_angle,
    find_gutter_x,
    list_images_in_folder,
    list_unsupported_images_in_folder,
    natural_sort_key,
    normalize_illumination,
    open_photo,
    otsu_thresh,
    postprocess_text,
    split_double_page,
)

configure_tesseract()  # necessaire aux tests de dewarp_page, qui s'appuient sur Tesseract pour detecter les lignes

requires_cv2 = pytest.mark.skipif(cv2 is None, reason="opencv-python-headless non installé")

try:
    _TEST_FONT = ImageFont.truetype("arial.ttf", 28)
except Exception:
    _TEST_FONT = ImageFont.load_default()


# ---------- tri naturel / listage de dossier ----------

def test_natural_sort_key_orders_numbers_not_lexicographically():
    names = ["page10.jpg", "page2.jpg", "page1.jpg"]
    assert sorted(names, key=natural_sort_key) == ["page1.jpg", "page2.jpg", "page10.jpg"]


def test_list_images_in_folder_filters_and_sorts(tmp_path):
    for name in ["page10.jpg", "page2.PNG", "notes.txt", "page1.jpeg"]:
        (tmp_path / name).write_bytes(b"")
    result = [os.path.basename(p) for p in list_images_in_folder(str(tmp_path))]
    assert result == ["page1.jpeg", "page2.PNG", "page10.jpg"]


def test_list_unsupported_images_in_folder_detects_heic(tmp_path):
    (tmp_path / "IMG_001.HEIC").write_bytes(b"")
    (tmp_path / "page2.jpg").write_bytes(b"")
    assert list_unsupported_images_in_folder(str(tmp_path)) == ["IMG_001.HEIC"]


# ---------- ouverture de photo / EXIF ----------

def _write_jpeg_with_orientation_tag(tmp_path, orientation=6):
    img = Image.new("RGB", (100, 60), "white")
    exif = img.getexif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    path = tmp_path / "photo.jpg"
    path.write_bytes(buf.getvalue())
    return str(path)


def test_open_photo_default_ignores_exif_orientation(tmp_path):
    # Défaut à apply_exif=False : certains Android (vérifié sur un Galaxy A54 5G
    # réel) enregistrent une balise Orientation obsolète alors que les pixels
    # sont déjà correctement orientés ; appliquer la rotation par défaut
    # tournerait ces photos à tort.
    path = _write_jpeg_with_orientation_tag(tmp_path, orientation=6)
    assert open_photo(path).size == (100, 60)


def test_open_photo_applies_exif_orientation_when_requested(tmp_path):
    # Sur les appareils qui suivent la convention EXIF standard (iPhone
    # notamment), apply_exif=True doit permuter les dimensions.
    path = _write_jpeg_with_orientation_tag(tmp_path, orientation=6)
    assert open_photo(path, apply_exif=True).size == (60, 100)


# ---------- seuillage / gouttière ----------

def test_otsu_thresh_separates_bimodal_distribution():
    # Un léger bruit gaussien simule la variation continue d'une vraie image
    # (une distribution parfaitement bimodale à 2 valeurs est un cas dégénéré
    # qui ne se produit jamais sur une photo ou un scan réel).
    rng = np.random.default_rng(0)
    low = np.clip(rng.normal(20, 4, 500), 0, 255).astype(np.uint8)
    high = np.clip(rng.normal(220, 4, 500), 0, 255).astype(np.uint8)
    arr = np.concatenate([low, high])
    t = otsu_thresh(arr)
    assert 20 < t < 220


def _make_double_page(width=1000, height=700, gutter_x=None):
    """Fabrique une image de double page : deux blocs de texte séparés par une
    bande claire (la gouttière) à gutter_x (par défaut, le centre). Un léger flou
    simule l'anti-aliasing/le grain d'une vraie photo (une image binaire parfaite
    est un cas dégénéré pour le seuillage Otsu, cf. test_otsu_thresh_*)."""
    if gutter_x is None:
        gutter_x = width // 2
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    for y in range(20, height - 20, 8):
        draw.line([(30, y), (gutter_x - 30, y)], fill=0, width=5)
        draw.line([(gutter_x + 30, y), (width - 30, y)], fill=0, width=5)
    return img.filter(ImageFilter.GaussianBlur(radius=1.0))


def test_find_gutter_x_locates_gutter_near_expected_position():
    gutter_x = 420
    img = _make_double_page(width=1000, gutter_x=gutter_x)
    found = find_gutter_x(img, central_frac=0.6, smooth_px=15)
    assert abs(found - gutter_x) < 30


def test_split_double_page_half_mode_returns_two_equal_halves():
    img = _make_double_page(width=1000, height=700)
    left, right = split_double_page(img, mode="half")
    assert left.size == (500, 700)
    assert right.size == (500, 700)


def test_split_double_page_single_page_ratio_returns_one_image():
    # Ratio largeur/hauteur < 1.28 : l'heuristique doit renoncer à découper.
    img = Image.new("L", (600, 900), color=255)
    result = split_double_page(img, mode="auto")
    assert len(result) == 1
    assert result[0].size == (600, 900)


# ---------- mode photo : éclairage, seuillage, deskew ----------

def test_normalize_illumination_reduces_lighting_gradient():
    w, h = 400, 300
    gradient = np.tile(np.linspace(80, 220, w), (h, 1)).astype(np.uint8)
    img = Image.fromarray(gradient, mode="L")

    normalized = normalize_illumination(img, blur_radius=31)
    arr = np.asarray(normalized, dtype=np.float32)

    col_means_before = gradient.astype(np.float32).mean(axis=0)
    col_means_after = arr.mean(axis=0)
    assert col_means_after.std() < col_means_before.std()


def test_adaptive_threshold_returns_pure_binary_image():
    w, h = 300, 200
    gradient = np.tile(np.linspace(60, 200, w), (h, 1)).astype(np.uint8)
    img = Image.fromarray(gradient, mode="L")

    binary = adaptive_threshold(img)
    values = set(np.unique(np.asarray(binary)).tolist())
    assert values <= {0, 255}


@pytest.mark.parametrize("true_angle", [3.0, -4.0])
def test_deskew_recovers_known_rotation_angle(true_angle):
    img = Image.new("L", (800, 500), color=255)
    draw = ImageDraw.Draw(img)
    for y in range(30, 470, 15):
        draw.line([(40, y), (760, y)], fill=0, width=3)
    rotated = img.rotate(true_angle, expand=True, fillcolor=255)

    _, estimated_angle = deskew_image(rotated, max_angle=8.0, step=0.5)
    # deskew_image doit tourner dans le sens opposé pour corriger la rotation appliquée
    assert abs(estimated_angle + true_angle) < 1.0


def test_estimate_skew_angle_ignores_dark_border_padding_artifact():
    # Régression : rotate(..., expand=False, fillcolor=0) remplit les coins avec du
    # noir, ce qui — combiné à une bordure sombre réaliste (cadre décoratif, fond de
    # photo) — faisait diverger l'estimation vers max_angle au lieu de détecter que
    # le texte est déjà droit (reproduit sur de vraies photos smartphone).
    img = Image.new("L", (800, 600), color=255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (799, 599)], outline=0, width=40)
    for y in range(80, 520, 15):
        draw.line([(80, y), (720, y)], fill=0, width=3)

    for max_angle in (5.0, 10.0, 15.0, 20.0):
        angle = estimate_skew_angle(img, max_angle=max_angle, step=0.5)
        assert angle == 0.0, f"max_angle={max_angle} a divergé vers {angle}"


def test_estimate_skew_angle_is_near_zero_for_already_straight_image():
    img = Image.new("L", (800, 500), color=255)
    draw = ImageDraw.Draw(img)
    for y in range(30, 470, 15):
        draw.line([(40, y), (760, y)], fill=0, width=3)
    angle = estimate_skew_angle(img, max_angle=5.0, step=0.5)
    assert abs(angle) <= 0.5


# ---------- correction de courbure (dewarp_page) ----------
#
# dewarp_page s'appuie sur Tesseract (pytesseract.image_to_data) pour regrouper
# les mots en lignes réelles — plus robuste qu'une heuristique d'image pure sur
# du texte dense/resserré (notes, citations), mais cela signifie que les images
# de test doivent contenir du VRAI texte reconnaissable (pas de simples traits),
# d'où le rendu via une police plutôt que ImageDraw.line.

_WORDS = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur",
          "adipiscing", "elit", "sed", "vulputate", "libero", "nec"]


def _draw_curved_text_line(draw, font, base_y, curve_fn, x_start, x_end, word_gap=16, words=None):
    x = x_start
    i = 0
    words = words or _WORDS
    while x < x_end:
        word = words[i % len(words)]
        y = base_y + curve_fn(x)
        draw.text((x, y), word, fill=0, font=font)
        x = draw.textbbox((x, y), word, font=font)[2] + word_gap
        i += 1


def _make_curved_lines_image(w=1400, h=1800, amplitude=40, extra_short_line=False):
    """Simule une page dont les lignes de texte gondolent près de la reliure
    (courbure parabolique croissante vers la gauche, comme observé sur de vraies
    photos de livre ouvert)."""
    img = Image.new("L", (w, h), color=255)
    draw = ImageDraw.Draw(img)

    def curve_offset(x):
        t = (x - w * 0.15) / (w * 0.85)
        return amplitude * (t ** 2)

    for base_y in range(80, h - 80, 55):
        _draw_curved_text_line(draw, _TEST_FONT, base_y, curve_offset, 60, w - 60)

    if extra_short_line:
        # ligne courte hors du corps de texte (ex. titre courant), loin du bord
        # gauche : reproduit le cas qui faisait diverger l'extrapolation polynomiale.
        _draw_curved_text_line(draw, _TEST_FONT, 20, lambda x: 0, int(w * 0.75), int(w * 0.92),
                                words=["Fig", "3", "Ibid"])

    return img


@requires_cv2
def test_dewarp_page_straightens_curved_lines():
    img = _make_curved_lines_image()
    dewarped, applied, bbox = dewarp_page(img, min_lines=4)
    assert applied is True
    assert bbox is not None

    from ocr_pdf_gui import _detect_text_line_points

    def line_stds(pil_img):
        arr = np.asarray(pil_img.convert("L"))
        _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return [ys.std() for _, ys in _detect_text_line_points(bw)]

    stds_before = line_stds(img)
    stds_after = line_stds(dewarped)
    assert min(stds_before) > 5.0  # les lignes sont bien courbes au départ
    assert max(stds_after) < 5.0  # et nettement redressées après coup


@requires_cv2
def test_dewarp_page_returns_unchanged_when_too_few_lines():
    blank = Image.new("L", (400, 300), color=255)
    result_img, applied, bbox = dewarp_page(blank, min_lines=4)
    assert applied is False
    assert bbox is None
    assert result_img is blank


@requires_cv2
def test_dewarp_page_ignores_tall_border_component():
    # Régression : sur une vraie photo, la bordure décorative du livre formait une
    # composante connexe couvrant 81% de la hauteur de l'image et corrompait tout
    # le champ de déplacement. Une bordure verticale haute ne doit pas empêcher un
    # dewarping correct du texte à l'intérieur.
    img = _make_curved_lines_image(amplitude=30)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (15, img.height - 1)], fill=0)  # bordure verticale fine et haute

    dewarped, applied, bbox = dewarp_page(img, min_lines=4)
    assert applied is True
    # la bordure ne doit pas être incluse dans la zone de texte détectée
    assert bbox[0] > 20


@requires_cv2
def test_dewarp_page_short_offaxis_line_does_not_corrupt_result():
    # Régression : une ligne courte hors du corps de texte (ex. titre courant),
    # extrapolée sur toute la largeur par son polynôme, divergeait et corrompait
    # le champ de déplacement à des positions x éloignées de son propre domaine.
    img = _make_curved_lines_image(extra_short_line=True)
    dewarped, applied, bbox = dewarp_page(img, min_lines=4)
    assert applied is True
    assert dewarped.size == img.size


@requires_cv2
def test_dewarp_page_detects_short_tightly_spaced_lines():
    # Le cas explicitement demandé : notes de bas de page / citations, avec des
    # lignes plus courtes que le corps de texte et à interligne plus serré.
    # Elles doivent être détectées comme des lignes à part entière (pas fusionnées
    # ni ignorées), pour fournir une courbure mesurée plutôt que seulement
    # extrapolée depuis le corps de texte.
    w, h = 1400, 1800
    img = Image.new("L", (w, h), color=255)
    draw = ImageDraw.Draw(img)

    def curve_offset(x):
        t = (x - w * 0.15) / (w * 0.85)
        return 35 * (t ** 2)

    for base_y in range(80, 900, 55):
        _draw_curved_text_line(draw, _TEST_FONT, base_y, curve_offset, 60, w - 60)

    small_font = ImageFont.truetype("arial.ttf", 16) if _TEST_FONT != ImageFont.load_default() else _TEST_FONT
    draw.line([(60, 950), (w - 60, 950)], fill=0, width=2)  # règle de séparation des notes
    for base_y in range(970, h - 30, 26):  # interligne serré, lignes plus courtes
        _draw_curved_text_line(draw, small_font, base_y, curve_offset, 60, int(w * 0.55), word_gap=10)

    from ocr_pdf_gui import _detect_text_line_points

    arr = np.asarray(img)
    _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    lines = _detect_text_line_points(bw)
    footnote_lines = [ys for xs, ys in lines if ys.mean() > 950]
    assert len(footnote_lines) >= 3, "les lignes de notes ne sont pas détectées individuellement"


# ---------- post-traitement texte ----------

def test_postprocess_text_reflow_true_joins_single_linebreaks():
    raw = "Premier mot\ndeuxième mot\n\nNouveau paragraphe"
    out = postprocess_text(raw, reflow=True)
    assert out == "Premier mot deuxième mot\n\nNouveau paragraphe"


def test_postprocess_text_reflow_false_preserves_linebreaks():
    raw = "Premier mot\ndeuxième mot\n\nNouveau paragraphe"
    out = postprocess_text(raw, reflow=False)
    assert out == "Premier mot\ndeuxième mot\n\nNouveau paragraphe"


def test_postprocess_text_dehyphenates_across_linebreak():
    raw = "un mot cou-\npé en deux"
    out = postprocess_text(raw, reflow=True)
    assert "coupé" in out
