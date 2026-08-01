# TODO

Suivi des points ouverts identifiés lors des sessions d'audit/développement (voir `AUDIT.md` pour le détail complet et l'historique). Un seul point ouvert à ce jour.

---

## Bordure décorative laissée dans le cadre à cause d'une règle de séparation pleine largeur

**Statut** : non résolu, mis au jour en creusant l'amélioration des notes de bas de page (§7.5 de `AUDIT.md`).

**Symptôme** : sur certaines photos, l'image *visuellement* quasi parfaite après correction de courbure (`dewarp_page`) donne pourtant un OCR dégradé par endroits (mots réels mais mélangés dans le désordre).

**Cause identifiée** : une règle de séparation des notes de bas de page (trait horizontal, pleine largeur) est acceptée à tort comme une "ligne de texte" par `_detect_text_line_points` — elle a une hauteur et une dispersion verticale compatibles avec les filtres actuels. Résultat : la boîte englobante calculée pour le recadrage (`bbox` dans `dewarp_page`) s'étend jusqu'au bord de l'image, laissant la bordure décorative du livre dans le cadre. Cette bordure perturbe ensuite l'ordre de lecture de Tesseract (segmentation de page confuse entre le texte et le motif décoratif).

**Piste déjà essayée et écartée** : distinguer une règle graphique d'une vraie ligne de texte via le taux de colonnes encrées après dilatation horizontale (`coverage = colonnes_avec_encre / largeur_composante`). Ne fonctionne pas : la dilatation nécessaire pour regrouper les caractères d'une ligne comble aussi les espaces entre mots d'une vraie ligne de texte, donnant 100 % de couverture dans les deux cas — aucune séparation possible avec cette mesure.

**Pistes à explorer pour la suite** (non tentées) :
- Détecter spécifiquement les traits fins et quasi parfaitement horizontaux (variance verticale proche de zéro sur toute leur largeur, contrairement à une vraie ligne de texte qui a toujours un peu de texture même après dilatation) et les exclure explicitement avant le calcul de la bbox.
- Reprendre le sujet plus général de la détection de bordure/page (déjà identifié comme limite connue indépendamment de ce cas précis) plutôt qu'un correctif ponctuel sur les règles de séparation.
- Vérifier si le problème se reproduit sur un plus grand échantillon de photos avant d'investir, pour éviter de sur-ajuster à un seul cas observé.
