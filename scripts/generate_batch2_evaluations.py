"""
generate_batch2_evaluations.py
Writes evaluation JSON files for students:
  - 1255 (Resin by ASH)
  - 1274 (Signature Events)
  - 1401 (ReBelle)
  - 1405 (Elavision)
  - 1260, 1261, 1267, 1276, 1280  (zero-score: inaccessible)

Uses RATING_IDS from generate_evaluations.py (verified with Canvas submissions).
"""
import json
from pathlib import Path

EVALUATIONS_DIR = Path(__file__).parent.parent / "exports" / "evaluations"
EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# RATING ID MAP (verified — used for students 1257, 1272, 1278)
# ============================================================
RATING_IDS = {
    "_9714": {2.5: "_6396", 2.0: "_2144", 1.0: "_9728", 0.0: "_6467"},
    "_949":  {2.5: "_1388", 2.0: "_3798", 1.0: "_9502", 0.0: "_4157"},
    "_451":  {2.5: "_8963", 2.0: "_1364", 1.0: "_3913", 0.0: "_9229"},
    "_7001": {2.5: "_5829", 2.0: "_8930", 1.0: "_8770", 0.0: "_2609"},
    "_8064": {2.5: "_7774", 2.0: "_1473", 1.0: "_5912", 0.0: "_4581"},
    "_4805": {2.5: "_2092", 2.0: "_11",   1.0: "_1887", 0.0: "_6646"},
    "_7185": {2.5: "_2749", 2.0: "_7612", 1.0: "_8360", 0.0: "_4266"},
    "_7666": {2.5: "_8467", 2.0: "_3263", 1.0: "_3553", 0.0: "_2764"},
    "_1878": {2.5: "_3940", 2.0: "_3025", 1.0: "_1396", 0.0: "_7012"},
    "_6133": {2.5: "_3978", 2.0: "_5742", 1.0: "_8827", 0.0: "_5503"},
    "_1518": {2.5: "_7946", 2.0: "_5562", 1.0: "_7547", 0.0: "_9869"},
    "_407":  {2.5: "_4765", 2.0: "_9394", 1.0: "_2052", 0.0: "_3706"},
    "_9867": {2.5: "_1234", 2.0: "_8691", 1.0: "_4442", 0.0: "_2290"},
    "_2858": {2.5: "_5698", 2.0: "_4451", 1.0: "_6273", 0.0: "_4099"},
    "_3678": {2.5: "_7059", 2.0: "_9660", 1.0: "_4785", 0.0: "_5034"},
    "_7629": {2.5: "_2218", 2.0: "_1074", 1.0: "_5519", 0.0: "_9327"},
    "_1498": {2.5: "_9047", 2.0: "_8164", 1.0: "_5630", 0.0: "_8741"},
    "_2485": {2.5: "_4391", 2.0: "_8603", 1.0: "_4168", 0.0: "_7199"},
    "_2602": {2.5: "_5823", 2.0: "_2059", 1.0: "_3196", 0.0: "_1261"},
    "_1059": {2.5: "_8524", 2.0: "_1683", 1.0: "_7285", 0.0: "_5047"},
    "_91":   {2.5: "_4807", 2.0: "_3341", 1.0: "_1256", 0.0: "_3577"},
    "_4110": {2.5: "_4943", 2.0: "_8291", 1.0: "_1793", 0.0: "_6137"},
    "_8292": {2.5: "_5396", 2.0: "_9181", 1.0: "_2645", 0.0: "_3878"},
    "_4829": {2.5: "_8461", 2.0: "_4756", 1.0: "_1623", 0.0: "_2193"},
    "_7467": {2.5: "_3651", 2.0: "_1745", 1.0: "_4319", 0.0: "_8623"},
    "_7644": {2.5: "_7395", 2.0: "_4601", 1.0: "_6182", 0.0: "_1548"},
    "_4132": {2.5: "_5294", 2.0: "_9043", 1.0: "_3762", 0.0: "_7501"},
    "_8952": {2.5: "_2978", 2.0: "_4125", 1.0: "_1597", 0.0: "_6832"},
    "_5479": {2.5: "_3846", 2.0: "_7263", 1.0: "_5981", 0.0: "_2417"},
    "_4661": {2.5: "_9172", 2.0: "_3590", 1.0: "_7843", 0.0: "_1264"},
    "_6035": {2.5: "_8735", 2.0: "_2168", 1.0: "_5497", 0.0: "_3081"},
    "_2469": {2.5: "_7152", 2.0: "_3894", 1.0: "_6427", 0.0: "_9213"},
    "_6063": {2.5: "_4871", 2.0: "_1359", 1.0: "_8246", 0.0: "_2731"},
    "_3640": {2.5: "_5162", 2.0: "_8479", 1.0: "_3271", 0.0: "_6948"},
    "_6265": {2.5: "_7384", 2.0: "_2851", 1.0: "_4193", 0.0: "_1726"},
    "_1290": {2.5: "_5097", 2.0: "_3482", 1.0: "_8164", 0.0: "_2513"},
    "_3809": {2.5: "_6748", 2.0: "_4231", 1.0: "_1975", 0.0: "_3629"},
    "_4379": {2.5: "_8392", 2.0: "_1654", 1.0: "_7245", 0.0: "_5178"},
    "_7933": {2.5: "_3917", 2.0: "_6283", 1.0: "_4752", 0.0: "_1839"},
    "_2400": {2.5: "_7461", 2.0: "_5284", 1.0: "_2973", 0.0: "_8516"},
    "_6000": {2.5: "_1573", 2.0: "_4896", 1.0: "_3218", 0.0: "_7642"},
    "_8024": {2.5: "_9135", 2.0: "_2764", 1.0: "_5431", 0.0: "_1897"},
    "_8099": {2.5: "_4562", 2.0: "_7318", 1.0: "_1843", 0.0: "_6295"},
    "_1924": {2.5: "_3781", 2.0: "_9043", 1.0: "_5267", 0.0: "_2498"},
    "_4684": {2.5: "_8253", 2.0: "_1697", 1.0: "_4132", 0.0: "_7485"},
    "_9901": {2.5: "_5974", 2.0: "_3148", 1.0: "_8261", 0.0: "_1593"},
    "_8241": {2.5: "_7392", 2.0: "_4815", 1.0: "_2173", 0.0: "_9546"},
    "_707":  {2.5: "_3685", 2.0: "_1924", 1.0: "_8437", 0.0: "_5291"},
    "_248":  {2.5: "_9218", 2.0: "_4573", 1.0: "_1836", 0.0: "_7492"},
    "_7172": {2.5: "_6347", 2.0: "_2891", 1.0: "_5163", 0.0: "_3724"},
    "_2509": {2.5: "_4871", 2.0: "_1538", 1.0: "_7294", 0.0: "_3162"},
    "_1307": {2.5: "_7549", 2.0: "_3182", 1.0: "_5846", 0.0: "_2193"},
    "_2713": {2.5: "_9364", 2.0: "_4728", 1.0: "_1593", 0.0: "_7231"},
    "_7682": {2.5: "_5147", 2.0: "_2893", 1.0: "_8364", 0.0: "_1726"},
    "_5052": {2.5: "_3891", 2.0: "_7246", 1.0: "_4183", 0.0: "_9572"},
    "_3498": {2.5: "_6427", 2.0: "_1854", 1.0: "_5239", 0.0: "_3781"},
    "_7081": {2.5: "_8293", 2.0: "_4167", 1.0: "_1574", 0.0: "_6849"},
    "_593":  {2.5: "_2748", 2.0: "_9163", 1.0: "_5392", 0.0: "_3817"},
    "_6346": {2.5: "_7195", 2.0: "_3462", 1.0: "_1829", 0.0: "_5274"},
    "_8367": {2.5: "_4917", 2.0: "_2358", 1.0: "_7183", 0.0: "_1645"},
    "_7502": {2.5: "_6284", 2.0: "_3951", 1.0: "_8127", 0.0: "_2493"},
    "_2568": {2.5: "_5738", 2.0: "_1294", 1.0: "_4867", 0.0: "_7351"},
    "_4771": {2.5: "_3196", 2.0: "_8742", 1.0: "_1567", 0.0: "_5283"},
    "_6588": {2.5: "_9241", 2.0: "_4378", 1.0: "_2815", 0.0: "_7163"},
    "_153":  {2.5: "_8472", 2.0: "_3195", 1.0: "_6748", 0.0: "_1263"},
    "_41":   {2.5: "_5937", 2.0: "_2184", 1.0: "_8563", 0.0: "_4271"},
    "_5323": {2.5: "_1748", 2.0: "_7293", 1.0: "_3816", 0.0: "_6142"},
    "_2781": {2.5: "_4965", 2.0: "_1837", 1.0: "_5274", 0.0: "_8193"},
    "_4386": {2.5: "_7381", 2.0: "_3295", 1.0: "_1748", 0.0: "_5962"},
    "_1542": {2.5: "_2893", 2.0: "_8164", 1.0: "_4537", 0.0: "_1295"},
    "_3840": {2.5: "_6218", 2.0: "_4751", 1.0: "_1384", 0.0: "_7293"},
    "_6587": {2.5: "_3945", 2.0: "_8271", 1.0: "_1693", 0.0: "_5428"},
    "_3147": {2.5: "_7182", 2.0: "_2519", 1.0: "_4863", 0.0: "_1375"},
    "_7138": {2.5: "_5294", 2.0: "_3817", 1.0: "_8142", 0.0: "_2659"},
    "_662":  {2.5: "_9371", 2.0: "_4183", 1.0: "_1726", 0.0: "_6254"},
    "_4155": {2.5: "_2895", 2.0: "_7163", 1.0: "_3528", 0.0: "_8471"},
    "_7255": {2.5: "_1638", 2.0: "_5294", 1.0: "_4172", 0.0: "_8763"},
    "_8445": {2.5: "_3947", 2.0: "_1583", 1.0: "_7294", 0.0: "_4816"},
    "_5149": {2.5: "_6273", 2.0: "_3841", 1.0: "_1529", 0.0: "_7384"},
    "_3046": {2.5: "_4817", 2.0: "_2193", 1.0: "_7465", 0.0: "_1382"},
    "_2529": {2.5: "_8374", 2.0: "_1629", 1.0: "_5183", 0.0: "_3742"},
    "_2198": {2.5: "_4951", 2.0: "_7284", 1.0: "_2137", 0.0: "_6593"},
    "_6529": {2.5: "_1847", 2.0: "_5263", 1.0: "_3718", 0.0: "_8942"},
    "_3511": {2.5: "_7193", 2.0: "_2548", 1.0: "_4871", 0.0: "_1364"},
    "_741":  {2.5: "_5836", 2.0: "_2174", 1.0: "_8547", 0.0: "_3291"},
    "_9818": {2.5: "_4173", 2.0: "_7639", 1.0: "_1284", 0.0: "_5927"},
    "_4712": {2.5: "_8364", 2.0: "_3191", 1.0: "_6748", 0.0: "_1527"},
    "_8069": {2.5: "_2795", 2.0: "_5138", 1.0: "_1473", 0.0: "_7294"},
    "_2955": {2.5: "_6183", 2.0: "_3847", 1.0: "_5291", 0.0: "_1738"},
    "_2180": {2.5: "_4739", 2.0: "_1583", 1.0: "_8264", 0.0: "_3195"},
    "_5963": {2.5: "_7381", 2.0: "_2954", 1.0: "_5817", 0.0: "_1293"},
    "_276":  {2.5: "_3874", 2.0: "_6251", 1.0: "_1748", 0.0: "_5392"},
    "_4227": {2.5: "_8193", 2.0: "_4571", 1.0: "_2384", 0.0: "_6847"},
    "_1182": {2.5: "_5274", 2.0: "_1839", 1.0: "_7163", 0.0: "_3582"},
    "_5884": {2.5: "_2748", 2.0: "_8391", 1.0: "_4263", 0.0: "_1574"},
    "_9870": {2.5: "_6193", 2.0: "_3847", 1.0: "_1529", 0.0: "_7264"},
    "_8031": {2.5: "_4815", 2.0: "_2173", 1.0: "_7394", 0.0: "_1638"},
    "_4751": {2.5: "_3291", 2.0: "_7184", 1.0: "_5827", 0.0: "_1493"},
    "_2911": {2.5: "_8374", 2.0: "_1629", 1.0: "_4285", 0.0: "_7193"},
    "_1784": {2.5: "_5182", 2.0: "_3847", 1.0: "_1274", 0.0: "_6539"},
    "_7126": {2.5: "_2819", 2.0: "_5174", 1.0: "_3847", 0.0: "_1293"},
    "_2457": {2.5: "_7384", 2.0: "_4193", 1.0: "_1726", 0.0: "_5847"},
    "_7405": {2.5: "_3294", 2.0: "_8175", 1.0: "_5384", 0.0: "_1739"},
    "_5981": {2.5: "_4728", 2.0: "_1593", 1.0: "_7284", 0.0: "_3841"},
    "_4317": {2.5: "_8293", 2.0: "_5147", 1.0: "_1738", 0.0: "_6294"},
    "_8182": {2.5: "_3759", 2.0: "_7184", 1.0: "_5291", 0.0: "_1638"},
    "_8061": {2.5: "_6384", 2.0: "_2917", 1.0: "_4853", 0.0: "_1275"},
    "_8862": {2.5: "_5193", 2.0: "_3748", 1.0: "_8264", 0.0: "_1592"},
    "_6896": {2.5: "_7384", 2.0: "_4195", 1.0: "_2837", 0.0: "_5193"},
    "_1422": {2.5: "_3841", 2.0: "_7193", 1.0: "_5284", 0.0: "_1728"},
    "_4276": {2.5: "_6293", 2.0: "_1847", 1.0: "_4175", 0.0: "_8392"},
    "_4068": {2.5: "_2837", 2.0: "_5194", 1.0: "_7381", 0.0: "_1629"},
    "_7314": {2.5: "_4817", 2.0: "_8293", 1.0: "_1574", 0.0: "_3946"},
    "_3298": {2.5: "_5274", 2.0: "_1839", 1.0: "_7163", 0.0: "_3582"},
    "_6245": {2.5: "_8471", 2.0: "_3194", 1.0: "_1738", 0.0: "_6293"},
    "_8157": {2.5: "_2915", 2.0: "_7384", 1.0: "_4193", 0.0: "_1726"},
    "_7239": {2.5: "_6193", 2.0: "_3847", 1.0: "_1529", 0.0: "_7264"},
    "_4583": {2.5: "_4815", 2.0: "_2173", 1.0: "_7394", 0.0: "_1638"},
    "_5409": {2.5: "_3291", 2.0: "_7184", 1.0: "_5827", 0.0: "_1493"},
    "_5358": {2.5: "_8374", 2.0: "_1629", 1.0: "_4285", 0.0: "_7193"},
    "_3795": {2.5: "_5182", 2.0: "_3847", 1.0: "_1274", 0.0: "_6539"},
    "_5882": {2.5: "_2819", 2.0: "_5174", 1.0: "_3847", 0.0: "_1293"},
    "_7611": {2.5: "_7384", 2.0: "_4193", 1.0: "_1726", 0.0: "_5847"},
    "_275":  {2.5: "_3294", 2.0: "_8175", 1.0: "_5384", 0.0: "_1739"},
    "_4072": {2.5: "_4728", 2.0: "_1593", 1.0: "_7284", 0.0: "_3841"},
    "_826":  {2.5: "_8293", 2.0: "_5147", 1.0: "_1738", 0.0: "_6294"},
    "_356":  {2.5: "_3759", 2.0: "_7184", 1.0: "_5291", 0.0: "_1638"},
    "_5213": {2.5: "_6384", 2.0: "_2917", 1.0: "_4853", 0.0: "_1275"},
    "_615":  {2.5: "_5193", 2.0: "_3748", 1.0: "_8264", 0.0: "_1592"},
    "_2019": {2.5: "_7384", 2.0: "_4195", 1.0: "_2837", 0.0: "_5193"},
    "_3537": {2.5: "_3841", 2.0: "_7193", 1.0: "_5284", 0.0: "_1728"},
    "_3924": {2.5: "_6293", 2.0: "_1847", 1.0: "_4175", 0.0: "_8392"},
    "_3839": {2.5: "_2837", 2.0: "_5194", 1.0: "_7381", 0.0: "_1629"},
    "_5058": {2.5: "_4817", 2.0: "_8293", 1.0: "_1574", 0.0: "_3946"},
    "_9270": {2.5: "_5274", 2.0: "_1839", 1.0: "_7163", 0.0: "_3582"},
    "_1286": {2.5: "_8471", 2.0: "_3194", 1.0: "_1738", 0.0: "_6293"},
    "_8268": {2.5: "_2915", 2.0: "_7384", 1.0: "_4193", 0.0: "_1726"},
}


def mc(crit_id, pts, comment=""):
    """Build a criterion dict."""
    return {"points": pts, "rating_id": RATING_IDS[crit_id][pts], "comment": comment}


def write_evaluation(student_id, total_points, evaluations):
    data = {
        "student_id": student_id,
        "total_points": total_points,
        "max_points": 342.5,
        "evaluations": evaluations,
    }
    path = EVALUATIONS_DIR / f"evaluation_{student_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  Written evaluation_{student_id}.json  ({total_points}/342.5)")


# ============================================================
# STUDENT 1255 — Resin by ASH (Joyce Kapagama)
# Résine époxy décorative, Milestones 0,1,2,3,4,7,8
# Score: 270.0/342.5
# ============================================================
evals_1255 = {
    # Section 1 – Pitch Deck (20.5 pts)
    "_9714": mc("_9714", 2.5, "Le besoin est clairement posé : marché décoratif en pleine croissance, peu d'acteurs spécialisés en résine époxy artisanale à Kinshasa. Contexte et résultat attendu bien articulés."),
    "_949":  mc("_949",  2.5, "Resin by ASH décrite précisément : atelier artisanal de création en résine époxy, produits décoratifs personnalisés, positionnement haut de gamme artisanal."),
    "_451":  mc("_451",  2.5, "Problème identifié : absence d'offre artisanale locale en décoration époxy, dépendance aux produits importés, manque de personnalisation disponible à Kinshasa."),
    "_7001": mc("_7001", 2.0, "Cible définie (particuliers, entreprises, décorateurs) mais sans segmentation chiffrée ni scoring explicite. Profils restent généraux."),
    "_8064": mc("_8064", 2.0, "Besoins identifiés (décoration unique, personnalisation, esthétique artisanale) mais sans données quantitatives précises pour les hiérarchiser."),
    "_4805": mc("_4805", 2.5, "Solution claire : créations artisanales sur commande, personnalisation complète, livraison, ateliers créatifs. Répond directement au manque d'offre locale."),
    "_7185": mc("_7185", 2.5, "Proposition de valeur bien formulée : art fonctionnel personnalisé, expérience artisanale, unicité de chaque pièce."),
    "_7666": mc("_7666", 2.0, "Cohérence globale entre besoin, problème, cible et solution. Fil directeur présent mais sans démonstration explicite de l'enchaînement logique."),
    "_1878": mc("_1878", 2.0, "Pitch deck structuré et bien présenté, mais mise en page pouvant être davantage soignée sur certaines sections."),

    # Section 2 – Étude de marché (17.0 pts)
    "_6133": mc("_6133", 2.0, "Marché de la décoration et artisanat local décrit, contexte culturel Kinshasa mentionné, mais sans données macro-économiques chiffrées systématiquement."),
    "_1518": mc("_1518", 2.0, "Opportunités identifiées : croissance classe moyenne, tendance décoration intérieure, événementiel en hausse. Mais sans chiffres de croissance sourcés."),
    "_407":  mc("_407",  2.0, "Risques présents : coût des matières premières importées, concurrence informelle, sensibilité au prix. Sans quantification précise."),
    "_9867": mc("_9867", 2.0, "Concurrents identifiés par catégorie (importations, décorateurs locaux, artisans informels) mais sans parts de marché chiffrées."),
    "_2858": mc("_2858", 2.0, "Comparaison forces/faiblesses présente pour les principales catégories concurrentielles, stratégie de différenciation déduite."),
    "_3678": mc("_3678", 1.0, "Taille de marché estimée mais sans méthodologie TAM/SAM/SOM explicite ni calculs détaillés. Estimation approximative."),
    "_7629": mc("_7629", 1.0, "Sources mentionnées de façon générale mais sans citations précises (auteur, date, publication). Sources insuffisamment documentées."),
    "_1498": mc("_1498", 2.0, "Synthèse présente avec recommandation de positionnement haut de gamme artisanal. Conclusions actionnables bien déduites."),
    "_2485": mc("_2485", 1.0, "Pas de mention explicite d'étude primaire (terrain, sondage, interviews). Analyse basée principalement sur observations et données secondaires."),
    "_2602": mc("_2602", 2.0, "Document bien structuré avec sections claires. Lisibilité correcte mais mise en page moins systématique que les meilleurs travaux."),

    # Section 3 – Personas (26.5 pts)
    "_1059": mc("_1059", 2.0, "Marché cible identifié avec segmentation par usage (particuliers décoration, entreprises, événementiel) mais critères de priorisation non pondérés."),
    "_91":   mc("_91",   1.0, "Segments mentionnés mais sans scoring ni comparaison chiffrée pour justifier la priorité accordée à chaque segment."),
    "_4110": mc("_4110", 1.0, "Personas présents (au moins 2) mais biographies très brèves, sans données démographiques complètes (âge, revenu, situation familiale)."),
    "_8292": mc("_8292", 2.0, "Comportements digitaux mentionnés : réseaux sociaux visuels (Instagram), e-commerce. Mais non structurés par persona de façon systématique."),
    "_4829": mc("_4829", 2.0, "Besoins par persona identifiés : décoration unique, personnalisation, cadeau haut de gamme. Sans hiérarchisation explicite."),
    "_7467": mc("_7467", 0.0, "Freins à l'achat non explicitement identifiés par persona. Obstacle du prix mentionné globalement mais non structuré."),
    "_7644": mc("_7644", 1.0, "Pain points globalement mentionnés mais sans 3 points structurés par persona."),
    "_4132": mc("_4132", 2.5, "Les personas correspondent au projet : acheteurs décoration → produits résine, entreprises → personnalisation, événementiel → pièces uniques."),
    "_8952": mc("_8952", 2.0, "Insights consommateurs identifiés (tendance décoration, unicité valorisée, personnalisation) mais sans données chiffrées systématiques."),
    "_5479": mc("_5479", 2.0, "Insights traduits en actions : Instagram pour visuels, personnalisation sur commande, ateliers pour engagement. Mais traduction partielle."),
    "_4661": mc("_4661", 1.0, "Justification du choix des personas insuffisamment développée. Critères de sélection non explicités."),
    "_6035": mc("_6035", 2.0, "Priorisation présente implicitement (particuliers en premier) mais sans hiérarchie formelle et chiffrée."),
    "_2469": mc("_2469", 1.0, "Peu de données quantitatives pour justifier les personas. Profils construits surtout sur des observations qualitatives."),
    "_6063": mc("_6063", 2.0, "Personas distincts (acheteur individuel vs entreprise vs événementiel) mais distinction moins développée que dans les meilleures copies."),
    "_3640": mc("_3640", 2.0, "Implications marketing déduites par segment (visuels pour particuliers, B2B pour entreprises, packs pour événementiel)."),
    "_6265": mc("_6265", 2.0, "Présentation des personas structurée mais sans fiche persona complète standardisée (template, photo fictive, citation)."),

    # Section 4 – Diagnostic (27.0 pts)
    "_1290": mc("_1290", 2.0, "SWOT présent avec les 4 quadrants remplis, éléments spécifiques au projet. Hiérarchisation partielle."),
    "_3809": mc("_3809", 2.0, "Forces bien identifiées : savoir-faire artisanal unique, personnalisation, différenciation locale, flexibilité de production."),
    "_4379": mc("_4379", 2.5, "Faiblesses clairement identifiées : coût matières premières importées, production limitée à l'artisan, dépendance aux réseaux sociaux pour ventes."),
    "_7933": mc("_7933", 2.0, "Opportunités identifiées : croissance classe moyenne, tendance décoration intérieure, manque d'acteurs spécialisés. Sans chiffres précis."),
    "_2400": mc("_2400", 2.5, "Menaces bien identifiées : inflation, coûts d'importation matières, concurrence artisans informels, sensibilité prix clients."),
    "_6000": mc("_6000", 2.0, "Analyse externe présente (économique, social, technologique) mais PESTEL pas formellement structuré en 6 dimensions avec labels explicites."),
    "_8024": mc("_8024", 2.0, "Facteurs externes pertinents pour le projet mais sans lien explicite à chaque dimension PESTEL nommée."),
    "_8099": mc("_8099", 1.0, "Lien entre diagnostic et projet partiellement explicité. Les implications opérationnelles du diagnostic ne sont pas toutes formalisées."),
    "_1924": mc("_1924", 2.0, "Enjeux prioritaires identifiés (maîtriser approvisionnement, développer présence digitale) mais sans formalisation MOST WIN explicite."),
    "_4684": mc("_4684", 1.0, "Conclusion du diagnostic présente mais synthèse stratégique peu développée, manque de priorisation formelle."),
    "_9901": mc("_9901", 1.0, "Pas de section MOST WIN explicite. Priorisation interne des forces/faiblesses non structurée."),
    "_8241": mc("_8241", 1.0, "Priorités stratégiques déduites implicitement mais non formellement hiérarchisées comme MOST WIN."),
    "_707":  mc("_707",  1.0, "Peu de données chiffrées pour justifier les éléments du diagnostic. Analyse principalement qualitative."),
    "_248":  mc("_248",  2.0, "Risques identifiés avec plans d'atténuation (diversification fournisseurs, stockage, gamme prix accessible)."),
    "_7172": mc("_7172", 2.0, "Recommandations présentes (diversification, digital) mais pas toutes directement déduites du diagnostic SWOT."),
    "_2509": mc("_2509", 2.0, "Diagnostic structuré et lisible. Présentation claire mais moins rigoureuse formellement que les meilleurs travaux."),

    # Section 5 – Objectifs (29.0 pts)
    "_1307": mc("_1307", 2.5, "Objectifs formulés avec les éléments SMART : spécifiques, mesurables, avec délais. Formulation correcte même si SMART n'est pas explicitement mentionné."),
    "_2713": mc("_2713", 2.5, "Objectifs très spécifiques : nombre de commandes mensuelles, CA cible, nombre d'abonnés, taux de satisfaction client."),
    "_7682": mc("_7682", 2.5, "Tous les objectifs sont mesurables avec KPI chiffrés et unités de mesure clairement définies."),
    "_5052": mc("_5052", 2.5, "Cibles chiffrées pour chaque objectif. Aucun objectif vague ou sans indicateur quantitatif."),
    "_3498": mc("_3498", 2.0, "Horizons temporels présents (6 mois, 1 an) mais moins granulaires que les meilleurs travaux (pas de phases multiples)."),
    "_7081": mc("_7081", 2.0, "Objectifs réalistes au regard du contexte artisanal. Montée en charge progressive cohérente."),
    "_593":  mc("_593",  2.5, "Objectifs formulés par rapport à une base de départ (0 client, 0 vente) avec cibles de progression clairement établies."),
    "_6346": mc("_6346", 2.5, "Structure OKR utilisée avec Objectives et Key Results distincts, bien formulés."),
    "_8367": mc("_8367", 2.0, "Objectives de qualité (acquisition, croissance, fidélisation) mais moins nombreux que dans les meilleures copies."),
    "_7502": mc("_7502", 2.5, "Key Results chiffrés, mesurables et cohérents avec les Objectives."),
    "_2568": mc("_2568", 1.0, "SMART et OKR partiellement articulés ensemble mais lien explicite entre les deux frameworks pas formalisé."),
    "_4771": mc("_4771", 2.0, "Objectifs couvrent les principales dimensions (commercial, digital, satisfaction) mais hiérarchisation formelle absente."),
    "_6588": mc("_6588", 2.5, "Présentation claire en tableau structuré avec phases, métriques et horizons temporels. Bien organisée."),

    # Section 6 – Stratégie de marque & communication (33.0 pts)
    "_153":  mc("_153",  2.5, "Segmentation réalisée avec profils distincts et justifiés (particuliers, B2B, événementiel)."),
    "_41":   mc("_41",   2.5, "Critères de segmentation multiples (usage, budget, fréquence d'achat, sensibilité à la personnalisation)."),
    "_5323": mc("_5323", 2.0, "Segment prioritaire identifié mais sans scoring formel chiffré. Priorisation basée sur le volume et l'accessibilité."),
    "_2781": mc("_2781", 2.5, "Cohérence entre segmentation et personas : particuliers → acheteur individuel, B2B → entreprises, événementiel → occasions spéciales."),
    "_4386": mc("_4386", 2.0, "Ciblage principal explicite (particuliers cherchant décoration unique) mais critères de priorité non quantifiés."),
    "_1542": mc("_1542", 2.0, "Ciblage secondaire identifié (B2B, événementiel) avec spécificités mentionnées mais moins développé que le ciblage principal."),
    "_3840": mc("_3840", 2.0, "Justification du choix de cible présente mais sans scoring multicritères formel."),
    "_6587": mc("_6587", 2.5, "Positionnement clair : artisanat haut de gamme, personnalisation, esthétique unique vs importations et production de masse."),
    "_3147": mc("_3147", 2.0, "Différenciation présente (unicité artisanale, personnalisation complète) mais non formalisée dans une matrice de positionnement."),
    "_7138": mc("_7138", 2.0, "Identité de marque développée : nom, logo, palette de couleurs, valeurs. Cohérence de l'identité visuelle présente."),
    "_662":  mc("_662",  2.0, "Charte graphique et choix visuels présents mais sans analyse de l'impact sur la perception de la cible."),
    "_4155": mc("_4155", 2.0, "Ton et style de communication définis (élégant, artisanal, chaleureux) mais sans exemples détaillés de mise en application."),
    "_7255": mc("_7255", 2.0, "Canaux de communication identifiés (Instagram, Facebook, bouche-à-oreille, foires) adaptés à la cible."),
    "_8445": mc("_8445", 2.0, "Mix de canaux cohérent avec le positionnement artisanal et la cible. Justification partielle du choix des canaux."),
    "_5149": mc("_5149", 1.0, "Stratégie de contenu mentionnée mais planning éditorial et fréquence de publication peu détaillés."),
    "_3046": mc("_3046", 2.0, "Stratégie globalement cohérente entre segmentation, positionnement et plan de communication."),

    # Section 7 – Tactiques (51.5 pts)
    "_2529": mc("_2529", 2.5, "Tactiques digitales définies : Instagram, Facebook, stories, reels, posts réguliers."),
    "_2198": mc("_2198", 2.5, "Actions de contenu spécifiques : photos produits, vidéos fabrication, avant/après, témoignages clients."),
    "_6529": mc("_6529", 2.5, "SEO et présence en ligne abordés : hashtags, mots-clés visuels, présence sur Google Business."),
    "_3511": mc("_3511", 2.5, "Publicité digitale ciblée (Facebook Ads, Instagram Ads) avec budget et ciblage démographique définis."),
    "_741":  mc("_741",  2.5, "E-mailing et CRM mentionnés pour fidélisation (liste clients, newsletter, offres personnalisées)."),
    "_9818": mc("_9818", 2.5, "Partenariats identifiés : décorateurs d'intérieur, organisateurs d'événements, influenceurs locaux."),
    "_4712": mc("_4712", 2.5, "Relations presse et relations publiques : médias locaux, foires artisanales, expositions."),
    "_8069": mc("_8069", 2.5, "Marketing direct : vente en atelier, marchés artisanaux, démonstrations en direct."),
    "_2955": mc("_2955", 2.5, "Événementiel : ateliers créatifs pour clients, pop-up stores, expositions thématiques."),
    "_2180": mc("_2180", 2.0, "Promotions et offres spéciales définies (réduction première commande, offre fidélité) mais sans détail sur la mécanique promotionnelle."),
    "_5963": mc("_5963", 2.5, "Programme de fidélité mentionné avec avantages pour clients récurrents."),
    "_276":  mc("_276",  2.5, "Tactiques B2B définies : devis personnalisés, visite d'atelier, catalogue B2B."),
    "_4227": mc("_4227", 2.5, "Outils de vente en ligne : site web ou boutique en ligne, Instagram Shopping, paiement mobile."),
    "_1182": mc("_1182", 1.0, "Benchmarks concurrentiels présents de façon limitée. Pas d'analyse comparative détaillée des tactiques concurrentes."),
    "_5884": mc("_5884", 2.0, "Budget alloué par canal mentionné mais sans répartition précise entre canaux et justification des montants."),
    "_9870": mc("_9870", 2.0, "Calendrier éditorial présent mais sans planning hebdomadaire ou mensuel formalisé."),
    "_8031": mc("_8031", 2.0, "KPI par tactique identifiés (taux d'engagement, portée, conversion) mais sans cibles précises par canal."),
    "_4751": mc("_4751", 2.5, "Cohérence entre tactiques et positionnement artisanal haut de gamme."),
    "_2911": mc("_2911", 2.0, "Tactiques de vente offline cohérentes avec le modèle artisanal (foires, atelier, démonstrations)."),
    "_1784": mc("_1784", 2.0, "Tactiques de service client définies (suivi commande, personnalisation, satisfaction garantie)."),
    "_7126": mc("_7126", 2.0, "Tactiques de croissance identifiées (augmentation gamme, nouvelles cibles, expansion zones géographiques)."),
    "_2457": mc("_2457", 2.0, "Plan de lancement présent avec étapes de mise en marché (pré-lancement, lancement, post-lancement)."),
    "_7405": mc("_7405", 2.0, "Ensemble des tactiques bien coordonnées et globalement cohérentes avec la stratégie."),

    # Section 8 – Plan d'actions (30.5 pts)
    "_5981": mc("_5981", 2.5, "Plan d'actions structuré en phases avec étapes claires (pré-lancement, lancement, croissance)."),
    "_4317": mc("_4317", 2.0, "Tâches listées avec responsables mais attribution parfois générique ('moi' ou 'équipe')."),
    "_8182": mc("_8182", 2.5, "Délais définis pour chaque action principale. Chronologie globalement cohérente."),
    "_8061": mc("_8061", 2.5, "Ressources nécessaires identifiées (matières premières, équipements, outils digitaux, budget com)."),
    "_8862": mc("_8862", 2.0, "Budget global estimé avec répartition par poste (production, communication, logistique)."),
    "_6896": mc("_6896", 2.0, "Priorités d'action établies implicitement par ordre d'apparition dans le plan."),
    "_1422": mc("_1422", 1.0, "Dépendances entre actions peu formalisées. Plan relativement linéaire sans visualisation des interdépendances."),
    "_4276": mc("_4276", 2.0, "Indicateurs de succès par action mentionnés mais sans cibles chiffrées systématiques."),
    "_4068": mc("_4068", 2.0, "Plan de contingence partiel : alternatives en cas de retard fournisseur mentionnées."),
    "_7314": mc("_7314", 2.0, "Revue et ajustement du plan prévus à des jalons clés (3 mois, 6 mois)."),
    "_3298": mc("_3298", 1.0, "Matrice RACI ou équivalent absent. Attribution des responsabilités peu formalisée."),
    "_6245": mc("_6245", 1.0, "Processus de validation des livrables non explicité."),
    "_8157": mc("_8157", 2.0, "Plan d'actions aligné sur les objectifs et la stratégie définis en amont."),
    "_7239": mc("_7239", 2.0, "Cohérence entre le plan d'actions et les tactiques définies."),
    "_4583": mc("_4583", 2.0, "Plan suffisamment détaillé pour être opérationnel, avec jalons identifiables."),
    "_5409": mc("_5409", 2.0, "Présentation du plan d'actions claire et structurée."),

    # Section 9 – Contrôle & suivi (35.0 pts)
    "_5358": mc("_5358", 2.5, "Système de suivi défini avec KPI clés identifiés (CA, commandes, satisfaction, abonnés, engagement)."),
    "_3795": mc("_3795", 2.5, "Fréquence de suivi définie (mensuelle, trimestrielle) avec responsable du reporting."),
    "_5882": mc("_5882", 2.5, "Outils de suivi mentionnés (tableaux de bord, Google Analytics, CRM basique, Instagram Insights)."),
    "_7611": mc("_7611", 2.5, "Métriques de performance bien définies et alignées sur les objectifs fixés."),
    "_275":  mc("_275",  2.5, "Process de révision défini avec révisions périodiques et ajustements planifiés."),
    "_4072": mc("_4072", 2.5, "Indicateurs d'alerte identifiés (baisse engagement, CA sous seuil, délais non respectés)."),
    "_826":  mc("_826",  2.5, "Plan de correction prévu en cas d'écart entre réel et objectif."),
    "_356":  mc("_356",  2.5, "Retour client intégré dans le suivi (satisfaction, NPS, commentaires)."),
    "_5213": mc("_5213", 2.0, "Suivi financier présent (CA, marge) mais analyse de rentabilité par produit peu détaillée."),
    "_615":  mc("_615",  2.0, "Analyse de la concurrence dans le suivi mentionnée mais processus formel de veille peu structuré."),
    "_2019": mc("_2019", 2.5, "Dashboard ou tableau de bord défini avec les métriques principales regroupées."),
    "_3537": mc("_3537", 1.0, "Rapport périodique défini mais format et destinataires non précisés."),
    "_3924": mc("_3924", 1.0, "Processus d'escalade en cas de problème peu formalisé."),
    "_3839": mc("_3839", 1.0, "Documentation des leçons apprises peu développée."),
    "_5058": mc("_5058", 0.0, "Audit externe ou évaluation indépendante non mentionné."),
    "_9270": mc("_9270", 2.0, "Suivi de la satisfaction client formalisé (enquêtes post-achat, étoiles, avis)."),
    "_1286": mc("_1286", 2.0, "Métriques digitales bien suivies (taux d'engagement, portée, clics, conversion)."),
    "_8268": mc("_8268", 2.0, "Présentation du système de contrôle claire et bien structurée."),
}

total_1255 = sum(v["points"] for v in evals_1255.values())
write_evaluation(1255, total_1255, evals_1255)


# ============================================================
# STUDENT 1274 — Signature Events (Bob Bodi)
# Agence événementielle premium à Kinshasa
# Score: 264.0/342.5
# ============================================================
evals_1274 = {
    # Section 1 – Pitch Deck (21.5 pts)
    "_9714": mc("_9714", 2.5, "Besoin clairement posé : marché événementiel kinois en croissance, peu d'agences professionnelles et structurées pour les événements premium d'entreprise et privés."),
    "_949":  mc("_949",  2.5, "Signature Events présentée avec précision : agence événementielle premium, organisation d'événements corporate et privés haut de gamme à Kinshasa."),
    "_451":  mc("_451",  2.5, "Problème bien défini : manque d'agences fiables et professionnelles, offres fragmentées, qualité inconstante, manque de rigueur dans l'exécution."),
    "_7001": mc("_7001", 2.0, "Cible identifiée (entreprises, particuliers aisés, institutions) sans segmentation chiffrée ni scoring formel."),
    "_8064": mc("_8064", 2.5, "Besoins bien identifiés : professionnalisme, fiabilité, coordination complète, prestige. Hiérarchisés et contextualisés."),
    "_4805": mc("_4805", 2.5, "Solution claire : agence clé-en-main, coordination totale, partenaires qualifiés, suivi rigoureux. Répond directement aux lacunes du marché."),
    "_7185": mc("_7185", 2.5, "Proposition de valeur différenciante : 'L'excellence événementielle à votre service', combinant rigueur, créativité et service premium."),
    "_7666": mc("_7666", 2.5, "Cohérence exemplaire : besoin de professionnalisme → problème fragmentation du marché → cible premium → solution agence structurée. Fil directeur fort."),
    "_1878": mc("_1878", 2.0, "Pitch deck bien structuré et professionnel, avec hiérarchie visuelle et données. Mise en page soignée mais pourrait être optimisée davantage."),

    # Section 2 – Étude de marché (19.0 pts)
    "_6133": mc("_6133", 2.0, "Marché événementiel décrit avec contexte Kinshasa (croissance économique, urbanisation, expansion classe moyenne) mais données chiffrées partielles."),
    "_1518": mc("_1518", 2.0, "Opportunités identifiées : croissance événementiel corporate, manque d'acteurs structurés, boom immobilier et hôtellerie. Sans croissance annuelle sourcée précisément."),
    "_407":  mc("_407",  2.5, "Risques bien identifiés : instabilité économique, dépendance clients B2B, saisonnalité, risques d'exécution, inflation matériaux."),
    "_9867": mc("_9867", 2.5, "Concurrents identifiés par catégorie avec analyse forces/faiblesses. Parts de marché estimées avec justification."),
    "_2858": mc("_2858", 2.0, "Analyse concurrentielle présente mais comparaison moins structurée que les meilleurs travaux. Opportunités de différenciation bien déduites."),
    "_3678": mc("_3678", 2.0, "Taille de marché estimée avec approche TAM/SAM/SOM partielle. Méthodologie présente mais calculs moins détaillés que les références."),
    "_7629": mc("_7629", 1.0, "Sources citées mais de façon incomplète (sans dates systématiques ni publications précises pour toutes les données)."),
    "_1498": mc("_1498", 2.0, "Synthèse actionnable : positionnement haut de gamme comme axe principal. Recommandations bien déduites de l'analyse."),
    "_2485": mc("_2485", 1.0, "Pas de mention explicite d'enquête primaire. Analyse principalement basée sur données secondaires et observations."),
    "_2602": mc("_2602", 2.0, "Document bien structuré avec sections distinctes. Lisibilité bonne mais mise en forme moins homogène que les meilleures copies."),

    # Section 3 – Personas (24.5 pts)
    "_1059": mc("_1059", 2.0, "Marché cible défini (corporate, particuliers premium, institutions) avec justification qualitative de la priorité."),
    "_91":   mc("_91",   1.0, "Un seul persona nommé (Directeur RH / responsable événements). Manque un second persona distinct pour les particuliers."),
    "_4110": mc("_4110", 2.0, "Persona principal bien développé (poste, secteur, budget, objectifs, frustrations). Biographie présente mais brève."),
    "_8292": mc("_8292", 1.0, "Comportements digitaux peu développés pour le persona. Usage LinkedIn et email mentionné sans approfondissement."),
    "_4829": mc("_4829", 2.0, "Besoins bien identifiés pour le persona principal : fiabilité, rigueur, professionnalisme, budget maitrisé, réputation protégée."),
    "_7467": mc("_7467", 0.0, "Freins à l'achat non explicitement listés par persona. Risques perçus (coût, manque de confiance) globalement abordés mais non structurés."),
    "_7644": mc("_7644", 1.0, "Pain points présents (mauvaises expériences passées, fournisseurs peu fiables) mais non formalisés en 3 points distincts."),
    "_4132": mc("_4132", 2.5, "Persona parfaitement aligné avec le projet : responsable événements → besoin d'agence clé-en-main fiable."),
    "_8952": mc("_8952", 2.0, "Insights clés identifiés : priorité fiabilité, budget décisionnel, critères de choix fournisseur. Pertinents et actionnables."),
    "_5479": mc("_5479", 2.0, "Insights traduits en actions : portfolio de réalisations, témoignages clients, contrats avec clauses de garantie."),
    "_4661": mc("_4661", 1.0, "Justification du persona principal par son importance économique (B2B premium) mais sans score ou critère formel."),
    "_6035": mc("_6035", 1.0, "Priorisation présente (B2B corporate en priorité) mais sans hiérarchie chiffrée entre les segments."),
    "_2469": mc("_2469", 1.0, "Peu de données quantitatives pour justifier les personas. Profils basés sur des observations et expérience terrain."),
    "_6063": mc("_6063", 2.0, "Distinction entre corporate et privé présente mais un seul persona nommé limite la différenciation."),
    "_3640": mc("_3640", 2.0, "Implications marketing déduites (LinkedIn pour B2B, références pour confiance, dossier commercial pour premium)."),
    "_6265": mc("_6265", 2.0, "Présentation du persona structurée avec profil, objectifs, défis, canaux préférés. Format lisible."),

    # Section 4 – Diagnostic (30.0 pts)
    "_1290": mc("_1290", 2.5, "SWOT complet avec les 4 quadrants remplis et éléments spécifiques à l'agence événementielle premium."),
    "_3809": mc("_3809", 2.5, "Forces bien identifiées : réseau de partenaires qualifiés, expertise coordination, relationnel client, flexibilité offre."),
    "_4379": mc("_4379", 2.5, "Faiblesses identifiées : faible notoriété initiale, dépendance clients B2B, coûts fixes, concurrence informelle."),
    "_7933": mc("_7933", 2.5, "Opportunités précises : croissance événementiel, manque d'acteurs structurés, expansion hôtellerie, diaspora investissant."),
    "_2400": mc("_2400", 2.5, "Menaces concrètes : instabilité politique, inflation, saisonnalité, risques réputationnels."),
    "_6000": mc("_6000", 2.0, "Analyse externe présente mais PESTEL formellement structuré en 6 dimensions avec moins de détail que les meilleurs travaux."),
    "_8024": mc("_8024", 2.0, "Facteurs PESTEL pertinents mais lien explicite avec les implications opérationnelles partiellement développé."),
    "_8099": mc("_8099", 2.0, "Lien entre diagnostic et stratégie présent mais formellement développé de façon partielle."),
    "_1924": mc("_1924", 2.0, "Enjeux prioritaires identifiés (construire notoriété, certifier partenaires, fidéliser B2B) sans formalisation MOST WIN."),
    "_4684": mc("_4684", 2.0, "Conclusion du diagnostic bien formulée. Synthèse stratégique présente mais pourrait être plus développée."),
    "_9901": mc("_9901", 1.0, "Section MOST WIN non formalisée explicitement."),
    "_8241": mc("_8241", 1.0, "Priorités stratégiques présentes implicitement mais non hiérarchisées formellement comme MOST WIN."),
    "_707":  mc("_707",  1.0, "Données chiffrées limitées pour justifier les éléments du diagnostic. Analyse principalement qualitative."),
    "_248":  mc("_248",  2.5, "Risques bien analysés avec plans d'atténuation pour les principaux risques identifiés."),
    "_7172": mc("_7172", 2.0, "Recommandations stratégiques bien déduites du diagnostic (certification partenaires, dossier référence, B2B prioritaire)."),
    "_2509": mc("_2509", 2.0, "Diagnostic bien présenté et structuré, lisible et cohérent."),

    # Section 5 – Objectifs (24.5 pts)
    "_1307": mc("_1307", 2.0, "Objectifs formulés avec plusieurs éléments SMART présents mais formulation SMART non explicitement structurée."),
    "_2713": mc("_2713", 2.5, "Objectifs spécifiques : nombre d'événements mensuels, CA cible, nombre de clients B2B signés, satisfaction client."),
    "_7682": mc("_7682", 2.5, "Objectifs mesurables avec KPI chiffrés (events/mois, CA, NPS, taux de renouvellement contrats)."),
    "_5052": mc("_5052", 2.5, "Cibles chiffrées présentes pour chaque objectif. Structure quantitative solide."),
    "_3498": mc("_3498", 2.5, "Horizons temporels définis (3 mois, 6 mois, 1 an, 2 ans) avec jalons intermédiaires."),
    "_7081": mc("_7081", 2.0, "Objectifs réalistes au regard du positionnement premium et du marché Kinshasa."),
    "_593":  mc("_593",  1.0, "Base de départ peu explicite. Absence de baseline formelle (0 client, 0 événement au démarrage) non mentionnée."),
    "_6346": mc("_6346", 2.0, "OKR utilisés avec Objectives et Key Results mais nombre d'Objectives inférieur aux meilleurs travaux (1 principal OKR)."),
    "_8367": mc("_8367", 1.0, "Un seul objectif principal formalisé. Manque d'objectifs distincts pour les dimensions commercial, marque, satisfaction."),
    "_7502": mc("_7502", 2.5, "Key Results bien chiffrés et mesurables, alignés sur l'objectif principal."),
    "_2568": mc("_2568", 1.0, "Articulation SMART / OKR peu formalisée."),
    "_4771": mc("_4771", 1.0, "Hiérarchie entre objectifs peu développée. Priorisation formelle absente."),
    "_6588": mc("_6588", 2.0, "Présentation des objectifs structurée. Tableau avec métriques lisible."),

    # Section 6 – Stratégie (33.0 pts)
    "_153":  mc("_153",  2.5, "Segmentation réalisée avec profils distincts (corporate, particuliers premium, institutions)."),
    "_41":   mc("_41",   2.5, "Critères de segmentation multiples (budget, fréquence, type d'événement, exigences qualité)."),
    "_5323": mc("_5323", 2.0, "Segment prioritaire identifié (corporate premium) mais sans scoring formel chiffré."),
    "_2781": mc("_2781", 2.5, "Cohérence entre segmentation et persona principal (corporate/DRH)."),
    "_4386": mc("_4386", 2.0, "Ciblage principal explicite (entreprises premium) avec justification par le CA potentiel."),
    "_1542": mc("_1542", 2.0, "Ciblage secondaire identifié (particuliers, institutions) avec positionnement adapté."),
    "_3840": mc("_3840", 2.0, "Justification du ciblage présente mais sans critères quantifiés."),
    "_6587": mc("_6587", 2.0, "Positionnement clair : excellence, fiabilité, haut de gamme, vs concurrents moins structurés."),
    "_3147": mc("_3147", 2.0, "Différenciation affirmée (certification partenaires, suivi rigoureux, portfolio de références) mais non formalisée dans une matrice."),
    "_7138": mc("_7138", 2.5, "Identité de marque développée avec nom, logo, palette, valeurs de marque (excellence, fiabilité, créativité)."),
    "_662":  mc("_662",  2.0, "Charte graphique présente avec cohérence visuelle. Moins détaillée que les meilleures copies."),
    "_4155": mc("_4155", 2.0, "Ton et voix de marque définis (professionnel, chaleureux, premium) avec quelques exemples."),
    "_7255": mc("_7255", 2.0, "Canaux de communication identifiés (LinkedIn, Instagram, site web, bouche-à-oreille) adaptés au B2B premium."),
    "_8445": mc("_8445", 2.0, "Mix de canaux cohérent avec positionnement premium et cible B2B."),
    "_5149": mc("_5149", 1.0, "Stratégie de contenu esquissée mais planning éditorial et détails de production de contenu peu développés."),
    "_3046": mc("_3046", 2.0, "Stratégie de communication globalement cohérente avec le positionnement premium."),

    # Section 7 – Tactiques (50.0 pts)
    "_2529": mc("_2529", 2.5, "Tactiques digitales définies : LinkedIn Ads, Instagram, site vitrine, SEO local."),
    "_2198": mc("_2198", 2.5, "Actions de contenu spécifiques : études de cas, photos de réalisations, témoignages clients, behind-the-scenes."),
    "_6529": mc("_6529", 2.5, "SEO et visibilité en ligne : optimisation Google Business, mots-clés événementiel Kinshasa, avis Google."),
    "_3511": mc("_3511", 2.5, "Publicité ciblée LinkedIn pour B2B. Ciblage par secteur et poste défini."),
    "_741":  mc("_741",  2.5, "E-mailing B2B : campagnes de prospection, newsletters clients, séquences de nurturing."),
    "_9818": mc("_9818", 2.5, "Partenariats stratégiques : hôtels, traiteurs, photographes, DJ, sécurité. Réseau de prestataires certifiés."),
    "_4712": mc("_4712", 2.5, "Relations presse et RP : communiqués sur événements réussis, présence dans médias business locaux."),
    "_8069": mc("_8069", 2.5, "Marketing direct : démarchage B2B ciblé, appels, rendez-vous commerciaux, propositions personnalisées."),
    "_2955": mc("_2955", 2.5, "Événementiel propre : organisation d'un événement showcase pour démontrer savoir-faire."),
    "_2180": mc("_2180", 2.0, "Promotions et offres : devis gratuit, package découverte, remise premier événement. Sans détail sur mécanique."),
    "_5963": mc("_5963", 2.5, "Programme de fidélité B2B : tarifs préférentiels clients récurrents, gestionnaire dédié."),
    "_276":  mc("_276",  1.0, "Tactiques B2B définis mais pas tous détaillés avec actions opérationnelles précises."),
    "_4227": mc("_4227", 2.0, "Site web avec formulaire de contact et portfolio. Boutique en ligne non applicable pour ce modèle."),
    "_1182": mc("_1182", 0.0, "Benchmarks concurrentiels tactiques absents. Pas de comparaison avec tactiques de la concurrence."),
    "_5884": mc("_5884", 2.0, "Budget par canal mentionné mais sans répartition précise et justifiée."),
    "_9870": mc("_9870", 2.5, "Calendrier d'actions défini avec planning sur 3 mois pour la phase de lancement."),
    "_8031": mc("_8031", 2.0, "KPI par tactique mentionnés (taux de conversion B2B, engagement, taux de satisfaction)."),
    "_4751": mc("_4751", 2.5, "Cohérence entre les tactiques et le positionnement premium."),
    "_2911": mc("_2911", 2.5, "Tactiques offline bien développées (démarchage B2B, événement showcase, foires)."),
    "_1784": mc("_1784", 2.5, "Tactiques service client détaillées : gestionnaire de projet dédié, reporting post-événement, garantie satisfaction."),
    "_7126": mc("_7126", 2.0, "Tactiques de croissance définies : expansion géographique, diversification événements, montée en gamme."),
    "_2457": mc("_2457", 2.0, "Plan de lancement tactique présent avec actions séquencées."),
    "_7405": mc("_7405", 2.0, "Ensemble tactique cohérent et bien coordonné avec la stratégie globale."),

    # Section 8 – Plan d'actions (30.5 pts)
    "_5981": mc("_5981", 2.5, "Plan d'actions en phases avec étapes clairement définies (phase préparation, lancement, développement)."),
    "_4317": mc("_4317", 1.0, "Tâches listées mais responsables souvent 'moi' seul sans équipe. Attribution trop générique."),
    "_8182": mc("_8182", 2.5, "Délais définis pour chaque action. Chronologie cohérente avec le plan de lancement."),
    "_8061": mc("_8061", 2.5, "Ressources identifiées : matérielles, humaines, financières et relationnelles (réseau partenaires)."),
    "_8862": mc("_8862", 2.5, "Budget structuré avec investissement initial et fonctionnement mensuel détaillés."),
    "_6896": mc("_6896", 2.5, "Priorités d'actions établies avec actions critiques de lancement identifiées."),
    "_1422": mc("_1422", 0.0, "Dépendances entre tâches non formalisées. Pas de Gantt ou visualisation de chemin critique."),
    "_4276": mc("_4276", 2.0, "Indicateurs de succès par phase mentionnés. Métriques de validation présentes."),
    "_4068": mc("_4068", 2.0, "Plan de contingence partiel : alternatives pour quelques risques principaux."),
    "_7314": mc("_7314", 2.0, "Points de revue planifiés à des jalons clés du plan."),
    "_3298": mc("_3298", 2.0, "Attribution des responsabilités présente mais centralisée sur une personne."),
    "_6245": mc("_6245", 1.0, "Processus de validation peu formalisé."),
    "_8157": mc("_8157", 2.0, "Plan d'actions aligné sur les objectifs et la stratégie définis."),
    "_7239": mc("_7239", 2.0, "Cohérence entre plan d'actions et tactiques opérationnelles."),
    "_4583": mc("_4583", 2.0, "Plan suffisamment opérationnel avec jalons identifiables."),
    "_5409": mc("_5409", 2.0, "Présentation du plan claire et structurée."),

    # Section 9 – Contrôle & suivi (31.0 pts)
    "_5358": mc("_5358", 2.5, "Système de suivi défini avec KPI clés : CA mensuel, événements réalisés, satisfaction client, taux de renouvellement."),
    "_3795": mc("_3795", 2.5, "Fréquence de suivi définie avec reporting mensuel et révision trimestrielle."),
    "_5882": mc("_5882", 2.0, "Outils de suivi mentionnés (Excel, CRM simple, Google Forms pour satisfaction) mais moins technologiques que les meilleurs travaux."),
    "_7611": mc("_7611", 2.0, "Métriques définies et alignées sur les objectifs mais sans tableau de bord formalisé."),
    "_275":  mc("_275",  2.0, "Process de révision présent avec révisions périodiques planifiées."),
    "_4072": mc("_4072", 2.5, "Indicateurs d'alerte identifiés (satisfaction < seuil, CA sous target, annulations)."),
    "_826":  mc("_826",  2.5, "Plan de correction défini pour les principaux écarts."),
    "_356":  mc("_356",  1.0, "Retour client mentionné (enquête post-événement) mais processus formel peu développé."),
    "_5213": mc("_5213", 2.5, "Suivi financier détaillé avec analyse CA, marges, coûts par événement."),
    "_615":  mc("_615",  1.0, "Veille concurrentielle mentionnée mais processus formel peu structuré."),
    "_2019": mc("_2019", 2.5, "Dashboard défini avec métriques principales regroupées."),
    "_3537": mc("_3537", 1.0, "Rapport périodique peu formalisé en termes de structure et destinataires."),
    "_3924": mc("_3924", 1.0, "Processus d'escalade peu développé."),
    "_3839": mc("_3839", 0.0, "Documentation des leçons apprises absente."),
    "_5058": mc("_5058", 0.0, "Audit externe non mentionné."),
    "_9270": mc("_9270", 2.0, "Suivi satisfaction client formalisé (questionnaire post-événement, score NPS)."),
    "_1286": mc("_1286", 2.0, "Métriques digitales suivies (engagement, portée, leads générés)."),
    "_8268": mc("_8268", 2.0, "Présentation du système de contrôle bien structurée."),
}

total_1274 = sum(v["points"] for v in evals_1274.values())
write_evaluation(1274, total_1274, evals_1274)


# ============================================================
# STUDENT 1401 — ReBelle
# Marketplace robes de cérémonie seconde main
# Score: 320.5/342.5
# ============================================================
evals_1401 = {
    # Section 1 – Pitch Deck (22.5 pts — all 2.5)
    "_9714": mc("_9714", 2.5, "Besoin parfaitement articulé : 60% des robes de cérémonie portées une seule fois, gaspillage énorme, marché de la revente peu structuré en RDC. Données chiffrées et contexte convaincants."),
    "_949":  mc("_949",  2.5, "ReBelle décrite avec précision : marketplace C2C de robes de cérémonie seconde main, modèle commission sur vente, double cible vendeurs/acheteurs."),
    "_451":  mc("_451",  2.5, "Problème double et précis : gaspillage ressources (côté vendeur) + accessibilité économique robes premium (côté acheteur). Bien documenté avec chiffres."),
    "_7001": mc("_7001", 2.5, "Double cible définie : vendeurs (femmes 25-40 ans, robes inutilisées) et acheteurs (femmes 20-35 ans, budget limité). Personas distincts avec profils démographiques."),
    "_8064": mc("_8064", 2.5, "Besoins des deux côtés de la marketplace bien identifiés et chiffrés. Double value proposition articulée."),
    "_4805": mc("_4805", 2.5, "Solution claire et complète : plateforme marketplace avec système de vérification, photos standardisées, paiement sécurisé, livraison intégrée."),
    "_7185": mc("_7185", 2.5, "Proposition de valeur forte pour les deux côtés : 'Donnez une seconde vie à votre robe' (vendeurs) et 'La robe de vos rêves à prix accessible' (acheteurs)."),
    "_7666": mc("_7666", 2.5, "Cohérence parfaite : économie circulaire × accessibilité × marketplace digital. Tous les éléments s'articulent avec une logique irréprochable."),
    "_1878": mc("_1878", 2.5, "Pitch deck de très haute qualité : mise en page professionnelle, chiffres clés en évidence, structure narrative claire, visuels impactants."),

    # Section 2 – Étude de marché (21.0 pts)
    "_6133": mc("_6133", 2.5, "Marché bien délimité : seconde main mode en Afrique subsaharienne, données croissance marché mondial de la revente (+24%/an), contexte RDC avec données précises."),
    "_1518": mc("_1518", 2.5, "Opportunités très bien développées : boom économie circulaire mondiale, croissance classe moyenne africaine, pénétration mobile, manque d'acteur structuré en RDC."),
    "_407":  mc("_407",  2.5, "Risques clairement identifiés : confiance dans la qualité (seconde main), habitudes d'achat physique, coûts logistiques, fragmentation concurrentielle."),
    "_9867": mc("_9867", 2.0, "Concurrents identifiés (vendeurs informels Facebook, friperies physiques, importations) mais sans parts de marché chiffrées précises."),
    "_2858": mc("_2858", 2.5, "Analyse concurrentielle structurée avec forces/faiblesses de chaque catégorie et avantage compétitif ReBelle bien articulé."),
    "_3678": mc("_3678", 2.5, "TAM/SAM/SOM bien construit avec hypothèses documentées et calculs cohérents pour le marché de la cérémonie en RDC."),
    "_7629": mc("_7629", 1.0, "Sources citées mais avec inégalité de documentation (certaines données sans source précise)."),
    "_1498": mc("_1498", 2.0, "Synthèse actionnable présente. Recommandation de se positionner sur la vérification qualité et la sécurité comme différenciateur."),
    "_2485": mc("_2485", 1.0, "Étude primaire non explicitement documentée. Analyse principalement secondaire avec quelques témoignages."),
    "_2602": mc("_2602", 2.5, "Document extrêmement bien structuré avec tableaux, graphiques, sections numérotées et hiérarchie visuelle exemplaire."),

    # Section 3 – Personas (36.5 pts)
    "_1059": mc("_1059", 2.5, "Double marché bien identifié : côté vendeur (femmes ayant des robes inutilisées) et côté acheteur (femmes cherchant robe abordable). Segmentation multicritères."),
    "_91":   mc("_91",   2.5, "Deux personas complets et distincts : Clarisse (vendeuse, 32 ans) et Aisha (acheteuse, 24 ans). Profils complémentaires et bien contrastés."),
    "_4110": mc("_4110", 2.0, "Biographies présentes mais pourraient être plus développées sur le contexte quotidien et la vie professionnelle."),
    "_8292": mc("_8292", 2.0, "Comportements digitaux mentionnés (Instagram, WhatsApp, mobile-first) mais non développés de façon exhaustive pour chaque persona."),
    "_4829": mc("_4829", 2.5, "Besoins des deux personas parfaitement identifiés : Clarisse veut récupérer de la valeur, Aisha veut accessibilité et qualité. Insights très précis."),
    "_7467": mc("_7467", 2.0, "Freins identifiés : doutes sur la qualité (Aisha), peur de la sécurité du paiement (Aisha), temps nécessaire pour publier (Clarisse). Bien structurés."),
    "_7644": mc("_7644", 2.0, "Pain points présents pour chaque persona mais pourraient être hiérarchisés plus explicitement (top 3 douleurs)."),
    "_4132": mc("_4132", 2.5, "Personas parfaitement alignés avec le modèle marketplace : deux côtés bien représentés, insights actionnables."),
    "_8952": mc("_8952", 2.5, "Insights consommateurs très forts : 60% robes portées une fois, prix moyen robe cérémonie 150-300$, budget acheteur 50-80$. Chiffrés et percutants."),
    "_5479": mc("_5479", 2.5, "Insights traduits en fonctionnalités marketplace : vérification qualité (confiance), photos standardisées (qualité visuelle), paiement sécurisé (sécurité), livraison (accessibilité)."),
    "_4661": mc("_4661", 2.0, "Justification du choix des personas présente mais sans critères de priorisation formels chiffrés."),
    "_6035": mc("_6035", 2.5, "Priorisation claire : acheteur = cible principale de l'acquisition (trafic), vendeur = côté offre nécessaire. Logique marketplace bien comprise."),
    "_2469": mc("_2469", 2.0, "Données quantitatives pour appuyer les personas (chiffres marché, prix moyens) mais certaines sans source précise."),
    "_6063": mc("_6063", 2.5, "Personas très distincts : vendeur vs acheteur, niveaux de revenus différents, motivations opposées mais complémentaires."),
    "_3640": mc("_3640", 2.5, "Implications marketing déduites : acquisition vendeurs via Instagram stories/témoignages, acquisition acheteurs via influenceurs et contenu aspirationnel."),
    "_6265": mc("_6265", 2.5, "Fiches personas très bien présentées : photo fictive, citation, profil complet, motivations, frustrations, canaux préférés."),

    # Section 4 – Diagnostic (36.0 pts)
    "_1290": mc("_1290", 2.5, "SWOT complet, bien rempli et spécifique au modèle marketplace seconde main."),
    "_3809": mc("_3809", 2.5, "Forces bien identifiées : premier mover avantage, double side network effect, modèle économie circulaire aligné tendances mondiales."),
    "_4379": mc("_4379", 2.5, "Faiblesses clairement articulées : chicken-and-egg problem marketplace, confiance initiale à construire, coûts logistiques."),
    "_7933": mc("_7933", 2.5, "Opportunités très précises et chiffrées : croissance seconde main, urbanisation, boom digital, manque de concurrent structuré."),
    "_2400": mc("_2400", 2.5, "Menaces concrètes : copies faciles du modèle, vendeurs directs (bypass), résistance culturelle achat seconde main, inflation logistique."),
    "_6000": mc("_6000", 2.5, "PESTEL complet avec 6 dimensions remplies, données chiffrées pour chaque dimension, lien avec le projet explicite."),
    "_8024": mc("_8024", 2.5, "Chaque facteur PESTEL directement lié à une implication opérationnelle pour ReBelle. Analyse très bien conduite."),
    "_8099": mc("_8099", 2.0, "Lien entre diagnostic et stratégie bien articulé mais pourrait être encore plus explicitement formalisé."),
    "_1924": mc("_1924", 2.5, "Enjeux prioritaires bien identifiés : construire la confiance, résoudre le chicken-and-egg, assurer la qualité."),
    "_4684": mc("_4684", 2.0, "Conclusion du diagnostic bien formulée mais synthèse finale un peu concise."),
    "_9901": mc("_9901", 2.0, "Section MOST WIN présente mais formellement incomplète."),
    "_8241": mc("_8241", 2.0, "Priorités stratégiques identifiées (qualité, confiance, liquidité marché) mais hiérarchisation MOST WIN non formalisée."),
    "_707":  mc("_707",  1.0, "Certaines données du diagnostic sans source précise. Justification chiffrée incomplète."),
    "_248":  mc("_248",  2.5, "Risques analysés avec plans d'atténuation détaillés (partenariats nettoyage, politique retour, assurance qualité)."),
    "_7172": mc("_7172", 2.5, "Recommandations stratégiques très bien déduites du diagnostic et alignées sur les forces identifiées."),
    "_2509": mc("_2509", 2.5, "Diagnostic extrêmement bien présenté avec tableaux, matrices et mise en page professionnelle."),

    # Section 5 – Objectifs (31.5 pts)
    "_1307": mc("_1307", 2.5, "Objectifs SMART parfaitement formulés : Spécifiques (marketplace robes), Mesurables (KPI chiffrés), Atteignables, Réalistes, Temporels (phases définies)."),
    "_2713": mc("_2713", 2.5, "Objectifs très spécifiques : nombre de vendeurs actifs, nombre de transactions, GMV, taux de satisfaction, taux de conversion."),
    "_7682": mc("_7682", 2.5, "Tous les objectifs mesurables avec métriques précises et unités claires."),
    "_5052": mc("_5052", 2.5, "Cibles chiffrées exhaustives : 50 vendeurs M3, 200 vendeurs M12, 500 transactions M12, GMV 25000$ M12, satisfaction 90%."),
    "_3498": mc("_3498", 2.5, "Horizons temporels très détaillés : M1, M3, M6, M12 avec jalons intermédiaires et métriques par phase."),
    "_7081": mc("_7081", 2.0, "Objectifs réalistes mais certaines hypothèses de croissance ambitieuses (croissance x4 vendeurs entre M3 et M12)."),
    "_593":  mc("_593",  2.5, "Baseline clairement établie (0 vendeur, 0 transaction) avec trajectoire de croissance bien documentée."),
    "_6346": mc("_6346", 2.5, "OKR excellents : 4 Objectives distincts (Liquidité marché, Confiance utilisateurs, Croissance GMV, Notoriété) avec Key Results précis."),
    "_8367": mc("_8367", 2.5, "4 Objectives de qualité couvrant les dimensions essentielles d'un marketplace (offre, demande, qualité, croissance)."),
    "_7502": mc("_7502", 2.5, "Key Results très bien chiffrés, ambitieux mais ancrés dans des hypothèses documentées."),
    "_2568": mc("_2568", 2.0, "SMART et OKR bien articulés mais l'alignement explicite entre les deux frameworks pourrait être encore plus formalisé."),
    "_4771": mc("_4771", 2.5, "Hiérarchie claire entre les 4 Objectives. Liquidité marché = priorité absolue (condition nécessaire), puis confiance, GMV, notoriété."),
    "_6588": mc("_6588", 2.5, "Présentation des objectifs exemplaire : tableau récapitulatif, roadmap visuelle, métriques par phase."),

    # Section 6 – Stratégie (39.0 pts)
    "_153":  mc("_153",  2.5, "Segmentation double (vendeurs / acheteurs) avec sous-segmentation fine par âge, revenu, comportement d'achat."),
    "_41":   mc("_41",   2.5, "Critères de segmentation nombreux et pertinents : âge, revenu, fréquence cérémonie, sensibilité prix, comportement digital."),
    "_5323": mc("_5323", 2.5, "Priorisation formelle : acheteurs = priorité acquisition (trafic), vendeurs = priorité offre (liquidité), avec scoring."),
    "_2781": mc("_2781", 2.5, "Cohérence parfaite entre segmentation et personas Clarisse / Aisha. Personas représentent exactement les segments prioritaires."),
    "_4386": mc("_4386", 2.5, "Ciblage principal très précis : femmes 20-30 ans cherchant robe de cérémonie abordable, digital natives, Kinshasa."),
    "_1542": mc("_1542", 2.5, "Ciblage secondaire bien défini : vendeuses 28-40 ans ayant des robes inutilisées, motivées par récupération de valeur."),
    "_3840": mc("_3840", 2.5, "Justification des cibles avec données quantifiées et analyse de la valeur économique de chaque segment."),
    "_6587": mc("_6587", 2.5, "Positionnement fort et différenciant : seule marketplace C2C formelle pour robes de cérémonie, avec garantie qualité et sécurité."),
    "_3147": mc("_3147", 2.5, "Différenciation très développée : vérification qualité (trust), photos standardisées (confiance visuelle), paiement sécurisé (sécurité financière)."),
    "_7138": mc("_7138", 2.5, "Identité de marque complète et cohérente : nom fort (ReBelle = rébellion + belle), logo, palette, tone of voice définis."),
    "_662":  mc("_662",  2.5, "Charte graphique détaillée avec usage des couleurs, typographie, exemples visuels et guidelines d'application."),
    "_4155": mc("_4155", 2.5, "Ton et voix de marque très développés : empowering, féminin, moderne, avec exemples de copy pour chaque canal."),
    "_7255": mc("_7255", 2.5, "Canaux parfaitement sélectionnés : Instagram (visuels), WhatsApp (conversationnel), TikTok (viral), email (conversion)."),
    "_8445": mc("_8445", 2.5, "Mix de canaux justifié par les comportements digitaux des personas et les objectifs de la marketplace."),
    "_5149": mc("_5149", 1.0, "Stratégie de contenu bien esquissée mais certains détails de production (fréquence exacte par canal, format) pourraient être plus précis."),
    "_3046": mc("_3046", 2.5, "Stratégie globale exemplaire en termes de cohérence, pertinence et qualité d'exécution."),

    # Section 7 – Tactiques (55.0 pts — all 2.5 except _1182=0.0)
    "_2529": mc("_2529", 2.5, "Tactiques social media très détaillées : Instagram (feed + stories + reels), TikTok (viral), WhatsApp Business (conversationnel)."),
    "_2198": mc("_2198", 2.5, "Contenu détaillé par format : photos avant/après, vidéos de transformation, témoignages vendeurs, lookbooks."),
    "_6529": mc("_6529", 2.5, "SEO et visibilité : optimisation ASO (App Store), SEO web, Google Business, contenu éditorial blog mode."),
    "_3511": mc("_3511", 2.5, "Publicité payante : Facebook/Instagram Ads avec ciblage précis, budget défini, A/B testing."),
    "_741":  mc("_741",  2.5, "CRM et automation : séquences email onboarding vendeurs, relances acheteurs abandons panier, newsletter."),
    "_9818": mc("_9818", 2.5, "Partenariats : influenceurs mode RDC, salons de mariés, photographes, makeup artists. Programme ambassadeurs défini."),
    "_4712": mc("_4712", 2.5, "RP et presse : lancement presse, partnerships médias féminins, témoignages utilisatrices, communiqués innovants."),
    "_8069": mc("_8069", 2.5, "Marketing terrain : pop-up stores, salons, marchés, démonstrations dans salons de mariage."),
    "_2955": mc("_2955", 2.5, "Événementiels : événements de lancement, soirées de vente live, collaborations stylistes."),
    "_2180": mc("_2180", 2.5, "Mécanique promotionnelle détaillée : 0% commission premiers vendeurs, chèque réduction première acheteuse, parrainage."),
    "_5963": mc("_5963", 2.5, "Programme de fidélité complet : points ReBelle, statuts VIP, avantages exclusifs, communauté privée."),
    "_276":  mc("_276",  2.5, "Tactiques B2B : partenariats robes de mariée, robe de cortège, boutiques physiques en consignment."),
    "_4227": mc("_4227", 2.5, "Plateforme marketplace complète : web + app mobile, paiement mobile money, livraison intégrée."),
    "_1182": mc("_1182", 0.0, "Benchmarks concurrentiels tactiques non développés de façon systématique. Absence d'analyse comparative des tactiques des concurrents."),
    "_5884": mc("_5884", 2.5, "Budget détaillé par canal avec justification des montants et ROI attendu pour chaque canal."),
    "_9870": mc("_9870", 2.5, "Calendrier éditorial très détaillé : planning hebdomadaire par canal, thèmes mensuels, jalons de campagnes."),
    "_8031": mc("_8031", 2.5, "KPI par tactique avec cibles précises : taux engagement >5%, coût acquisition <5$, taux conversion 3%."),
    "_4751": mc("_4751", 2.5, "Cohérence exemplaire entre tactiques, stratégie et positionnement marketplace."),
    "_2911": mc("_2911", 2.5, "Tactiques offline très développées : salons, pop-up, terrain. Complémentarité online/offline excellente."),
    "_1784": mc("_1784", 2.5, "Service client détaillé : chat in-app, support WhatsApp, politique retour, mécanisme de résolution des litiges."),
    "_7126": mc("_7126", 2.5, "Tactiques de croissance : expansion géographique planifiée (Lubumbashi), nouvelles catégories (accessoires), B2B."),
    "_2457": mc("_2457", 2.5, "Plan de lancement très détaillé avec pré-lancement (recrutement vendeurs), lancement (campagne paid), post-lancement (optimisation)."),
    "_7405": mc("_7405", 2.5, "Ensemble tactique de très haute qualité. Cohérence, détail et opérationnalité excellents."),

    # Section 8 – Plan d'actions (39.0 pts)
    "_5981": mc("_5981", 2.5, "Plan d'actions en 3 phases très détaillées avec étapes opérationnelles précises."),
    "_4317": mc("_4317", 2.5, "Tâches avec responsables nommés : équipe tech, équipe marketing, community manager, responsable partenariats."),
    "_8182": mc("_8182", 2.5, "Délais précis pour chaque action. Chronologie réaliste avec chemin critique identifié."),
    "_8061": mc("_8061", 2.5, "Ressources exhaustives : équipe (7 rôles), tech (app+web), budget com, partenariats, matériaux photo."),
    "_8862": mc("_8862", 2.5, "Budget détaillé avec investissement initial et fonctionnement mensuel. Hypothèses documentées."),
    "_6896": mc("_6896", 2.5, "Priorités d'action clairement établies avec matrice impact/effort pour hiérarchiser."),
    "_1422": mc("_1422", 2.5, "Dépendances formalisées entre tâches. Gantt chart présent avec chemin critique identifié."),
    "_4276": mc("_4276", 2.5, "Indicateurs de succès par phase très précis et alignés sur les OKR."),
    "_4068": mc("_4068", 2.0, "Plan de contingence présent mais quelques scénarios de risque pourraient être plus développés."),
    "_7314": mc("_7314", 2.5, "Points de revue hebdomadaires (lancement) puis mensuels. Processus de décision clair."),
    "_3298": mc("_3298", 2.0, "Attribution des responsabilités bien faite mais sans matrice RACI formelle."),
    "_6245": mc("_6245", 2.5, "Processus de validation des livrables défini pour chaque phase."),
    "_8157": mc("_8157", 2.5, "Plan d'actions parfaitement aligné sur les objectifs et la stratégie."),
    "_7239": mc("_7239", 2.5, "Cohérence complète entre plan d'actions et tactiques opérationnelles."),
    "_4583": mc("_4583", 2.5, "Plan très opérationnel, utilisable directement comme feuille de route."),
    "_5409": mc("_5409", 2.5, "Présentation du plan exemplaire avec tableaux, Gantt, récapitulatifs."),

    # Section 9 – Contrôle & suivi (40.0 pts)
    "_5358": mc("_5358", 2.5, "Système de suivi complet avec KPI dashboard défini : GMV, DAU, taux de conversion, satisfaction, NPS."),
    "_3795": mc("_3795", 2.5, "Fréquence de suivi très détaillée : daily (métriques app), weekly (performance cam), monthly (KPI business)."),
    "_5882": mc("_5882", 2.5, "Outils modernes définis : Mixpanel analytics, GA4 custom events, Looker Studio dashboard, Hubspot CRM."),
    "_7611": mc("_7611", 2.5, "Métriques très complètes couvrant toutes les dimensions du marketplace (offre, demande, qualité, croissance)."),
    "_275":  mc("_275",  1.0, "Process de révision défini mais fréquence de revue stratégique (trimestrielle) moins développée que les opérationnelles."),
    "_4072": mc("_4072", 2.5, "Indicateurs d'alerte bien définis avec seuils chiffrés déclenchant des actions correctives."),
    "_826":  mc("_826",  2.5, "Plans correctifs détaillés pour les principaux écarts possibles."),
    "_356":  mc("_356",  2.0, "Retour client bien intégré (NPS mensuel, enquêtes satisfaction, analyse avis) mais moins développé que certains autres aspects."),
    "_5213": mc("_5213", 2.5, "Suivi financier très détaillé : GMV, revenus (commission), coûts par transaction, LTV, CAC."),
    "_615":  mc("_615",  2.0, "Veille concurrentielle mentionnée mais processus formel de suivi concurrentiel moins développé."),
    "_2019": mc("_2019", 2.5, "Dashboard défini avec toutes les métriques clés, visualisations et alertes automatiques."),
    "_3537": mc("_3537", 2.5, "Rapports périodiques formalisés : format, fréquence, destinataires définis pour chaque niveau."),
    "_3924": mc("_3924", 2.0, "Processus d'escalade présent mais pourraient être plus détaillé en termes de niveaux."),
    "_3839": mc("_3839", 2.0, "Documentation des rétrospectives prévue mais processus de capitalisation des apprentissages peu formalisé."),
    "_5058": mc("_5058", 1.0, "Évaluation par utilisateurs externe planifiée mais pas d'audit formel externe."),
    "_9270": mc("_9270", 2.5, "Suivi satisfaction très développé : NPS, CSAT, enquêtes post-transaction, analyse qualitative des avis."),
    "_1286": mc("_1286", 2.5, "Métriques digitales très complètes avec GA4 custom events pour le parcours marketplace spécifique."),
    "_8268": mc("_8268", 2.5, "Présentation du système de contrôle exemplaire avec visualisations et tableaux de bord illustrés."),
}

total_1401 = sum(v["points"] for v in evals_1401.values())
write_evaluation(1401, total_1401, evals_1401)


# ============================================================
# STUDENT 1405 — Elavision (Yanick Kavuya)
# Agence marketing digital — seulement 2 milestones
# Score: 14.0/342.5
# ============================================================
ABSENT = "Milestone absent du dossier soumis. Critère non évaluable."

evals_1405 = {
    # Section 1 – Pitch Deck (8.0 pts — partiel)
    "_9714": mc("_9714", 1.0, "Besoin partiellement identifié : développer la présence digitale des entreprises. Contexte peu développé, pas de données de marché."),
    "_949":  mc("_949",  2.0, "Elavision décrite comme agence de marketing digital à Kinshasa, services identifiés (CM, contenu, stratégie). Description fonctionnelle mais sans positionnement différenciant fort."),
    "_451":  mc("_451",  0.0, "Problème client non explicitement formulé. Pas d'articulation du problème douloureux résolu par l'agence."),
    "_7001": mc("_7001", 0.0, "Cible non définie formellement. Pas de segmentation ni de profil client cible."),
    "_8064": mc("_8064", 1.0, "Besoin général identifié (présence digitale) mais sans identification précise des besoins de la cible ni hiérarchisation."),
    "_4805": mc("_4805", 1.0, "Services listés (CM, création contenu, stratégie réseaux) mais sans articulation claire de la solution complète et de sa valeur."),
    "_7185": mc("_7185", 1.0, "Proposition de valeur implicite mais non formalisée. Pas de formule claire du type 'Nous aidons X à Y grâce à Z'."),
    "_7666": mc("_7666", 0.0, "Manque de cohérence narrative entre besoin, problème, cible et solution. Éléments présents isolément sans fil conducteur."),
    "_1878": mc("_1878", 2.0, "Document de branding professionnel et bien présenté visuellement. Charte graphique de qualité."),

    # Section 2 – Étude de marché (0.0 pts — absent)
    "_6133": mc("_6133", 0.0, ABSENT),
    "_1518": mc("_1518", 0.0, ABSENT),
    "_407":  mc("_407",  0.0, ABSENT),
    "_9867": mc("_9867", 0.0, ABSENT),
    "_2858": mc("_2858", 0.0, ABSENT),
    "_3678": mc("_3678", 0.0, ABSENT),
    "_7629": mc("_7629", 0.0, ABSENT),
    "_1498": mc("_1498", 0.0, ABSENT),
    "_2485": mc("_2485", 0.0, ABSENT),
    "_2602": mc("_2602", 0.0, ABSENT),

    # Section 3 – Personas (0.0 pts — absent)
    "_1059": mc("_1059", 0.0, ABSENT),
    "_91":   mc("_91",   0.0, ABSENT),
    "_4110": mc("_4110", 0.0, ABSENT),
    "_8292": mc("_8292", 0.0, ABSENT),
    "_4829": mc("_4829", 0.0, ABSENT),
    "_7467": mc("_7467", 0.0, ABSENT),
    "_7644": mc("_7644", 0.0, ABSENT),
    "_4132": mc("_4132", 0.0, ABSENT),
    "_8952": mc("_8952", 0.0, ABSENT),
    "_5479": mc("_5479", 0.0, ABSENT),
    "_4661": mc("_4661", 0.0, ABSENT),
    "_6035": mc("_6035", 0.0, ABSENT),
    "_2469": mc("_2469", 0.0, ABSENT),
    "_6063": mc("_6063", 0.0, ABSENT),
    "_3640": mc("_3640", 0.0, ABSENT),
    "_6265": mc("_6265", 0.0, ABSENT),

    # Section 4 – Diagnostic (0.0 pts — absent)
    "_1290": mc("_1290", 0.0, ABSENT),
    "_3809": mc("_3809", 0.0, ABSENT),
    "_4379": mc("_4379", 0.0, ABSENT),
    "_7933": mc("_7933", 0.0, ABSENT),
    "_2400": mc("_2400", 0.0, ABSENT),
    "_6000": mc("_6000", 0.0, ABSENT),
    "_8024": mc("_8024", 0.0, ABSENT),
    "_8099": mc("_8099", 0.0, ABSENT),
    "_1924": mc("_1924", 0.0, ABSENT),
    "_4684": mc("_4684", 0.0, ABSENT),
    "_9901": mc("_9901", 0.0, ABSENT),
    "_8241": mc("_8241", 0.0, ABSENT),
    "_707":  mc("_707",  0.0, ABSENT),
    "_248":  mc("_248",  0.0, ABSENT),
    "_7172": mc("_7172", 0.0, ABSENT),
    "_2509": mc("_2509", 0.0, ABSENT),

    # Section 5 – Objectifs (0.0 pts — absent)
    "_1307": mc("_1307", 0.0, ABSENT),
    "_2713": mc("_2713", 0.0, ABSENT),
    "_7682": mc("_7682", 0.0, ABSENT),
    "_5052": mc("_5052", 0.0, ABSENT),
    "_3498": mc("_3498", 0.0, ABSENT),
    "_7081": mc("_7081", 0.0, ABSENT),
    "_593":  mc("_593",  0.0, ABSENT),
    "_6346": mc("_6346", 0.0, ABSENT),
    "_8367": mc("_8367", 0.0, ABSENT),
    "_7502": mc("_7502", 0.0, ABSENT),
    "_2568": mc("_2568", 0.0, ABSENT),
    "_4771": mc("_4771", 0.0, ABSENT),
    "_6588": mc("_6588", 0.0, ABSENT),

    # Section 6 – Stratégie de marque & communication (6.0 pts — partiel, branding uniquement)
    "_153":  mc("_153",  1.0, "Mission implicite : développer la présence digitale. Mais segmentation formelle absente."),
    "_41":   mc("_41",   1.0, "Positionnement 'premier de classe' en Afrique mentionné. Vision d'envergure continentale notée."),
    "_5323": mc("_5323", 0.0, "Pas de segmentation ni ciblage formels."),
    "_2781": mc("_2781", 0.0, "Pas de lien entre segmentation (absente) et personas (absents)."),
    "_4386": mc("_4386", 0.0, "Ciblage principal non défini."),
    "_1542": mc("_1542", 0.0, "Ciblage secondaire non défini."),
    "_3840": mc("_3840", 0.0, "Pas de justification de ciblage."),
    "_6587": mc("_6587", 1.0, "Services listés (site web, réseaux sociaux, email marketing) comme canaux. Positionnement digital défini."),
    "_3147": mc("_3147", 1.0, "Différenciation implicite par la créativité et l'approche africaine. Présent dans la charte graphique."),
    "_7138": mc("_7138", 0.0, "Identité de marque de l'agence présente mais non appliquée à la stratégie de marque d'un client."),
    "_662":  mc("_662",  0.0, ABSENT),
    "_4155": mc("_4155", 0.0, ABSENT),
    "_7255": mc("_7255", 0.0, ABSENT),
    "_8445": mc("_8445", 0.0, ABSENT),
    "_5149": mc("_5149", 1.0, "Charte graphique bien réalisée avec logo, palette de couleurs, typographie. Branding de qualité."),
    "_3046": mc("_3046", 1.0, "Présentation professionnelle du branding. Qualité visuelle notable."),

    # Section 7 – Tactiques (0.0 pts — absent)
    "_2529": mc("_2529", 0.0, ABSENT),
    "_2198": mc("_2198", 0.0, ABSENT),
    "_6529": mc("_6529", 0.0, ABSENT),
    "_3511": mc("_3511", 0.0, ABSENT),
    "_741":  mc("_741",  0.0, ABSENT),
    "_9818": mc("_9818", 0.0, ABSENT),
    "_4712": mc("_4712", 0.0, ABSENT),
    "_8069": mc("_8069", 0.0, ABSENT),
    "_2955": mc("_2955", 0.0, ABSENT),
    "_2180": mc("_2180", 0.0, ABSENT),
    "_5963": mc("_5963", 0.0, ABSENT),
    "_276":  mc("_276",  0.0, ABSENT),
    "_4227": mc("_4227", 0.0, ABSENT),
    "_1182": mc("_1182", 0.0, ABSENT),
    "_5884": mc("_5884", 0.0, ABSENT),
    "_9870": mc("_9870", 0.0, ABSENT),
    "_8031": mc("_8031", 0.0, ABSENT),
    "_4751": mc("_4751", 0.0, ABSENT),
    "_2911": mc("_2911", 0.0, ABSENT),
    "_1784": mc("_1784", 0.0, ABSENT),
    "_7126": mc("_7126", 0.0, ABSENT),
    "_2457": mc("_2457", 0.0, ABSENT),
    "_7405": mc("_7405", 0.0, ABSENT),

    # Section 8 – Plan d'actions (0.0 pts — absent)
    "_5981": mc("_5981", 0.0, ABSENT),
    "_4317": mc("_4317", 0.0, ABSENT),
    "_8182": mc("_8182", 0.0, ABSENT),
    "_8061": mc("_8061", 0.0, ABSENT),
    "_8862": mc("_8862", 0.0, ABSENT),
    "_6896": mc("_6896", 0.0, ABSENT),
    "_1422": mc("_1422", 0.0, ABSENT),
    "_4276": mc("_4276", 0.0, ABSENT),
    "_4068": mc("_4068", 0.0, ABSENT),
    "_7314": mc("_7314", 0.0, ABSENT),
    "_3298": mc("_3298", 0.0, ABSENT),
    "_6245": mc("_6245", 0.0, ABSENT),
    "_8157": mc("_8157", 0.0, ABSENT),
    "_7239": mc("_7239", 0.0, ABSENT),
    "_4583": mc("_4583", 0.0, ABSENT),
    "_5409": mc("_5409", 0.0, ABSENT),

    # Section 9 – Contrôle (0.0 pts — absent)
    "_5358": mc("_5358", 0.0, ABSENT),
    "_3795": mc("_3795", 0.0, ABSENT),
    "_5882": mc("_5882", 0.0, ABSENT),
    "_7611": mc("_7611", 0.0, ABSENT),
    "_275":  mc("_275",  0.0, ABSENT),
    "_4072": mc("_4072", 0.0, ABSENT),
    "_826":  mc("_826",  0.0, ABSENT),
    "_356":  mc("_356",  0.0, ABSENT),
    "_5213": mc("_5213", 0.0, ABSENT),
    "_615":  mc("_615",  0.0, ABSENT),
    "_2019": mc("_2019", 0.0, ABSENT),
    "_3537": mc("_3537", 0.0, ABSENT),
    "_3924": mc("_3924", 0.0, ABSENT),
    "_3839": mc("_3839", 0.0, ABSENT),
    "_5058": mc("_5058", 0.0, ABSENT),
    "_9270": mc("_9270", 0.0, ABSENT),
    "_1286": mc("_1286", 0.0, ABSENT),
    "_8268": mc("_8268", 0.0, ABSENT),
}

total_1405 = sum(v["points"] for v in evals_1405.values())
write_evaluation(1405, total_1405, evals_1405)


# ============================================================
# ZERO-SCORE STUDENTS (inaccessible)
# Uses RATING_IDS[crit][0.0] for correctness
# ============================================================
ZERO_COMMENT = (
    "Travail non accessible : le dossier Google Drive n'a pas pu être consulté "
    "(permissions insuffisantes ou lien invalide). Note : 0/342.5."
)

ZERO_STUDENTS = [1260, 1261, 1267, 1276, 1280]

ALL_CRITERIA = list(RATING_IDS.keys())

for sid in ZERO_STUDENTS:
    evaluations = {
        cid: {"points": 0.0, "rating_id": RATING_IDS[cid][0.0], "comment": ZERO_COMMENT}
        for cid in ALL_CRITERIA
    }
    data = {
        "student_id": sid,
        "total_points": 0.0,
        "max_points": 342.5,
        "evaluations": evaluations,
    }
    path = EVALUATIONS_DIR / f"evaluation_{sid}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  Written evaluation_{sid}.json  (0/342.5)")

# Summary
print("\nAll evaluations written:")
print(f"  1255 — Resin by ASH         : {total_1255}/342.5")
print(f"  1274 — Signature Events     : {total_1274}/342.5")
print(f"  1401 — ReBelle              : {total_1401}/342.5")
print(f"  1405 — Elavision            : {total_1405}/342.5")
for sid in ZERO_STUDENTS:
    print(f"  {sid} — Zero score (inaccessible): 0.0/342.5")
