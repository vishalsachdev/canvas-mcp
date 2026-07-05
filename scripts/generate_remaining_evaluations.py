"""
Generate evaluation JSON files for:
 - Student 1344: 90.5/342.5 (3 milestones submitted: M5 design thinking, M6 SEO, M8 CRM/AAARRR)
 - All 78 remaining students: 0/342.5 (no accessible content)

Run: python scripts/generate_remaining_evaluations.py
"""
import json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_batch2_evaluations import RATING_IDS, mc, write_evaluation

OUTPUT_DIR = Path(__file__).parent.parent / "exports" / "evaluations"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Student 1344  — "Miel Manzo" brand — 3/9 milestones submitted
# M5: Design Thinking (persona Béatrice, empathy map, user stories, priorisation)
# M6: Site web & SEO (thématique, mots-clés)
# M8: AAARRR funnel / Automation & Pipeline CRM
# Missing: M0 (pitch), M1 (discovery), M2 (SOSTAC), M3 (comm plan), M4 (brand), M7 (campagnes)
# ---------------------------------------------------------------------------

ev_1344 = {
    # ── Section 1 – Pitch Deck (9) – non soumis ──────────────────────────
    "_9714": mc("_9714", 0.0, "Pitch deck non soumis"),
    "_949":  mc("_949",  0.0, "Pitch deck non soumis"),
    "_451":  mc("_451",  0.0, "Pitch deck non soumis"),
    "_7001": mc("_7001", 0.0, "Pitch deck non soumis"),
    "_8064": mc("_8064", 0.0, "Pitch deck non soumis"),
    "_4805": mc("_4805", 0.0, "Pitch deck non soumis"),
    "_7185": mc("_7185", 0.0, "Pitch deck non soumis"),
    "_7666": mc("_7666", 0.0, "Pitch deck non soumis"),
    "_1878": mc("_1878", 0.0, "Pitch deck non soumis"),

    # ── Section 2 – Étude de marché (10) – non soumis ─────────────────────
    "_6133": mc("_6133", 0.0, "Étude de marché non soumise"),
    "_1518": mc("_1518", 0.0, "Étude de marché non soumise"),
    "_407":  mc("_407",  0.0, "Étude de marché non soumise"),
    "_9867": mc("_9867", 0.0, "Étude de marché non soumise"),
    "_2858": mc("_2858", 0.0, "Étude de marché non soumise"),
    "_3678": mc("_3678", 0.0, "Étude de marché non soumise"),
    "_7629": mc("_7629", 0.0, "Étude de marché non soumise"),
    "_1498": mc("_1498", 0.0, "Étude de marché non soumise"),
    "_2485": mc("_2485", 0.0, "Étude de marché non soumise"),
    "_2602": mc("_2602", 0.0, "Étude de marché non soumise"),

    # ── Section 3 – Personas (16) – M5 présent ────────────────────────────
    "_1059": mc("_1059", 1.0, "Marché cible implicitement défini (Kinshasa, consommateurs de miel) mais pas formalisé"),
    "_91":   mc("_91",   1.0, "Segmentation basique: B2C (particuliers) et B2B mentionnés, non développée"),
    "_4110": mc("_4110", 2.5, "Bio détaillée de Béatrice Mawete: 39 ans, fonctionnaire, mariée, 3 enfants, Ngaliema"),
    "_8292": mc("_8292", 1.0, "Comportement digital partiel: WhatsApp, Facebook, marchés locaux mentionnés"),
    "_4829": mc("_4829", 2.5, "Besoins clairement exprimés: canal digital fiable, informations sur qualité/origine, achat facile"),
    "_7467": mc("_7467", 1.0, "Objections partiellement couvertes via méfiance qualité et prix perçu élevé (dans M8)"),
    "_7644": mc("_7644", 1.0, "Pain points implicites dans empathy map mais non étiquetés comme tels"),
    "_4132": mc("_4132", 2.0, "Bonne cohérence entre la persona et le projet Miel Manzo"),
    "_8952": mc("_8952", 1.0, "Insights consommateurs via empathy map (ce que pense/voit/dit/entend l'utilisateur)"),
    "_5479": mc("_5479", 1.0, "Insights actionnables traduits en user stories (8 user stories pertinentes)"),
    "_4661": mc("_4661", 0.0, "Choix du persona non justifié explicitement"),
    "_6035": mc("_6035", 0.0, "Un seul persona défini, pas de priorisation entre plusieurs personas"),
    "_2469": mc("_2469", 1.0, "Observations terrain mentionnées: marchés locaux, vendeurs sans information claire"),
    "_6063": mc("_6063", 0.0, "Un seul persona, pas de différenciation possible"),
    "_3640": mc("_3640", 1.0, "Implications marketing partielles via user stories (bouton commander, page produit, témoignages)"),
    "_6265": mc("_6265", 2.0, "Présentation design thinking bien structurée avec persona, empathy map, définition, idéation"),

    # ── Section 4 – Diagnostic (16) – non soumis ──────────────────────────
    "_1290": mc("_1290", 0.0, "Analyse SWOT non soumise (M2 absent)"),
    "_3809": mc("_3809", 0.0, "Analyse SWOT non soumise"),
    "_4379": mc("_4379", 0.0, "Analyse SWOT non soumise"),
    "_7933": mc("_7933", 0.0, "Analyse SWOT non soumise"),
    "_2400": mc("_2400", 0.0, "Analyse SWOT non soumise"),
    "_6000": mc("_6000", 0.0, "Analyse PESTEL non soumise"),
    "_8024": mc("_8024", 0.0, "Analyse PESTEL non soumise"),
    "_8099": mc("_8099", 0.0, "Analyse PESTEL non soumise"),
    "_1924": mc("_1924", 0.0, "Diagnostic interne/externe non soumis"),
    "_4684": mc("_4684", 0.0, "Diagnostic interne/externe non soumis"),
    "_9901": mc("_9901", 0.0, "Diagnostic interne/externe non soumis"),
    "_8241": mc("_8241", 0.0, "Diagnostic interne/externe non soumis"),
    "_707":  mc("_707",  0.0, "Diagnostic interne/externe non soumis"),
    "_248":  mc("_248",  0.0, "Diagnostic interne/externe non soumis"),
    "_7172": mc("_7172", 0.0, "Diagnostic interne/externe non soumis"),
    "_2509": mc("_2509", 0.0, "Diagnostic interne/externe non soumis"),

    # ── Section 5 – Objectifs SMART & OKR (13) – partiels dans M8 ─────────
    "_1307": mc("_1307", 2.0, "Objectifs formulés de manière SMART-like: 250 ventes, 300 prospects, 5000 abonnés en 6 mois"),
    "_2713": mc("_2713", 2.5, "Objectifs spécifiques: 250 ventes de miel, 300 prospects WhatsApp, 5000 abonnés cumulés"),
    "_7682": mc("_7682", 2.5, "Objectifs mesurables avec KPIs quantifiés (ventes, abonnés, taux engagement ≥5%)"),
    "_5052": mc("_5052", 2.5, "Cibles chiffrées précises: 250 ventes, 300 prospects, 5000 abonnés, 30% notoriété"),
    "_3498": mc("_3498", 2.5, "Horizon temporel défini: 6 mois pour tous les objectifs business"),
    "_7081": mc("_7081", 1.0, "Objectifs semblent réalistes mais aucune baseline fournie pour évaluer l'ambition"),
    "_593":  mc("_593",  0.0, "Pas de baseline / point de départ défini (situation actuelle inconnue)"),
    "_6346": mc("_6346", 0.0, "OKR non formulés"),
    "_8367": mc("_8367", 0.0, "Pas d'Objective OKR formalisé"),
    "_7502": mc("_7502", 0.0, "Pas de Key Results OKR définis"),
    "_2568": mc("_2568", 0.0, "Pas de cohérence SMART-OKR possible (OKR absents)"),
    "_4771": mc("_4771", 1.0, "3 niveaux d'objectifs (business, notoriété, communauté) mais sans priorisation explicite"),
    "_6588": mc("_6588", 1.0, "Objectifs intégrés dans M8 sans section dédiée, présentation partielle"),

    # ── Section 6 – Stratégie (16) – éléments épars dans M5/M8 ───────────
    "_153":  mc("_153",  1.0, "Segmentation évoquée: B2C (Kinshasa) et B2B (cafés, restaurants, boutiques)"),
    "_41":   mc("_41",   1.0, "Critères de segmentation: géographique (Kinshasa) et comportemental (acheteurs miel)"),
    "_5323": mc("_5323", 1.0, "Segment prioritaire implicite: consommateurs particuliers à Kinshasa"),
    "_2781": mc("_2781", 1.0, "Cohérence entre segmentation et persona Béatrice (fonctionnaire Kinshasa)"),
    "_4386": mc("_4386", 1.0, "Ciblage principal: consommateurs Kinshasa cherchant du miel naturel"),
    "_1542": mc("_1542", 1.0, "Ciblage secondaire B2B: cafés, restaurants, boutiques mentionnés"),
    "_3840": mc("_3840", 0.0, "Justification du choix de la cible non explicitée"),
    "_6587": mc("_6587", 1.0, "Positionnement défini: miel 100% naturel, pur, artisanal avec valeurs authenticité/proximité"),
    "_3147": mc("_3147", 1.0, "Différenciation basée sur authenticité, qualité, proximité et aspect naturel"),
    "_7138": mc("_7138", 1.0, "Bonne cohérence entre cible (mères de famille) et positionnement (miel sain et naturel)"),
    "_662":  mc("_662",  0.0, "Pas d'énoncé de positionnement formalisé"),
    "_4155": mc("_4155", 0.0, "Pas de mapping concurrentiel"),
    "_7255": mc("_7255", 0.0, "Attractivité des segments non analysée"),
    "_8445": mc("_8445", 0.0, "Faisabilité du ciblage non évaluée"),
    "_5149": mc("_5149", 1.0, "Promesse associée au positionnement: 'miel 100% naturel et pur pour toute la famille'"),
    "_3046": mc("_3046", 0.0, "Pas de section stratégie dédiée, éléments dispersés dans M5 et M8"),

    # ── Section 7 – Tactiques (23) – M8 AAARRR bien développé ────────────
    "_2529": mc("_2529", 2.0, "Canaux choisis: Facebook, Instagram, Google Ads, WhatsApp Business, email, landing pages"),
    "_2198": mc("_2198", 1.0, "Rôle des canaux partiellement défini (notoriété, acquisition, activation) dans AAARRR"),
    "_6529": mc("_6529", 1.0, "Priorisation implicite via AAARRR mais pas de canal principal explicitement priorisé"),
    "_3511": mc("_3511", 1.0, "Bonne cohérence canaux-cible: WhatsApp et Facebook adaptés au marché kinois"),
    "_741":  mc("_741",  2.5, "Acquisition bien développée: lead magnets, landing pages, formulaires, KPIs CPL définis"),
    "_9818": mc("_9818", 2.0, "Activation décrite: WhatsApp automatique, catalogue produit, offre première commande"),
    "_4712": mc("_4712", 2.0, "Rétention structurée: relance J+7 et J+21, programme fidélité 3 achats = réduction"),
    "_8069": mc("_8069", 2.0, "Programme de recommandation/parrainage décrit avec mécaniques et KPIs"),
    "_2955": mc("_2955", 2.0, "Revenus diversifiés: packs famille/santé, abonnement mensuel, ventes B2B"),
    "_2180": mc("_2180", 2.5, "KPIs définis par étape AAARRR: reach, CPL, taux conversion, taux réachat, parrainages"),
    "_5963": mc("_5963", 1.0, "CRM mentionné (Airtable) et pipeline de suivi WhatsApp Business décrits brièvement"),
    "_276":  mc("_276",  2.0, "Automation décrite: email automatique post-achat, WhatsApp sequences, Fillout pour formulaires"),
    "_4227": mc("_4227", 1.0, "Segmentation CRM partielle: remarketing ciblé selon points de friction identifiés"),
    "_1182": mc("_1182", 0.0, "Stratégie de communication non soumise (M3 absent)"),
    "_5884": mc("_5884", 0.0, "Piliers éditoriaux non définis"),
    "_9870": mc("_9870", 0.0, "Charte éditoriale non présente (M3 absent)"),
    "_8031": mc("_8031", 1.0, "Formats contenus évoqués: vidéos, photos professionnelles, témoignages"),
    "_4751": mc("_4751", 1.0, "Cohérence implicite entre communication naturelle/santé et positionnement miel"),
    "_2911": mc("_2911", 1.0, "Bonne articulation AAARRR-canaux dans M8, logique séquentielle respectée"),
    "_1784": mc("_1784", 0.0, "Plan de contenu non présent"),
    "_7126": mc("_7126", 1.0, "Scénarios CRM décrits: relance satisfaction J+7, rappel J+21, programme fidélité"),
    "_2457": mc("_2457", 1.0, "Tactiques réalistes pour un lancement à Kinshasa avec budget modeste"),
    "_7405": mc("_7405", 2.0, "M8 bien présenté avec tableaux structurés, logique AAARRR claire"),

    # ── Section 8 – Actions (16) – partielles M5 + M8 ────────────────────
    "_5981": mc("_5981", 0.0, "Pas de feuille de route globale / roadmap"),
    "_4317": mc("_4317", 1.0, "Actions définies dans M5 (idéation, priorisation) et M8 (funnel)"),
    "_8182": mc("_8182", 1.0, "Lien entre actions (M5 design, M8 CRM) et tactiques AAARRR"),
    "_8061": mc("_8061", 0.0, "Pas d'échéances précises par action (uniquement '6 mois' global)"),
    "_8862": mc("_8862", 0.0, "Pas de responsables définis pour les actions"),
    "_6896": mc("_6896", 1.0, "Livrables mentionnés: maquette Figma (M5), site web (M6), CRM Airtable (M8)"),
    "_1422": mc("_1422", 0.0, "Pas de budget par action ou canal défini"),
    "_4276": mc("_4276", 0.0, "Cohérence budgétaire non évaluable (budget absent)"),
    "_4068": mc("_4068", 2.0, "Priorisation des actions via matrice d'impact/effort dans M5 (8 actions notées)"),
    "_7314": mc("_7314", 0.0, "Cohérence chronologique non présentée"),
    "_3298": mc("_3298", 0.0, "Dépendances entre actions non identifiées"),
    "_6245": mc("_6245", 1.0, "Ressources identifiées: Miro (maquette), Airtable (CRM), Fillout (formulaires)"),
    "_8157": mc("_8157", 0.0, "Format de suivi du plan d'action non présent"),
    "_7239": mc("_7239", 1.0, "Réalisme opérationnel correct: outils gratuits/accessibles, démarche progressive"),
    "_4583": mc("_4583", 1.0, "Indicateurs de réussite par étape AAARRR (ventes, leads, abonnés, taux réachat)"),
    "_5409": mc("_5409", 0.0, "Pas de section Actions dédiée, éléments dispersés"),

    # ── Section 9 – Contrôle (18) – KPIs dans M8 ─────────────────────────
    "_5358": mc("_5358", 2.5, "KPIs de succès clairement définis par étape AAARRR (reach, CPL, taux conversion, réachat)"),
    "_3795": mc("_3795", 2.0, "Cohérence entre KPIs et objectifs business (250 ventes, 300 prospects, 5000 abonnés)"),
    "_5882": mc("_5882", 1.0, "Plan de tracking implicite via AAARRR mais pas formalisé comme document dédié"),
    "_7611": mc("_7611", 0.0, "Événements GA4 non définis"),
    "_275":  mc("_275",  1.0, "Conversions partiellement définies: taux conversion landing pages, taux de clic"),
    "_4072": mc("_4072", 0.0, "Pixels de tracking non mentionnés"),
    "_826":  mc("_826",  0.0, "UTM non mentionnés"),
    "_356":  mc("_356",  0.0, "Tableau de bord KPI non présenté"),
    "_5213": mc("_5213", 1.0, "Sources de données implicites: WhatsApp Business, formulaires Fillout, Meta Ads"),
    "_615":  mc("_615",  0.0, "Fréquence de suivi non définie"),
    "_2019": mc("_2019", 1.0, "Méthode d'analyse mentionnée: 'KPIs permettent une optimisation continue'"),
    "_3537": mc("_3537", 0.0, "Plan d'optimisation non formalisé"),
    "_3924": mc("_3924", 0.0, "Seuils d'alerte non définis"),
    "_3839": mc("_3839", 0.0, "Plan d'A/B testing non présent"),
    "_5058": mc("_5058", 0.0, "Nomenclature de tracking non définie"),
    "_9270": mc("_9270", 0.0, "Responsabilité du suivi non assignée"),
    "_1286": mc("_1286", 0.0, "Reporting final non présenté"),
    "_8268": mc("_8268", 0.0, "Section Contrôle non dédiée, KPIs intégrés dans M8 sans présentation autonome"),
}

total_1344 = sum(e["points"] for e in ev_1344.values())
print(f"Student 1344 total: {total_1344}/342.5 ({len(ev_1344)} criteria)")
assert len(ev_1344) == 137, f"Expected 137, got {len(ev_1344)}"
assert all(cid.startswith('_') for cid in ev_1344.keys()), "All keys must start with _"
write_evaluation("1344", total_1344, ev_1344)

# ---------------------------------------------------------------------------
# Zero-score evaluations for 78 students with no accessible content
# ---------------------------------------------------------------------------

ZERO_STUDENTS = [
    '919', '1208', '1254', '1262', '1264', '1281', '1282', '1284', '1285',
    '1286', '1287', '1288', '1289', '1290', '1291', '1292', '1293', '1294',
    '1296', '1297', '1298', '1299', '1301', '1305', '1306', '1308', '1309',
    '1310', '1311', '1312', '1313', '1315', '1316', '1317', '1318', '1320',
    '1321', '1322', '1323', '1324', '1325', '1326', '1327', '1328', '1329',
    '1330', '1331', '1333', '1334', '1335', '1336', '1338', '1339', '1341',
    '1342', '1343', '1345', '1347', '1348', '1349', '1351', '1357', '1358',
    '1361', '1368', '1375', '1376', '1377', '1378', '1379', '1380', '1395',
    '1396', '1398', '1408', '1409', '1451', '1460',
]

# Build zero-score evaluation (all criteria at 0.0)
CRIT_IDS = [
    # Section 1 - Pitch
    "_9714", "_949", "_451", "_7001", "_8064", "_4805", "_7185", "_7666", "_1878",
    # Section 2 - Étude de marché
    "_6133", "_1518", "_407", "_9867", "_2858", "_3678", "_7629", "_1498", "_2485", "_2602",
    # Section 3 - Personas
    "_1059", "_91", "_4110", "_8292", "_4829", "_7467", "_7644", "_4132", "_8952",
    "_5479", "_4661", "_6035", "_2469", "_6063", "_3640", "_6265",
    # Section 4 - Diagnostic
    "_1290", "_3809", "_4379", "_7933", "_2400", "_6000", "_8024", "_8099", "_1924",
    "_4684", "_9901", "_8241", "_707", "_248", "_7172", "_2509",
    # Section 5 - Objectifs
    "_1307", "_2713", "_7682", "_5052", "_3498", "_7081", "_593", "_6346", "_8367",
    "_7502", "_2568", "_4771", "_6588",
    # Section 6 - Stratégie
    "_153", "_41", "_5323", "_2781", "_4386", "_1542", "_3840", "_6587", "_3147",
    "_7138", "_662", "_4155", "_7255", "_8445", "_5149", "_3046",
    # Section 7 - Tactiques
    "_2529", "_2198", "_6529", "_3511", "_741", "_9818", "_4712", "_8069", "_2955",
    "_2180", "_5963", "_276", "_4227", "_1182", "_5884", "_9870", "_8031", "_4751",
    "_2911", "_1784", "_7126", "_2457", "_7405",
    # Section 8 - Actions
    "_5981", "_4317", "_8182", "_8061", "_8862", "_6896", "_1422", "_4276", "_4068",
    "_7314", "_3298", "_6245", "_8157", "_7239", "_4583", "_5409",
    # Section 9 - Contrôle
    "_5358", "_3795", "_5882", "_7611", "_275", "_4072", "_826", "_356", "_5213",
    "_615", "_2019", "_3537", "_3924", "_3839", "_5058", "_9270", "_1286", "_8268",
]

assert len(CRIT_IDS) == 137, f"Expected 137 crit IDs, got {len(CRIT_IDS)}"

zero_evaluations = {cid: mc(cid, 0.0, "Travail non accessible ou non soumis") for cid in CRIT_IDS}

skipped = 0
written = 0
for sid in ZERO_STUDENTS:
    eval_path = OUTPUT_DIR / f"evaluation_{sid}.json"
    if eval_path.exists():
        skipped += 1
        continue
    write_evaluation(sid, 0.0, zero_evaluations)
    written += 1

print(f"\nZero-score: {written} written, {skipped} already existed")
print(f"\nDone. Total files in exports/evaluations/: {len(list(OUTPUT_DIR.glob('evaluation_*.json')))}")
