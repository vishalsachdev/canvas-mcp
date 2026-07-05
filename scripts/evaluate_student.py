"""
evaluate_student.py - Evaluate a student's extracted content against the Chef d'Oeuvre rubric.

Outputs a JSON evaluation file with per-criterion points and feedback in French.
Uses Claude claude-sonnet-4-5 via Anthropic API.

Usage:
    python scripts/evaluate_student.py --student-id 1272
    python scripts/evaluate_student.py --student-id 1272 --dry-run   # show prompt only
    python scripts/evaluate_student.py --all --batch 5              # evaluate batch of 5 unevaluated students
"""
import argparse
import json
import os
import sys
import csv
from pathlib import Path

STUDENT_TEXTS_DIR = Path(__file__).parent.parent / "exports" / "student_texts"
EVALUATIONS_DIR = Path(__file__).parent.parent / "exports" / "evaluations"

# All 137 rubric criteria in order (criterion_id, section, name, ratings dict)
# ratings: {2.5: (description, rating_id), 2.0: ..., 1.0: ..., 0.0: ...}
RUBRIC_CRITERIA = [
    # === Pitch Deck / Brief projet (9 criteria) ===
    {"id": "_9714", "section": "Pitch Deck / Brief projet", "name": "Compréhension du besoin",
     "ratings": {2.5: ("Le besoin est clairement expliqué ce que le porteur veut lancer, ce qui lui manque actuellement, pourquoi il a besoin d'une stratégie digitale et quel résultat il attend", "_6396"),
                 2.0: ("Le besoin est compris et expliqué, mais certains éléments comme le contexte ou le résultat attendu restent peu détaillés", "_2144"),
                 1.0: ("Le besoin est mentionné, mais il reste vague. On comprend mal pourquoi une stratégie digitale est nécessaire", "_9728"),
                 0.0: ("Le besoin n'est pas identifié ou l'explication est hors sujet.", "_6467")}},
    {"id": "_949", "section": "Pitch Deck / Brief projet", "name": "Description du projet",
     "ratings": {2.5: ("Le projet est présenté avec précision: nom, secteur, produit/service, contexte de lancement, stade actuel et ambition générale.", "_1388"),
                 2.0: ("Le projet est clair on comprend le produit/service, le secteur et l'idée générale.", "_3798"),
                 1.0: ("Le projet est partiellement présenté des informations importantes manquent comme le secteur, l'offre ou le contexte.", "_9502"),
                 0.0: ("Le projet n'est pas clairement décrit. On ne comprend pas ce qui est lancé", "_4157")}},
    {"id": "_451", "section": "Pitch Deck / Brief projet", "name": "Identification du problème",
     "ratings": {2.5: ("Le problème est précis, concret et relié à une cible: qui rencontre le problème, dans quelle situation et avec quelles conséquences", "_8963"),
                 2.0: ("Le problème est clair et cohérent avec le projet. Il justifie la solution proposée.", "_1364"),
                 1.0: ("Le problème est évoqué, mais il est trop général ou mal relié à la cible.", "_3913"),
                 0.0: ("Aucun problème clair n'est identifié.", "_9229")}},
    {"id": "_7001", "section": "Pitch Deck / Brief projet", "name": "Définition de la cible",
     "ratings": {2.5: ("La cible est définie avec précision segment, profil, localisation besoins, comportements digitaux, capacité d'achat/action et justification du choix.", "_5829"),
                 2.0: ("La cible principale est clairement identifiée et cohérente avec le projet", "_8930"),
                 1.0: ("La cible est trop large ou imprécise, par exemple 'les jeunes', 'les femmes', 'les entreprises', sans segmentation.", "_8770"),
                 0.0: ("Aucune cible claire n'est définie ou la cible n'a pas de lien avec le projet.", "_2609")}},
    {"id": "_8064", "section": "Pitch Deck / Brief projet", "name": "Identification des besoins de la cible",
     "ratings": {2.5: ("Les besoins sont clairement identifiés et reliés au projet besoins pratiques, émotionnels, financiers ou fonctionnels", "_7774"),
                 2.0: ("Les principaux besoins de la cible sont présents et cohérents avec la solution", "_1473"),
                 1.0: ("Les besoins sont évoqués de manière générique, sans précision réelle.", "_5912"),
                 0.0: ("Les besoins de la cible ne sont pas identifiés.", "_4581")}},
    {"id": "_4805", "section": "Pitch Deck / Brief projet", "name": "Solution proposée",
     "ratings": {2.5: ("La solution répond clairement au problème ce qu'elle apporte, comment elle fonctionne, pourquoi elle est utile et adaptée à la cible.", "_2092"),
                 2.0: ("La solution est claire et cohérente avec le problème identifié.", "_11"),
                 1.0: ("La solution est mentionnée, mais elle reste floue ou peu reliée au problème.", "_1887"),
                 0.0: ("Aucune solution pertinente n'est proposée.", "_6646")}},
    {"id": "_7185", "section": "Pitch Deck / Brief projet", "name": "Proposition de valeur",
     "ratings": {2.5: ("La proposition de valeur est claire différenciante et formulée simplement bénéfice principal raison de choisir cette offre.", "_2749"),
                 2.0: ("La proposition de valeur est présente et compréhensible, mais la différenciation peut être renforcée", "_7612"),
                 1.0: ("La proposition de valeur ressemble à une simple description de l'offre sans bénéfice clair", "_8360"),
                 0.0: ("Aucune proposition de valeur n'est formulée", "_4266")}},
    {"id": "_7666", "section": "Pitch Deck / Brief projet", "name": "Cohérence besoin-problème-cible-solution",
     "ratings": {2.5: ("Tous les éléments sont parfaitement alignés une cible précise a un problème précis, et la solution répond directement à ce problème", "_2007"),
                 2.0: ("Les éléments sont cohérents entre eux, même si l'argumentation peut être approfondie", "_7879"),
                 1.0: ("Certains éléments sont présents, mais le lien logique entre besoin, problème, cible et solution est faible", "_904"),
                 0.0: ("Les éléments sont incohérents ou ne semblent pas appartenir au même projet", "_604")}},
    {"id": "_1878", "section": "Pitch Deck / Brief projet", "name": "Qualité de présentation du pitch deck",
     "ratings": {2.5: ("Le support est professionnel structure logique, slides lisibles, titres clairs design propre, informations hiérarchisées et peu de fautes", "_7578"),
                 2.0: ("Le support est clair et lisible, même si la mise en forme peut être améliorée", "_7012"),
                 1.0: ("Le support est difficile à suivre trop chargé, désorganisé ou peu lisible", "_2431"),
                 0.0: ("Aucun support exploitable n'est fourni", "_979")}},
    # === Étude de marché (10 criteria) ===
    {"id": "_6133", "section": "Étude de marché", "name": "Compréhension du marché étudié",
     "ratings": {2.5: ("Le marché est clairement défini secteur type d'offre, zone géographique clientèle concernée, contexte actuel et enjeu principal du marché. Une personne extérieure comprend exactement dans quel marché le projet va entrer", "_1202"),
                 2.0: ("Le marché est identifié et compréhensible secteur, offre et clientèle sont présentés, même si le contexte reste peu approfondi", "_9969"),
                 1.0: ("Le marché est évoqué, mais de manière trop générale.", "_9753"),
                 0.0: ("Le marché n'est pas défini ou le marché présenté n'a pas de lien clair avec le projet", "_6692")}},
    {"id": "_1518", "section": "Étude de marché", "name": "Identification des opportunités de marché",
     "ratings": {2.5: ("Les opportunités sont précises et justifiées besoin non satisfait, segment mal servi tendance favorable canal sous-exploité faiblesse des concurrents ou évolution du comportement client", "_3364"),
                 2.0: ("Les opportunités principales sont identifiées et cohérentes avec le projet", "_7199"),
                 1.0: ("Les opportunités sont mentionnées, mais elles restent vagues ou non prouvées.", "_239"),
                 0.0: ("Aucune opportunité claire n'est identifiée.", "_8443")}},
    {"id": "_407", "section": "Étude de marché", "name": "Identification des risques ou menaces du marché",
     "ratings": {2.5: ("Les risques sont clairement identifiés forte concurrence, faible pouvoir d'achat, manque de confiance, réglementation, coût d'acquisition élevé habitudes difficiles à changer ou barrière technologique", "_7129"),
                 2.0: ("Les risques principaux sont présents et cohérents avec le contexte du projet", "_9417"),
                 1.0: ("Les risques sont évoqués de manière très générale sans montrer comment ils peuvent affecter le projet.", "_7328"),
                 0.0: ("Aucun risque ou menace n'est identifié", "_3420")}},
    {"id": "_9867", "section": "Étude de marché", "name": "Analyse concurrentielle - Identification des concurrents",
     "ratings": {2.5: ("Les concurrents directs et indirects sont clairement listés, avec leur nom, type d'offre, cible, canaux digitaux utilisés et positionnement général", "_8112"),
                 2.0: ("Les principaux concurrents directs et indirects sont identifiés, même si certaines informations restent limitées", "_1005"),
                 1.0: ("Quelques concurrents sont mentionnés, mais la liste est incomplète, peu pertinente ou non structurée", "_4850"),
                 0.0: ("Aucun concurrent pertinent n'est identifié", "_7976")}},
    {"id": "_2858", "section": "Étude de marché", "name": "Analyse concurrentielle - Comparaison des concurrents",
     "ratings": {2.5: ("Les concurrents sont comparés sur des critères précis: prix, offre, positionnement, communication réseaux sociaux, expérience client, forces faiblesses et différenciation", "_6280"),
                 2.0: ("Les concurrents sont comparés sur quelques critères utiles, permettant de comprendre leurs forces et faiblesses principales.", "_4483"),
                 1.0: ("Les concurrents sont seulement listés, sans vraie comparaison", "_7687"),
                 0.0: ("Aucune comparaison concurrentielle n'est faite", "_4784")}},
    {"id": "_3678", "section": "Étude de marché", "name": "Mini-étude TAM/SAM/SOM",
     "ratings": {2.5: ("Le TAM le SAM et le SOM sont clairement distingués, chiffrés ou estimés, présentés dans un tableau avec sources ou hypothèses.", "_494"),
                 2.0: ("Le TAM, le SAM et le SOM sont présents et cohérents, même si certaines estimations restent approximatives.", "_215"),
                 1.0: ("Le TAM/SAM/SOM est incomplet, confus ou mal expliqué.", "_3027"),
                 0.0: ("Aucune mini-étude TAM/SAM/SOM n'est présentée", "_2981")}},
    {"id": "_7629", "section": "Étude de marché", "name": "Utilisation de sources fiables ou hypothèses justifiées",
     "ratings": {2.5: ("Les données importantes sont accompagnées de sources vérifiables rapports, sites officiels études, articles observations terrain ou hypothèses clairement expliquées.", "_3480"),
                 2.0: ("Les principales informations sont sourcées ou justifiées, même si toutes les données ne sont pas parfaitement documentées", "_4474"),
                 1.0: ("Quelques sources sont indiquées, mais elles sont insuffisantes, peu fiables ou mal reliées aux informations utilisées", "_988"),
                 0.0: ("Aucune source ou justification n'est fournie", "_3552")}},
    {"id": "_1498", "section": "Étude de marché", "name": "Synthèse des conclusions marché",
     "ratings": {2.5: ("L'apprenant termine par une synthèse claire ce que l'étude révèle, ce que cela signifie pour le projet quelles opportunités prioriser et quels risques surveiller", "_328"),
                 2.0: ("Une synthèse est présente et permet de comprendre les conclusions principales de l'étude", "_7598"),
                 1.0: ("La synthèse est trop vague ou se limite à répéter des informations sans conclusion stratégique", "_6592"),
                 0.0: ("Aucune synthèse n'est proposée", "_5892")}},
    {"id": "_2485", "section": "Étude de marché", "name": "Qualité de l'analyse des données terrain",
     "ratings": {2.5: ("Les données issues des entretiens ou du sondage sont transformées en enseignements clairs besoins clients objections comportements attentes, canaux ou opportunités.", "_5030"),
                 2.0: ("Les données terrain sont résumées et donnent quelques informations utiles pour la suite du projet", "_1732"),
                 1.0: ("Les données terrain sont présentées, mais sans vraie interprétation.", "_6633"),
                 0.0: ("Aucune donnée terrain n'est analysée", "_1589")}},
    {"id": "_2602", "section": "Étude de marché", "name": "Qualité de présentation du document",
     "ratings": {2.5: ("Le document est clair structuré et lisible titres, tableaux, sources, graphiques simples si nécessaire, synthèse finale et présentation professionnelle", "_6878"),
                 2.0: ("Le document est compréhensible et structuré, même si la mise en page peut être améliorée", "_1587"),
                 1.0: ("Le document est difficile à lire, désorganisé ou trop chargé.", "_3081"),
                 0.0: ("Aucun document exploitable n'est fourni", "_6372")}},
    # === Étude de la cible / Personas (16 criteria) ===
    {"id": "_1059", "section": "Étude de la cible / Personas", "name": "Définition du marché cible",
     "ratings": {2.5: ("Le marché cible est défini avec précision segment principal, zone géographique, profil général, type de besoin, pouvoir d'achat ou capacité d'action, et lien direct avec le projet", "_4672"),
                 2.0: ("Le marché cible est clairement identifié et cohérent avec l'offre, même si certains détails restent peu approfondis", "_9987"),
                 1.0: ("Le marché cible est mentionné, mais reste trop large ou imprécis", "_1021"),
                 0.0: ("Aucun marché cible n'est défini ou la cible choisie n'a pas de lien logique avec le projet", "_2320")}},
    {"id": "_91", "section": "Étude de la cible / Personas", "name": "Segmentation de la cible",
     "ratings": {2.5: ("L'apprenant distingue clairement plusieurs segments de cible: cible principale, cible secondaire, éventuellement prescripteurs ou influenceurs, avec une justification du choix prioritaire", "_9481"),
                 2.0: ("La cible principale est bien distinguée des autres profils possibles, même si la segmentation reste simple", "_4080"),
                 1.0: ("Plusieurs profils sont évoqués, mais sans vraie distinction entre cible principale, secondaire ou prioritaire.", "_3670"),
                 0.0: ("Aucune segmentation n'est faite.", "_6379")}},
    {"id": "_4110", "section": "Étude de la cible / Personas", "name": "Bio courte de chaque persona",
     "ratings": {2.5: ("Chaque persona contient une bio claire: nom fictif, âge ou tranche d'âge, situation professionnelle/personnelle, contexte de vie, motivation principale et lien avec le produit/service.", "_9966"),
                 2.0: ("Chaque persona contient une bio compréhensible avec les informations principales, même si elle manque de profondeur.", "_6727"),
                 1.0: ("Les bios sont très courtes ou superficielles.", "_9399"),
                 0.0: ("Les bios sont absentes.", "_513")}},
    {"id": "_8292", "section": "Étude de la cible / Personas", "name": "Comportement digital de chaque persona",
     "ratings": {2.5: ("Les comportements digitaux sont précis: plateformes utilisées, fréquence d'utilisation, type de contenus consommés, habitudes de recherche, canaux de confiance et comportement face à la publicité", "_2728"),
                 2.0: ("Les principaux comportements digitaux sont identifiés réseaux utilisés, habitudes en ligne et canaux principaux.", "_5674"),
                 1.0: ("Les comportements digitaux sont mentionnés de manière vague", "_5196"),
                 0.0: ("Aucun comportement digital n'est indiqué", "_2944")}},
    {"id": "_4829", "section": "Étude de la cible / Personas", "name": "Besoins de chaque persona",
     "ratings": {2.5: ("Les besoins sont clairement identifiés pour chaque persona: besoins pratiques, émotionnels, financiers, sociaux ou professionnels, avec un lien direct avec l'offre", "_9703"),
                 2.0: ("Les principaux besoins de la cible sont présents et cohérents avec le produit/service proposé.", "_1503"),
                 1.0: ("Les besoins sont génériques ou répétitifs", "_7074"),
                 0.0: ("Les besoins des personas ne sont pas identifiés", "_716")}},
    {"id": "_7467", "section": "Étude de la cible / Personas", "name": "Objections de chaque persona",
     "ratings": {2.5: ("Les objections sont précises: prix, manque de confiance, peur du risque, manque de temps, difficulté d'utilisation préférence pour une alternative, doute sur la qualité ou manque d'information", "_8999"),
                 2.0: ("Les objections principales sont présentes et cohérentes avec le profil de chaque persona.", "_6060"),
                 1.0: ("Les objections sont trop générales ou identiques pour tous les personas", "_5614"),
                 0.0: ("Aucune objection n'est identifiée", "_2004")}},
    {"id": "_7644", "section": "Étude de la cible / Personas", "name": "3 pain points par persona",
     "ratings": {2.5: ("Chaque persona contient 3 pain points concrets, formulés comme de vrais problèmes vécus par la cible. Les pain points sont spécifiques et reliés à l'offre", "_2721"),
                 2.0: ("Chaque persona contient 3 pain points globalement cohérents, même si certains restent peu détaillés.", "_2172"),
                 1.0: ("Les pain points sont incomplets, vagues ou mal formulés.", "_4527"),
                 0.0: ("Les pain points sont absents ou n'ont aucun lien avec le projet", "_2588")}},
    {"id": "_4132", "section": "Étude de la cible / Personas", "name": "Cohérence entre personas et projet",
     "ratings": {2.5: ("Les personas correspondent clairement au projet leurs besoins, problèmes, comportements et objections expliquent pourquoi ils peuvent être intéressés par l'offre.", "_2874"),
                 2.0: ("Les personas sont cohérents avec le projet, même si le lien avec l'offre pourrait être mieux expliqué.", "_2538"),
                 1.0: ("Certains personas semblent partiellement liés au projet, mais le lien avec l'offre reste faible ou confus", "_2894"),
                 0.0: ("Les personas ne correspondent pas au projet ou semblent choisis au hasard", "_877")}},
    {"id": "_8952", "section": "Étude de la cible / Personas", "name": "Insights consommateurs",
     "ratings": {2.5: ("Les insights sont formulés clairement l'apprenant explique ce qu'il a compris sur la cible, ses motivations, ses freins, ses habitudes et ses attentes", "_4636"),
                 2.0: ("Les principaux insights sont présents et utiles pour comprendre la cible.", "_7685"),
                 1.0: ("Les insights sont vagues ou ressemblent à de simples constats, sans vraie profondeur.", "_5841"),
                 0.0: ("Aucun insight consommateur n'est formulé", "_5311")}},
    {"id": "_5479", "section": "Étude de la cible / Personas", "name": "Insights actionnables pour la stratégie",
     "ratings": {2.5: ("Les insights sont directement transformés en décisions marketing: message à utiliser, canal à privilégier, offre à adapter, objection à traiter ou contenu à produire", "_2909"),
                 2.0: ("Les insights donnent quelques pistes utiles pour orienter la stratégie", "_6400"),
                 1.0: ("Les insights sont présents, mais on ne voit pas clairement comment ils seront utilisés dans la stratégie.", "_4499"),
                 0.0: ("Aucun lien n'est fait entre les insights et la stratégie", "_2802")}},
    {"id": "_4661", "section": "Étude de la cible / Personas", "name": "Justification du choix des personas",
     "ratings": {2.5: ("L'apprenant explique pourquoi ces 3 personas ont été choisis: potentiel commercial, urgence du besoin, accessibilité digitale, capacité d'achat, influence ou priorité stratégique", "_5309"),
                 2.0: ("Le choix des personas est justifié de manière simple et cohérente", "_2902"),
                 1.0: ("La justification est faible ou très générale.", "_3718"),
                 0.0: ("Aucune justification du choix des personas n'est donnée", "_7555")}},
    {"id": "_6035", "section": "Étude de la cible / Personas", "name": "Priorisation des personas",
     "ratings": {2.5: ("Les personas sont classés par priorité: cible principale, cible secondaire, cible d'influence ou cible à travailler plus tard. La priorité est justifiée.", "_1850"),
                 2.0: ("Les personas sont priorisés, même si la justification reste simple", "_30"),
                 1.0: ("Les personas sont présentés sans hiérarchie claire.", "_1479"),
                 0.0: ("Aucune priorisation n'est faite", "_7511")}},
    {"id": "_2469", "section": "Étude de la cible / Personas", "name": "Données ou observations utilisées",
     "ratings": {2.5: ("Les personas s'appuient sur des données ou observations: sondage, entretien, étude de marché, analyse concurrentielle, observation terrain ou hypothèses clairement justifiées", "_1917"),
                 2.0: ("Les personas sont appuyés par quelques données ou hypothèses cohérentes.", "_7088"),
                 1.0: ("Les personas semblent principalement inventés, avec peu de lien visible avec des données ou observations", "_2246"),
                 0.0: ("Aucune donnée, observation ou hypothèse ne soutient les personas.", "_4288")}},
    {"id": "_6063", "section": "Étude de la cible / Personas", "name": "Différenciation entre les personas",
     "ratings": {2.5: ("Les 3 personas ont des profils, besoins, objections, comportements digitaux et motivations réellement différents. Chaque persona apporte une lecture utile de la cible", "_7872"),
                 2.0: ("Les personas présentent quelques différences claires, même si certaines informations se répètent", "_5583"),
                 1.0: ("Les personas sont très similaires et donnent peu d'informations nouvelles", "_9664"),
                 0.0: ("Les personas sont identiques ou presque identiques.", "_5978")}},
    {"id": "_3640", "section": "Étude de la cible / Personas", "name": "Implications marketing par persona",
     "ratings": {2.5: ("Pour chaque persona, l'apprenant propose au moins une implication marketing: message clé, canal recommandé, type de contenu, argument de vente ou approche de conversion", "_7814"),
                 2.0: ("Les implications marketing sont présentes pour les personas principaux, même si elles peuvent être plus détaillées.", "_9091"),
                 1.0: ("Les implications sont vagues ou non personnalisées selon les personas", "_1672"),
                 0.0: ("Aucune implication marketing n'est proposée.", "_1506")}},
    {"id": "_6265", "section": "Étude de la cible / Personas", "name": "Qualité de présentation des fiches personas",
     "ratings": {2.5: ("Les fiches sont claires, lisibles et bien structurées: informations hiérarchisées, présentation propre, catégories visibles, formulation simple et professionnelle", "_1179"),
                 2.0: ("Les fiches sont compréhensibles et organisées, même si la mise en page peut être améliorée", "_6700"),
                 1.0: ("Les fiches sont difficiles à lire, mal structurées ou trop chargées.", "_2202"),
                 0.0: ("Aucun support exploitable n'est fourni", "_3997")}},
    # === Diagnostic interne & externe (16 criteria) ===
    {"id": "_1290", "section": "Diagnostic interne & externe", "name": "Réalisation de l'analyse SWOT",
     "ratings": {2.5: ("La SWOT est complète, équilibrée et bien structurée: forces, faiblesses, opportunités et menaces sont clairement identifiées, avec des éléments précis et liés au projet", "_509"),
                 2.0: ("La SWOT est présente avec les 4 parties principales et des éléments globalement cohérents avec le projet.", "_8410"),
                 1.0: ("La SWOT est incomplète, trop générale ou contient des éléments mal classés", "_9100"),
                 0.0: ("Aucune SWOT n'est présentée ou elle est hors sujet", "_6014")}},
    {"id": "_3809", "section": "Diagnostic interne & externe", "name": "Identification des forces internes",
     "ratings": {2.5: ("Les forces sont précises et concernent directement le projet: avantages de l'offre, ressources, compétences, différenciation, qualité, accès à une cible ou capacité d'exécution.", "_9079"),
                 2.0: ("Les forces principales sont identifiées et cohérentes avec le projet", "_7514"),
                 1.0: ("Les forces sont vagues, par exemple 'bonne qualité', 'bonne équipe', sans explication concrète.", "_8623"),
                 0.0: ("Aucune force interne n'est identifiée.", "_9608")}},
    {"id": "_4379", "section": "Diagnostic interne & externe", "name": "Identification des faiblesses internes",
     "ratings": {2.5: ("Les faiblesses sont réalistes et liées au projet: manque de notoriété, absence de site, budget limité, faible communauté, manque de preuves clients ressources limitées ou manque d'expérience disponibles", "_9095"),
                 2.0: ("Les faiblesses principales sont identifiées et cohérentes avec le stade du projet.", "_579"),
                 1.0: ("Les faiblesses sont mentionnées, mais elles restent superficielles ou peu liées au projet", "_4503"),
                 0.0: ("Aucune faiblesse interne n'est identifiée.", "_7474")}},
    {"id": "_7933", "section": "Diagnostic interne & externe", "name": "Identification des opportunités externes",
     "ratings": {2.5: ("Les opportunités sont concrètes et liées au marché: tendance favorable, besoin non satisfait, canal digital sous-exploité, segment mal servi, évolution technologique, partenariat possible ou demande croissante", "_3281"),
                 2.0: ("Les opportunités principales sont présentes et cohérentes avec l'environnement du projet.", "_6150"),
                 1.0: ("Les opportunités sont trop générales", "_4173"),
                 0.0: ("Aucune opportunité externe n'est identifiée", "_2073")}},
    {"id": "_2400", "section": "Diagnostic interne & externe", "name": "Identification des menaces externes",
     "ratings": {2.5: ("Les menaces sont réalistes: concurrence forte, faible pouvoir d'achat, manque de confiance, réglementation, coût publicitaire élevé, habitudes de consommation difficiles à changer ou instabilité du marché", "_4193"),
                 2.0: ("Les menaces principales sont identifiées et cohérentes avec le contexte du projet.", "_5059"),
                 1.0: ("Les menaces sont évoquées de manière vague, sans expliquer leur impact possible sur le projet", "_1462"),
                 0.0: ("Aucune menace externe n'est identifiée.", "_6635")}},
    {"id": "_6000", "section": "Diagnostic interne & externe", "name": "Réalisation de l'analyse PESTEL",
     "ratings": {2.5: ("La PESTEL couvre les dimensions pertinentes: politique, économique, sociale, technologique, environnementale et légale Chaque facteur est relié au projet et à son impact potentiel.", "_5872"),
                 2.0: ("La PESTEL est présente avec les dimensions principales et des éléments globalement cohérents", "_2046"),
                 1.0: ("La PESTEL est partielle, trop générale ou contient des éléments qui ne sont pas clairement reliés au projet", "_6958"),
                 0.0: ("Aucune PESTEL n'est présentée.", "_1833")}},
    {"id": "_8024", "section": "Diagnostic interne & externe", "name": "Pertinence des facteurs PESTEL",
     "ratings": {2.5: ("Les facteurs retenus sont réellement utiles pour comprendre le contexte du projet. L'apprenant explique comment chaque facteur peut influencer le lancement, la communication, le prix, l'acquisition ou la confiance client.", "_9989"),
                 2.0: ("Les facteurs PESTEL sont pertinents, même si leur impact n'est pas toujours approfondi.", "_1857"),
                 1.0: ("Certains facteurs sont présents, mais ils semblent choisis au hasard ou restent trop théoriques.", "_5886"),
                 0.0: ("Les facteurs PESTEL sont absents ou sans lien avec le projet.", "_3612")}},
    {"id": "_8099", "section": "Diagnostic interne & externe", "name": "Lien entre diagnostic et projet",
     "ratings": {2.5: ("Toutes les analyses sont appliquées au projet choisi. Le formateur voit clairement comment la SWOT et la PESTEL aident à comprendre les enjeux réels du lancement", "_5412"),
                 2.0: ("Le diagnostic est globalement relié au projet, même si certains éléments pourraient être mieux contextualisés.", "_5172"),
                 1.0: ("Le diagnostic semble générique et pourrait s'appliquer à n'importe quel projet.", "_8841"),
                 0.0: ("Le diagnostic n'a aucun lien clair avec le projet.", "_7387")}},
    {"id": "_1924", "section": "Diagnostic interne & externe", "name": "Identification des enjeux prioritaires",
     "ratings": {2.5: ("L'apprenant identifies les enjeux les plus importants à traiter: notoriété, acquisition, confiance, conversion, différenciation, budget, expérience utilisateur ou rétention.", "_8219"),
                 2.0: ("Les principaux enjeux sont identifiés et cohérents avec le diagnostic.", "_7835"),
                 1.0: ("Les enjeux sont mentionnés, mais ils ne sont pas priorisés ou restent difficiles à comprendre", "_9991"),
                 0.0: ("Aucun enjeu prioritaire n'est identifié", "_3097")}},
    {"id": "_4684", "section": "Diagnostic interne & externe", "name": "Conclusion stratégique du diagnostic",
     "ratings": {2.5: ("Le diagnostic se termine par une conclusion claire expliquant ce que l'apprenant retient et comment cela doit influencer la stratégie marketing", "_6156"),
                 2.0: ("Une conclusion est présente et reprend les principaux enseignements du diagnostic", "_1721"),
                 1.0: ("La conclusion est vague ou se limite à résumer sans expliquer les conséquences stratégiques", "_7974"),
                 0.0: ("Aucune conclusion stratégique n'est proposée", "_6211")}},
    {"id": "_9901", "section": "Diagnostic interne & externe", "name": "Priorisation des forces et faiblesses",
     "ratings": {2.5: ("L'apprenant distingue les forces les plus utiles à exploiter et les faiblesses les plus urgentes à corriger", "_1003"),
                 2.0: ("Les forces et faiblesses importantes sont identifiées, même si la priorisation reste simple.", "_7635"),
                 1.0: ("Toutes les forces et faiblesses sont présentées au même niveau, sans indication de priorité.", "_7918"),
                 0.0: ("Aucune priorisation n'est faite.", "_7512")}},
    {"id": "_8241", "section": "Diagnostic interne & externe", "name": "Priorisation des opportunités et menaces",
     "ratings": {2.5: ("L'apprenant distingue les opportunités à exploiter en premier et les menaces à surveiller en priorité.", "_1023"),
                 2.0: ("Les opportunités et menaces importantes sont reconnues, même si leur niveau de priorité reste peu détaillé.", "_4060"),
                 1.0: ("Les opportunités et menaces sont listées sans hiérarchie claire.", "_8467"),
                 0.0: ("Aucune priorisation n'est faite.", "_2296")}},
    {"id": "_707", "section": "Diagnostic interne & externe", "name": "Justification des éléments du diagnostic",
     "ratings": {2.5: ("Les éléments du diagnostic sont justifiés par des observations, données, sources, analyse concurrentielle, étude de marché ou hypothèses clairement expliquées.", "_3370"),
                 2.0: ("Les principaux éléments sont justifiés, même si toutes les informations ne sont pas sourcées", "_3133"),
                 1.0: ("Les éléments sont affirmés sans preuve suffisante ou sans explication claire.", "_7670"),
                 0.0: ("Aucune justification n'est fournie", "_9241")}},
    {"id": "_248", "section": "Diagnostic interne & externe", "name": "Analyse des risques",
     "ratings": {2.5: ("L'apprenant identifie les risques majeurs pour le projet et explique leurs conséquences possibles: faible conversion, manque de confiance, budget insuffisant, mauvais ciblage, difficulté technique ou saturation du marché.", "_3432"),
                 2.0: ("Les principaux risques sont identifiés et cohérents avec le projet.", "_7757"),
                 1.0: ("Les risques sont évoqués, mais sans explication claire de leurs conséquences", "_9843"),
                 0.0: ("Aucun risque n'est identifié.", "_3130")}},
    {"id": "_7172", "section": "Diagnostic interne & externe", "name": "Recommandations issues du diagnostic",
     "ratings": {2.5: ("L'apprenant propose des recommandations concrètes à partir du diagnostic exploiter une force, corriger une faiblesse, saisir une opportunité ou réduire une menace.", "_8330"),
                 2.0: ("Quelques recommandations cohérentes sont proposées à partir du diagnostic", "_223"),
                 1.0: ("Les recommandations sont vagues ou peu reliées à la SWOT/PESTEL", "_7349"),
                 0.0: ("Aucune recommandation n'est proposée.", "_4095")}},
    {"id": "_2509", "section": "Diagnostic interne & externe", "name": "Qualité de présentation du diagnostic",
     "ratings": {2.5: ("Le diagnostic est bien présenté: tableaux lisibles, éléments courts et précis, titres clairs, synthèse finale et mise en page professionnelle.", "_2637"),
                 2.0: ("Le document est lisible et compréhensible, même si la présentation peut être améliorée", "_1299"),
                 1.0: ("Le diagnostic est difficile à lire, désorganisé ou trop chargé", "_8109"),
                 0.0: ("Aucun support exploitable n'est fourni.", "_2771")}},
    # === SOSTAC - Objectifs SMART & OKR (13 criteria) ===
    {"id": "_1307", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Formulation des objectifs SMART",
     "ratings": {2.5: ("Les objectifs sont formulés de manière complète avec les 5 éléments SMART: spécifique, mesurable, atteignable, réaliste et temporellement défini.", "_4417"),
                 2.0: ("Les objectifs sont globalement SMART, ils sont compréhensibles et mesurables, mais certains éléments peuvent manquer de précision", "_8226"),
                 1.0: ("Les objectifs sont partiellement formulés. Ils ressemblent encore à des intentions générales", "_5955"),
                 0.0: ("Aucun objectif SMART n'est formulé", "_6005")}},
    {"id": "_2713", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Spécificité des objectifs",
     "ratings": {2.5: ("Chaque objectif indique clairement ce que l'apprenant veut améliorer ou atteindre: notoriété, trafic, leads, conversion, ventes, inscriptions, engagement ou fidélisation.", "_3830"),
                 2.0: ("Les objectifs indiquent globalement ce qui doit être amélioré, même si la formulation peut être plus précise", "_9063"),
                 1.0: ("Les objectifs sont trop larges ou flous.", "_9117"),
                 0.0: ("Les objectifs ne précisent pas ce qui doit être atteint.", "_1989")}},
    {"id": "_7682", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Mesurabilité des objectifs",
     "ratings": {2.5: ("Chaque objectif est associé à un indicateur mesurable: nombre de leads, taux de conversion, trafic, portée, taux d'engagement, CPC, CPL, CPA, ventes ou inscriptions.", "_1719"),
                 2.0: ("Les objectifs ont des indicateurs de mesure, mais certains KPI peuvent être incomplets ou peu précis.", "_2543"),
                 1.0: ("Quelques indicateurs sont mentionnés, mais ils ne permettent pas vraiment d'évaluer la réussite de l'objectif", "_4551"),
                 0.0: ("Aucun KPI ou indicateur de mesure n'est associé aux objectifs", "_5917")}},
    {"id": "_5052", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Cible chiffrée des objectifs",
     "ratings": {2.5: ("Chaque objectif contient une valeur cible claire: atteindre 500 visites, générer 50 leads, obtenir 5% de conversion, réduire le CPL à 3 €, etc.", "_3385"),
                 2.0: ("Les principales cibles chiffrées sont présentes, même si certaines estimations peuvent être approximatives.", "_3375"),
                 1.0: ("Les objectifs utilisent des termes vagues comme 'augmenter', 'améliorer', 'développer', sans chiffre précis.", "_6215"),
                 0.0: ("Aucune cible chiffrée n'est indiquée.", "_9134")}},
    {"id": "_3498", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Horizon temporel",
     "ratings": {2.5: ("Chaque objectif précise une période ou une échéance", "_3339"),
                 2.0: ("Les objectifs ont une période globalement claire, mais tous ne sont pas parfaitement datés.", "_512"),
                 1.0: ("Le délai est vague", "_7606"),
                 0.0: ("Aucun délai n'est défini", "_465")}},
    {"id": "_7081", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Réalisme des objectifs",
     "ratings": {2.5: ("Les objectifs sont atteignables par rapport au projet, au budget, au délai, au niveau de départ, aux ressources disponibles et au contexte du marché.", "_5710"),
                 2.0: ("Les objectifs sont globalement réalistes, même si certaines estimations peuvent être discutées.", "_2709"),
                 1.0: ("Les objectifs semblent trop ambitieux ou trop faibles sans justification claire.", "_7204"),
                 0.0: ("Les objectifs sont irréalistes ou impossibles à évaluer.", "_4601")}},
    {"id": "_593", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Baseline ou point de départ",
     "ratings": {2.5: ("Le point de départ réel ou estimé: trafic actuel, communauté actuelle, absence de leads, taux actuel, budget disponible ou situation de départ. Cela permet de mesurer la progression.", "_7995"),
                 2.0: ("Une baseline est indiquée pour les objectifs principaux, même si elle est estimée.", "_1338"),
                 1.0: ("La baseline est vague ou incomplète.", "_1654"),
                 0.0: ("Aucun point de départ n'est indiqué.", "_9338")}},
    {"id": "_6346", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Formulation des OKR",
     "ratings": {2.5: ("Les OKR sont clairement structurés: un objectif qualitatif ambitieux est accompagné de résultats clés mesurables. On distingue bien l'Objective des Key Results.", "_3105"),
                 2.0: ("Les OKR sont présents et compréhensibles, même si certains Key Results peuvent être mieux formulés.", "_8596"),
                 1.0: ("Les OKR sont confus. L'apprenant mélange objectifs, tâches et résultats clés.", "_4151"),
                 0.0: ("Aucun OKR n'est présenté.", "_7236")}},
    {"id": "_8367", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Qualité de l'Objective dans l'OKR",
     "ratings": {2.5: ("L'Objective est clair, qualitatif, stratégique et orienté impact.", "_4544"),
                 2.0: ("L'Objective est clair et cohérent avec le projet, même s'il peut être plus ambitieux ou mieux formulé.", "_5118"),
                 1.0: ("L'Objective est vague, trop opérationnel ou ressemble à une tâche.", "_3607"),
                 0.0: ("Aucun Objective clair n'est formulé", "_8347")}},
    {"id": "_7502", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Qualité des Key Results",
     "ratings": {2.5: ("Les Key Results sont mesurables, chiffrés et vérifiables.", "_2760"),
                 2.0: ("Les Key Results sont mesurables et cohérents, même si certains manquent de précision.", "_3211"),
                 1.0: ("Les Key Results sont partiellement mesurables ou ressemblent à des actions à faire.", "_8030"),
                 0.0: ("Aucun Key Result mesurable n'est présenté.", "_6605")}},
    {"id": "_2568", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Cohérence entre SMART et OKR",
     "ratings": {2.5: ("Les objectifs SMART et les OKR sont alignés.", "_4415"),
                 2.0: ("Les SMART et OKR sont globalement cohérents, même si le lien entre les deux peut être renforcé", "_7258"),
                 1.0: ("Les SMART et les OKR existent, mais ils semblent déconnectés ou répétitifs.", "_1444"),
                 0.0: ("Aucun lien logique n'existe entre les objectifs SMART et les OKR.", "_6615")}},
    {"id": "_4771", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Priorisation des objectifs",
     "ratings": {2.5: ("L'apprenant distingue les objectifs principaux des objectifs secondaires.", "_5511"),
                 2.0: ("Les objectifs principaux sont identifiables, même si la priorisation reste simple.", "_4351"),
                 1.0: ("Tous les objectifs sont présentés au même niveau, sans ordre de priorité.", "_7839"),
                 0.0: ("Aucune priorisation n'est faite.", "_1674")}},
    {"id": "_6588", "section": "SOSTAC - Objectifs SMART & OKR", "name": "Qualité de présentation des objectifs",
     "ratings": {2.5: ("Les objectifs SMART et les OKR sont présentés dans un tableau clair avec: objectif, KPI, cible chiffrée, délai, baseline si possible, Objective et Key Results.", "_9721"),
                 2.0: ("La présentation est claire et compréhensible, même si elle peut être mieux structurée.", "_5726"),
                 1.0: ("La présentation est confuse ou désorganisée.", "_3069"),
                 0.0: ("Aucun support exploitable n'est fourni.", "_5556")}},
    # === SOSTAC - Stratégie (16 criteria) ===
    {"id": "_153", "section": "SOSTAC - Stratégie", "name": "Segmentation du marché",
     "ratings": {2.5: ("Le marché est découpé en segments clairs et pertinents selon plusieurs critères profil, besoins, comportements, budget, localisation, maturité digitale ou usage du produit/service", "_7618"),
                 2.0: ("Le marché est segmenté de manière compréhensible avec des groupes cohérents", "_779"),
                 1.0: ("La segmentation est présente, mais trop vague ou superficielle.", "_7181"),
                 0.0: ("Aucune segmentation du marché n'est proposée.", "_7652")}},
    {"id": "_41", "section": "SOSTAC - Stratégie", "name": "Critères de segmentation utilisés",
     "ratings": {2.5: ("Les critères utilisés sont clairement expliqués démographiques, géographiques, comportementaux, psychographiques, niveau de besoin, pouvoir d'achat ou fréquence d'usage", "_1034"),
                 2.0: ("Les critères de segmentation sont présents et globalement adaptés au projet.", "_8218"),
                 1.0: ("Les critères sont mentionnés, mais ils sont incomplets ou peu justifiés.", "_8932"),
                 0.0: ("Aucun critère de segmentation n'est indiqué.", "_7895")}},
    {"id": "_5323", "section": "SOSTAC - Stratégie", "name": "Identification des segments prioritaires",
     "ratings": {2.5: ("L'apprenant identifie clairement les segments les plus importants à viser en priorité et explique pourquoi ils sont plus stratégiques que les autres.", "_3675"),
                 2.0: ("Les segments prioritaires sont identifiés, même si la justification reste simple.", "_3980"),
                 1.0: ("Plusieurs segments sont listés, mais on ne comprend pas lesquels sont prioritaires", "_6722"),
                 0.0: ("Aucun segment prioritaire n'est identifié.", "_377")}},
    {"id": "_2781", "section": "SOSTAC - Stratégie", "name": "Cohérence entre segmentation et personas",
     "ratings": {2.5: ("Les segments sont cohérents avec les personas déjà créés. On voit clairement quel persona appartient à quel segment et pourquoi.", "_8600"),
                 2.0: ("Les segments sont globalement cohérents avec les personas, même si le lien pourrait être mieux expliqué", "_8765"),
                 1.0: ("Les personas et les segments existent, mais le lien entre les deux est faible ou confus.", "_1767"),
                 0.0: ("Aucun lien n'est fait entre segmentation et personas.", "_6885")}},
    {"id": "_4386", "section": "SOSTAC - Stratégie", "name": "Ciblage principal",
     "ratings": {2.5: ("La cible principale est clairement définie qui elle est, pourquoi elle est prioritaire, quel problème elle rencontre et pourquoi elle représente la meilleure opportunité pour le lancement.", "_1125"),
                 2.0: ("La cible principale est identifiée et cohérente avec le projet", "_1170"),
                 1.0: ("La cible principale est mentionnée, mais elle reste trop large ou insuffisamment justifiée.", "_7270"),
                 0.0: ("Aucune cible principale n'est définie.", "_5242")}},
    {"id": "_1542", "section": "SOSTAC - Stratégie", "name": "Ciblage secondaire",
     "ratings": {2.5: ("Une ou plusieurs cibles secondaires sont identifiées avec leur rôle futurs clients, prescripteurs, influenceurs, partenaires, utilisateurs occasionnels ou relais de communication.", "_6505"),
                 2.0: ("Une cible secondaire est identifiée et cohérente avec le projet", "_3756"),
                 1.0: ("La cible secondaire est évoquée, mais son rôle n'est pas clair", "_1859"),
                 0.0: ("Aucune cible secondaire n'est proposée alors qu'elle serait pertinente pour le projet", "_1317")}},
    {"id": "_3840", "section": "SOSTAC - Stratégie", "name": "Justification du choix de la cible",
     "ratings": {2.5: ("Le choix de la cible est justifié par des éléments concrets taille du segment, besoin fort, accessibilité digitale, capacité d'achat, urgence du problème, potentiel de conversion ou alignement avec l'offre.", "_2184"),
                 2.0: ("Le choix de la cible est justifié de manière cohérente, même si certaines preuves peuvent être renforcées.", "_9945"),
                 1.0: ("La justification est faible ou générale.", "_5399"),
                 0.0: ("Aucune justification du ciblage n'est donnée.", "_2")}},
    {"id": "_6587", "section": "SOSTAC - Stratégie", "name": "Positionnement choisi",
     "ratings": {2.5: ("Le positionnement est clairement formulé l'apprenant explique comment la marque veut être perçue par la cible par rapport aux concurrents.", "_4090"),
                 2.0: ("Le positionnement est présent et cohérent avec le projet, même s'il peut être plus différenciant", "_549"),
                 1.0: ("Le positionnement est vague ou générique.", "_8936"),
                 0.0: ("Aucun positionnement clair n'est défini.", "_6514")}},
    {"id": "_3147", "section": "SOSTAC - Stratégie", "name": "Différenciation par rapport aux concurrents",
     "ratings": {2.5: ("L'apprenant explique précisément ce qui différencie le projet prix, qualité, accessibilité, spécialisation, expérience client, innovation, proximité, rapidité, confiance ou service personnalisé.", "_4540"),
                 2.0: ("La différenciation est présente et compréhensible, même si elle peut être renforcée.", "_2571"),
                 1.0: ("La différenciation est faible ou ressemble à des promesses générales sans preuve", "_538"),
                 0.0: ("Aucune différenciation n'est identifiée.", "_3802")}},
    {"id": "_7138", "section": "SOSTAC - Stratégie", "name": "Cohérence entre cible et positionnement",
     "ratings": {2.5: ("Le positionnement répond clairement aux attentes, besoins, freins et motivations de la cible choisie.", "_9686"),
                 2.0: ("Le positionnement est globalement adapté à la cible.", "_218"),
                 1.0: ("Le positionnement existe, mais il n'est pas clairement relié aux attentes de la cible.", "_8320"),
                 0.0: ("Le positionnement n'a aucun lien logique avec la cible.", "_1696")}},
    {"id": "_662", "section": "SOSTAC - Stratégie", "name": "Formulation d'un énoncé de positionnement",
     "ratings": {2.5: ("L'énoncé de positionnement est formulé clairement en une phrase: pour quelle cible, quelle offre, quel bénéfice principal et quelle différence face aux alternatives.", "_898"),
                 2.0: ("L'énoncé est présent et compréhensible, même si il peut être plus précis ou plus fort.", "_2595"),
                 1.0: ("L'énoncé est incomplet ou ressemble à un slogan sans expliquer la cible, le bénéfice ou la différence.", "_9516"),
                 0.0: ("Aucun énoncé de positionnement n'est formulé.", "_2562")}},
    {"id": "_4155", "section": "SOSTAC - Stratégie", "name": "Mapping concurrentiel",
     "ratings": {2.5: ("L'apprenant propose un mapping ou une matrice simple pour visualiser la place du projet face aux concurrents selon deux critères pertinents", "_7647"),
                 2.0: ("Un mapping est présent et globalement cohérent, même si les axes peuvent être mieux justifiés", "_5116"),
                 1.0: ("Le mapping est peu clair, mal construit ou ne permet pas vraiment de comprendre le positionnement", "_6854"),
                 0.0: ("Aucun mapping concurrentiel n'est proposé.", "_207")}},
    {"id": "_7255", "section": "SOSTAC - Stratégie", "name": "Attractivité des segments",
     "ratings": {2.5: ("L'apprenant évalue l'attractivité des segments: taille, potentiel de croissance, accessibilité, rentabilité, niveau de concurrence et facilité de conversion.", "_1967"),
                 2.0: ("L'attractivité des principaux segments est analysée de manière simple.", "_9035"),
                 1.0: ("L'attractivité est évoquée, mais sans critères précis.", "_6355"),
                 0.0: ("Aucune analyse de l'attractivité des segments n'est faite", "_3428")}},
    {"id": "_8445", "section": "SOSTAC - Stratégie", "name": "Faisabilité du ciblage",
     "ratings": {2.5: ("L'apprenant montre que la cible choisie est réellement atteignable avec les ressources disponibles: budget, canaux, contenu, temps, compétences et outils.", "_2285"),
                 2.0: ("La cible semble atteignable et le choix est globalement réaliste.", "_2496"),
                 1.0: ("La cible choisie semble difficile à atteindre, mais l'apprenant ne l'explique pas", "_6674"),
                 0.0: ("Le ciblage est irréaliste ou impossible à exploiter.", "_4197")}},
    {"id": "_5149", "section": "SOSTAC - Stratégie", "name": "Clarté de la promesse associée au positionnement",
     "ratings": {2.5: ("La promesse est claire, crédible et orientée client. Elle exprime le bénéfice principal que la cible doit retenir.", "_9620"),
                 2.0: ("La promesse est présente et compréhensible, mais elle peut être plus forte ou plus spécifique.", "_4407"),
                 1.0: ("La promesse est vague, trop générale ou peu liée au positionnement", "_1781"),
                 0.0: ("Aucune promesse claire n'est formulée.", "_7208")}},
    {"id": "_3046", "section": "SOSTAC - Stratégie", "name": "Qualité de présentation de la partie stratégie",
     "ratings": {2.5: ("La partie est bien structurée: segmentation, ciblage et positionnement sont séparés, lisibles, logiques et faciles à évaluer.", "_226"),
                 2.0: ("La présentation est claire et compréhensible, même si elle peut être améliorée.", "_2418"),
                 1.0: ("La présentation est désorganisée ou difficile à suivre.", "_6695"),
                 0.0: ("Aucun support exploitable n'est fourni.", "_6395")}},
    # === SOSTAC - Tactiques (23 criteria) ===
    {"id": "_2529", "section": "SOSTAC - Tactiques", "name": "Choix des canaux marketing",
     "ratings": {2.5: ("Les canaux marketing sont clairement choisis et justifiés selon la cible, les objectifs SMART/OKR, le positionnement et le budget.", "_9278"),
                 2.0: ("Les canaux principaux sont choisis et cohérents avec le projet, mais la justification peut être plus approfondie.", "_4004"),
                 1.0: ("Plusieurs canaux sont cités, mais sans explication claire de leur utilité ou de leur lien avec la cible.", "_5035"),
                 0.0: ("Aucun canal marketing clair n'est choisi.", "_5606")}},
    {"id": "_2198", "section": "SOSTAC - Tactiques", "name": "Rôle de chaque canal",
     "ratings": {2.5: ("Chaque canal a un rôle défini: attirer, informer, rassurer, convertir, fidéliser ou relancer.", "_3409"),
                 2.0: ("Les rôles des principaux canaux sont indiqués, même si certains restent peu détaillés.", "_6737"),
                 1.0: ("Les canaux sont listés, mais leur rôle n'est pas clair.", "_9655"),
                 0.0: ("Aucun rôle n'est attribué aux canaux.", "_3457")}},
    {"id": "_6529", "section": "SOSTAC - Tactiques", "name": "Priorisation des canaux",
     "ratings": {2.5: ("Les canaux sont classés par priorité: canaux à lancer en premier, canaux secondaires et canaux à tester plus tard.", "_401"),
                 2.0: ("Les canaux prioritaires sont identifiables, même si la justification reste simple.", "_8708"),
                 1.0: ("Tous les canaux sont présentés au même niveau, sans ordre de priorité.", "_4659"),
                 0.0: ("Aucune priorisation des canaux n'est faite.", "_6645")}},
    {"id": "_3511", "section": "SOSTAC - Tactiques", "name": "Cohérence entre canaux et cible",
     "ratings": {2.5: ("Les canaux choisis correspondent aux habitudes digitales de la cible: plateformes utilisées, comportements de recherche, niveau de confiance, type de contenu consommé.", "_7069"),
                 2.0: ("Les canaux sont globalement adaptés à la cible.", "_7534"),
                 1.0: ("Les canaux semblent génériques et pourraient être utilisés pour n'importe quelle cible.", "_3289"),
                 0.0: ("Les canaux ne correspondent pas à la cible définie.", "_4776")}},
    {"id": "_741", "section": "SOSTAC - Tactiques", "name": "Acquisition - Attirer des prospects",
     "ratings": {2.5: ("L'apprenant explique clairement comment il va attirer de nouveaux prospects canaux utilisés, message d'entrée, contenu ou campagne, cible visée et KPI d'acquisition.", "_973"),
                 2.0: ("La logique d'acquisition est présente et cohérente, même si elle manque de précision.", "_8892"),
                 1.0: ("L'acquisition est mentionnée, mais sans action claire ni KPI.", "_6339"),
                 0.0: ("Aucune stratégie d'acquisition n'est proposée", "_1471")}},
    {"id": "_9818", "section": "SOSTAC - Tactiques", "name": "Activation - Faire passer à l'action",
     "ratings": {2.5: ("L'apprenant explique comment transformer un visiteur ou prospect en lead engagé landing page, formulaire, lead magnet, inscription, demande de contact, essai ou première interaction.", "_8845"),
                 2.0: ("La logique d'activation est claire, même si certains éléments peuvent être mieux détaillés.", "_8985"),
                 1.0: ("L'activation est évoquée, mais on ne comprend pas clairement quelle action l'utilisateur doit faire.", "_3136"),
                 0.0: ("Aucune action d'activation n'est prévue.", "_5218")}},
    {"id": "_4712", "section": "SOSTAC - Tactiques", "name": "Rétention - Maintenir l'intérêt",
     "ratings": {2.5: ("L'apprenant explique comment garder le contact avec les prospects ou clients: email, WhatsApp, contenu de suivi, relance, communauté, nurturing ou programme de fidélisation", "_2520"),
                 2.0: ("La logique de rétention est présente et cohérente.", "_5117"),
                 1.0: ("La rétention est mentionnée, mais sans mécanisme clair de suivi ou relance.", "_3043"),
                 0.0: ("Aucune action de rétention n'est proposée.", "_6584")}},
    {"id": "_8069", "section": "SOSTAC - Tactiques", "name": "Recommandation - Encourager le bouche-à-oreille",
     "ratings": {2.5: ("L'apprenant propose un mécanisme clair pour encourager la recommandation: parrainage, témoignages, avis clients, partage social, ambassadeurs, programme de référence ou UGC.", "_1415"),
                 2.0: ("Une logique de recommandation est présente, même si elle reste simple.", "_9315"),
                 1.0: ("La recommandation est évoquée, mais sans mécanisme concret", "_2124"),
                 0.0: ("Aucune action de recommandation n'est prévue.", "_6965")}},
    {"id": "_2955", "section": "SOSTAC - Tactiques", "name": "Revenu - Générer de la valeur business",
     "ratings": {2.5: ("L'apprenant explique comment les tactiques vont contribuer au revenu: vente, inscription payante, prise de rendez-vous, devis, abonnement, commande, conversion ou opportunité commerciale.", "_4832"),
                 2.0: ("Le lien entre tactiques et revenu est compréhensible, même s'il peut être mieux chiffré", "_6361"),
                 1.0: ("Le revenu est mentionné, mais le lien avec les actions marketing reste flou", "_247"),
                 0.0: ("Aucun lien n'est fait entre les tactiques et la génération de revenu.", "_8113")}},
    {"id": "_2180", "section": "SOSTAC - Tactiques", "name": "KPI par étape AAARRR",
     "ratings": {2.5: ("Chaque étape du funnel a au moins un KPI clair trafic, leads, taux d'activation, taux de rétention, nombre de recommandations, ventes, chiffre d'affaires ou taux de conversion.", "_873"),
                 2.0: ("Les KPI principaux du funnel sont présents, même si certains peuvent être mieux choisis", "_5680"),
                 1.0: ("Quelques KPI sont cités, mais ils ne couvrent pas correctement le funnel.", "_7457"),
                 0.0: ("Aucun KPI n'est défini pour le funnel.", "_5012")}},
    {"id": "_5963", "section": "SOSTAC - Tactiques", "name": "CRM & pipeline de suivi",
     "ratings": {2.5: ("L'apprenant prévoit un CRM ou une logique de suivi des prospects avec des statuts clairs nouveau lead, contacté, qualifié, opportunité, converti, perdu ou relancé", "_6993"),
                 2.0: ("Le pipeline CRM est présent et cohérent, même si les règles de passage peuvent être plus détaillées.", "_1625"),
                 1.0: ("Un CRM est mentionné, mais sans stages clairs ni logique de suivi.", "_2505"),
                 0.0: ("Aucun CRM ou pipeline de suivi n'est prévu.", "_8601")}},
    {"id": "_276", "section": "SOSTAC - Tactiques", "name": "Automation marketing",
     "ratings": {2.5: ("L'apprenant explique quelles actions seront automatisées: email de bienvenue, relance, qualification, scoring, notification, changement de statut CRM ou nurturing.", "_7062"),
                 2.0: ("L'automation est présente et cohérente, même si elle reste simple.", "_6655"),
                 1.0: ("L'automation est évoquée, mais sans scénario clair.", "_9106"),
                 0.0: ("Aucune automation n'est prévue.", "_9150")}},
    {"id": "_4227", "section": "SOSTAC - Tactiques", "name": "Segmentation CRM / Automation",
     "ratings": {2.5: ("Les contacts sont segmentés selon leur profil ou comportement: persona, source d'acquisition, niveau d'intérêt, score, statut CRM, action réalisée ou niveau de maturité", "_3489"),
                 2.0: ("Une segmentation simple est proposée et cohérente avec le projet.", "_2345"),
                 1.0: ("La segmentation est vague ou identique pour tous les contacts.", "_6995"),
                 0.0: ("Aucune segmentation n'est proposée.", "_3916")}},
    {"id": "_1182", "section": "SOSTAC - Tactiques", "name": "Stratégie de communication",
     "ratings": {2.5: ("L'apprenant définit une stratégie de communication claire objectifs de communication, messages clés, cible, canaux, formats, ton et intention des contenus.", "_3728"),
                 2.0: ("La stratégie de communication est présente et cohérente, mais certains éléments peuvent être mieux précisés.", "_425"),
                 1.0: ("La communication est abordée de manière vague, sans structure claire.", "_4146"),
                 0.0: ("Aucune stratégie de communication n'est définie.", "_8228")}},
    {"id": "_5884", "section": "SOSTAC - Tactiques", "name": "Piliers éditoriaux",
     "ratings": {2.5: ("L'apprenant définit 3 à 5 piliers éditoriaux cohérents avec la cible, le positionnement et les objectifs. Chaque pilier a une fonction claire.", "_7212"),
                 2.0: ("Les piliers éditoriaux sont présents et globalement cohérents.", "_1717"),
                 1.0: ("Les piliers sont vagues, trop nombreux, trop faibles ou peu reliés au projet.", "_2672"),
                 0.0: ("Aucun pilier éditorial n'est défini.", "_1347")}},
    {"id": "_9870", "section": "SOSTAC - Tactiques", "name": "Charte éditoriale",
     "ratings": {2.5: ("La charte éditoriale précise le ton, le style de langage, les types de messages, les mots à privilégier/éviter, la personnalité de la marque et les règles de communication.", "_5446"),
                 2.0: ("La charte éditoriale est présente et compréhensible, même si elle peut être plus détaillée.", "_940"),
                 1.0: ("Le ton est mentionné, mais il n'y a pas de vraie charte éditoriale exploitable.", "_9312"),
                 0.0: ("Aucune charte éditoriale n'est proposée.", "_460")}},
    {"id": "_8031", "section": "SOSTAC - Tactiques", "name": "Formats de contenus",
     "ratings": {2.5: ("Les formats sont clairement définis selon les canaux: posts, stories, reels, carrousels, vidéos courtes, articles, emails, lives, landing pages ou messages WhatsApp", "_9005"),
                 2.0: ("Les formats principaux sont définis et cohérents avec les canaux.", "_7905"),
                 1.0: ("Quelques formats sont cités, mais sans lien clair avec les canaux ou la cible.", "_2556"),
                 0.0: ("Aucun format de contenu n'est défini.", "_3107")}},
    {"id": "_4751", "section": "SOSTAC - Tactiques", "name": "Cohérence entre communication et positionnement",
     "ratings": {2.5: ("Les messages, le ton, les piliers et les formats renforcent clairement le positionnement choisi. La communication aide à construire l'image voulue.", "_4430"),
                 2.0: ("La communication est globalement cohérente avec le positionnement", "_7672"),
                 1.0: ("La communication semble partiellement déconnectée du positionnement.", "_8983"),
                 0.0: ("Aucun lien n'est fait entre communication et positionnement", "_6881")}},
    {"id": "_2911", "section": "SOSTAC - Tactiques", "name": "Articulation entre canaux, AAARRR et communication",
     "ratings": {2.5: ("L'apprenant montre comment les canaux, le funnel AAARRR, le CRM/automation et la communication fonctionnent ensemble dans un système cohérent", "_9545"),
                 2.0: ("Les blocs sont globalement cohérents entre eux, même si l'articulation peut être renforcée.", "_3683"),
                 1.0: ("Les blocs sont présents, mais ils semblent séparés et peu connectés.", "_2776"),
                 0.0: ("Aucune cohérence globale n'est visible.", "_2528")}},
    {"id": "_1784", "section": "SOSTAC - Tactiques", "name": "Plan de contenu indicatif",
     "ratings": {2.5: ("L'apprenant propose quelques exemples de contenus par pilier, avec objectif, canal, format et CTA.", "_1648"),
                 2.0: ("Des exemples de contenus sont proposés, même s'ils restent simples.", "_5903"),
                 1.0: ("Les exemples sont vagues ou peu reliés aux piliers.", "_1208"),
                 0.0: ("Aucun exemple de contenu n'est proposé.", "_5778")}},
    {"id": "_7126", "section": "SOSTAC - Tactiques", "name": "Scénarios CRM / Automation",
     "ratings": {2.5: ("L'apprenant propose des scénarios concrets après inscription, après téléchargement, après abandon, après demande de contact, après inactivité ou après conversion.", "_7571"),
                 2.0: ("Quelques scénarios simples sont présents et cohérents.", "_2033"),
                 1.0: ("Les scénarios sont mentionnés, mais restent flous ou incomplets.", "_6831"),
                 0.0: ("Aucun scénario CRM/automation n'est proposé", "_7432")}},
    {"id": "_2457", "section": "SOSTAC - Tactiques", "name": "Réalisme des tactiques",
     "ratings": {2.5: ("Les tactiques proposées sont réalistes par rapport au temps, au budget, aux outils, au niveau de maturité du projet et aux ressources disponibles.", "_6185"),
                 2.0: ("Les tactiques sont globalement réalistes, même si certaines estimations peuvent être ajustées.", "_4067"),
                 1.0: ("Certaines tactiques semblent difficiles à exécuter ou trop ambitieuses sans justification.", "_2057"),
                 0.0: ("Les tactiques sont irréalistes ou impossibles à appliquer.", "_179")}},
    {"id": "_7405", "section": "SOSTAC - Tactiques", "name": "Qualité de présentation des tactiques",
     "ratings": {2.5: ("La partie est claire et structurée canaux, AAARRR, CRM/automation et communication sont séparés, lisibles et faciles à évaluer", "_3381"),
                 2.0: ("La présentation est compréhensible, même si elle peut être mieux organisée.", "_3145"),
                 1.0: ("La présentation est désorganisée ou difficile à suivre.", "_315"),
                 0.0: ("Aucun support exploitable n'est fourni.", "_7435")}},
    # === SOSTAC - Actions (16 criteria) ===
    {"id": "_5981", "section": "SOSTAC - Actions", "name": "Feuille de route globale",
     "ratings": {2.5: ("La feuille de route présente clairement toutes les grandes étapes d'exécution: communication, contenus, site/landing page, acquisition, CRM, automation, tracking et analyse.", "_1298"),
                 2.0: ("La feuille de route contient les principales étapes d'exécution et permet de comprendre le déroulement général du projet", "_6350"),
                 1.0: ("La feuille de route est incomplète ou désorganisée.", "_6151"),
                 0.0: ("Aucune feuille de route n'est présentée.", "_2335")}},
    {"id": "_4317", "section": "SOSTAC - Actions", "name": "Définition précise des actions",
     "ratings": {2.5: ("Chaque action est formulée de manière concrète avec un verbe d'action clair.", "_9357"),
                 2.0: ("Les actions principales sont claires et compréhensibles, même si certaines restent encore un peu générales.", "_3137"),
                 1.0: ("Les actions sont vagues, par exemple 'faire du marketing'", "_8788"),
                 0.0: ("Aucune action concrète n'est définie.", "_729")}},
    {"id": "_8182", "section": "SOSTAC - Actions", "name": "Lien entre actions et tactiques",
     "ratings": {2.5: ("Chaque action correspond clairement à une tactique définie précédemment: canal marketing, AAARRR, CRM/automation ou stratégie de communication", "_7712"),
                 2.0: ("Les actions sont globalement reliées aux tactiques, même si certains liens pourraient être mieux explicités.", "_5120"),
                 1.0: ("Certaines actions semblent déconnectées des tactiques ou ajoutées sans logique claire.", "_8384"),
                 0.0: ("Aucun lien n'est visible entre les actions et les tactiques.", "_4411")}},
    {"id": "_8061", "section": "SOSTAC - Actions", "name": "Échéances des actions",
     "ratings": {2.5: ("Chaque action a une date, une période ou une deadline précise.", "_5947"),
                 2.0: ("Les principales actions ont des échéances globalement claires, même si certaines dates restent approximatives.", "_9627"),
                 1.0: ("Les échéances sont vagues", "_79"),
                 0.0: ("Aucune échéance n'est indiquée.", "_4952")}},
    {"id": "_8862", "section": "SOSTAC - Actions", "name": "Responsables des actions",
     "ratings": {2.5: ("Chaque action indique un responsable, même dans un projet individuel.", "_534"),
                 2.0: ("Les responsables principaux sont indiqués, même si certains rôles restent peu détaillés.", "_4125"),
                 1.0: ("Quelques responsables sont mentionnés, mais plusieurs actions restent sans personne responsable.", "_5068"),
                 0.0: ("Aucun responsable n'est indiqué.", "_9013")}},
    {"id": "_6896", "section": "SOSTAC - Actions", "name": "Livrables attendus par action",
     "ratings": {2.5: ("Chaque action précise le résultat attendu fichier, page publiée, calendrier éditorial, campagne configurée, séquence email, dashboard, capture d'écran, rapport ou visuel.", "_1508"),
                 2.0: ("Les livrables principaux sont indiqués et compréhensibles.", "_9385"),
                 1.0: ("Les actions sont listées, mais les résultats attendus ne sont pas toujours précisés.", "_6343"),
                 0.0: ("Aucun livrable attendu n'est associé aux actions.", "_3464")}},
    {"id": "_1422", "section": "SOSTAC - Actions", "name": "Budget par action ou canal",
     "ratings": {2.5: ("Le budget est détaillé par action ou par canal: création de contenu, publicité, outils, hébergement, domaine, email marketing, CRM, design, tracking ou production.", "_1115"),
                 2.0: ("Un budget est proposé pour les principaux canaux ou actions, même si certaines estimations restent approximatives.", "_649"),
                 1.0: ("Le budget est mentionné de manière globale, sans répartition claire par action ou canal", "_9957"),
                 0.0: ("Aucun budget n'est présenté.", "_2687")}},
    {"id": "_4276", "section": "SOSTAC - Actions", "name": "Cohérence du budget",
     "ratings": {2.5: ("Les montants proposés sont réalistes par rapport au projet, au marché, aux objectifs, aux canaux choisis et à la période d'exécution", "_1585"),
                 2.0: ("Le budget est globalement cohérent, même si quelques montants peuvent être discutés.", "_1303"),
                 1.0: ("Certains montants semblent irréalistes, trop faibles ou trop élevés, sans justification.", "_3711"),
                 0.0: ("Le budget est incohérent ou impossible à évaluer", "_9885")}},
    {"id": "_4068", "section": "SOSTAC - Actions", "name": "Priorisation des actions",
     "ratings": {2.5: ("Les actions sont classées par priorité: actions indispensables, actions secondaires, actions à tester ou actions à faire plus tard.", "_9019"),
                 2.0: ("Les actions principales sont identifiables comme prioritaires, même si la justification reste simple.", "_4290"),
                 1.0: ("Toutes les actions sont présentées au même niveau, sans indication de priorité.", "_5472"),
                 0.0: ("Aucune priorisation n'est faite.", "_1413")}},
    {"id": "_7314", "section": "SOSTAC - Actions", "name": "Cohérence chronologique",
     "ratings": {2.5: ("L'ordre des actions respecte une logique d'exécution.", "_1451"),
                 2.0: ("L'ordre des actions est globalement logique, même si quelques dépendances pourraient être mieux organisées", "_8282"),
                 1.0: ("L'ordre des actions est parfois incohérent ou difficile à suivre.", "_3203"),
                 0.0: ("Les actions sont présentées sans aucune logique chronologique.", "_9846")}},
    {"id": "_3298", "section": "SOSTAC - Actions", "name": "Identification des dépendances",
     "ratings": {2.5: ("L'apprenant identifie les actions qui dépendent d'autres actions.", "_2050"),
                 2.0: ("Certaines dépendances importantes sont identifiées", "_1566"),
                 1.0: ("Les dépendances sont peu visibles ou seulement implicites.", "_5081"),
                 0.0: ("Aucune dépendance entre les actions n'est identifiée.", "_5416")}},
    {"id": "_6245", "section": "SOSTAC - Actions", "name": "Ressources nécessaires",
     "ratings": {2.5: ("L'apprenant précise les ressources nécessaires pour exécuter les actions: outils, plateformes, compétences, contenus, visuels, accès aux comptes, budget, temps ou documents.", "_6172"),
                 2.0: ("Les principales ressources sont indiquées, même si elles peuvent être plus détaillées.", "_2872"),
                 1.0: ("Les ressources sont mentionnées de manière vague ou incomplète", "_8191"),
                 0.0: ("Aucune ressource nécessaire n'est indiquée", "_7920")}},
    {"id": "_8157", "section": "SOSTAC - Actions", "name": "Format de suivi du plan d'action",
     "ratings": {2.5: ("Le plan est présenté dans un format facile à suivre tableau, calendrier, roadmap, Gantt, Kanban ou planning opérationnel.", "_6326"),
                 2.0: ("Le plan est lisible et permet de suivre les actions, même si le format peut être amélioré.", "_2306"),
                 1.0: ("Le plan est difficile à suivre ou mal organisé", "_5507"),
                 0.0: ("Aucun format de suivi exploitable n'est fourni", "_1441")}},
    {"id": "_7239", "section": "SOSTAC - Actions", "name": "Réalisme opérationnel",
     "ratings": {2.5: ("Le plan d'action est faisable dans le temps disponible, avec les ressources, le budget et les compétences annoncées.", "_2533"),
                 2.0: ("Le plan est globalement réaliste, même si certaines actions peuvent être ajustées.", "_5983"),
                 1.0: ("Le plan semble trop ambitieux, trop flou ou difficile à exécuter dans les délais.", "_283"),
                 0.0: ("Le plan est irréaliste ou impossible à mettre en œuvre.", "_656")}},
    {"id": "_4583", "section": "SOSTAC - Actions", "name": "Indicateur de réussite par action",
     "ratings": {2.5: ("Pour les actions principales, l'apprenant indique comment savoir si l'action est terminée ou réussie.", "_1797"),
                 2.0: ("Des indicateurs de réussite sont indiqués pour les actions principales.", "_1035"),
                 1.0: ("Les indicateurs de réussite sont rares ou peu précis.", "_1410"),
                 0.0: ("Aucun indicateur de réussite n'est prévu.", "_8637")}},
    {"id": "_5409", "section": "SOSTAC - Actions", "name": "Qualité de présentation de la partie Actions",
     "ratings": {2.5: ("La partie Actions est claire, structurée et directement utilisable: action, responsable, échéance, budget, livrable, priorité et statut sont faciles à lire.", "_2358"),
                 2.0: ("La présentation est compréhensible, même si elle peut être mieux organisée.", "_2491"),
                 1.0: ("La présentation est désorganisée, trop chargée ou difficile à utiliser.", "_9705"),
                 0.0: ("Aucun support exploitable n'est fourni", "_4332")}},
    # === SOSTAC - Contrôle (18 criteria) ===
    {"id": "_5358", "section": "SOSTAC - Contrôle", "name": "Définition des indicateurs de succès",
     "ratings": {2.5: ("Les indicateurs de succès sont clairement définis et reliés aux objectifs SMART/OKR", "_6195"),
                 2.0: ("Les indicateurs principaux sont présents et cohérents avec les objectifs, même si certains peuvent être mieux précisés.", "_5820"),
                 1.0: ("Quelques indicateurs sont mentionnés, mais ils restent trop généraux", "_1660"),
                 0.0: ("Aucun indicateur de succès n'est défini", "_6276")}},
    {"id": "_3795", "section": "SOSTAC - Contrôle", "name": "Cohérence entre KPI et objectifs SMART/OKR",
     "ratings": {2.5: ("Chaque KPI permet de mesurer un objectif précis.", "_7660"),
                 2.0: ("Les KPI sont globalement liés aux objectifs, même si certains liens peuvent être mieux expliqués.", "_8353"),
                 1.0: ("Les KPI existent, mais ils semblent partiellement déconnectés des objectifs.", "_2374"),
                 0.0: ("Aucun lien n'est fait entre les KPI et les objectifs.", "_9956")}},
    {"id": "_5882", "section": "SOSTAC - Contrôle", "name": "Plan de tracking global",
     "ratings": {2.5: ("Le plan de tracking indique clairement ce qui doit être mesuré, sur quelles pages ou canaux, avec quels outils et pour quel objectif", "_5206"),
                 2.0: ("Le plan de tracking est présent et cohérent, même s'il manque quelques détails techniques.", "_9050"),
                 1.0: ("Le tracking est évoqué, mais sans plan clair.", "_648"),
                 0.0: ("Aucun plan de tracking n'est présenté.", "_133")}},
    {"id": "_7611", "section": "SOSTAC - Contrôle", "name": "Définition des événements GA4",
     "ratings": {2.5: ("Les événements GA4 sont clairement définis page_view, click_CTA, form_submit, generate_lead, scroll, purchase, sign_up ou autres événements pertinents selon le projet.", "_4223"),
                 2.0: ("Les événements principaux sont indiqués et cohérents avec le parcours utilisateur.", "_6616"),
                 1.0: ("Quelques événements sont mentionnés, mais ils sont incomplets ou mal reliés aux actions importantes du site.", "_1431"),
                 0.0: ("Aucun événement GA4 n'est défini.", "_8341")}},
    {"id": "_275", "section": "SOSTAC - Contrôle", "name": "Définition des conversions",
     "ratings": {2.5: ("Les conversions principales sont clairement identifiées formulaire rempli, demande de devis, achat, inscription, appel, téléchargement, réservation, ajout au panier ou prise de rendez-vous.", "_4163"),
                 2.0: ("Les conversions principales sont présentes et cohérentes avec le projet.", "_8265"),
                 1.0: ("Les conversions sont évoquées, mais elles ne sont pas clairement définies ou mesurables.", "_1913"),
                 0.0: ("Aucune conversion n'est définie.", "_9153")}},
    {"id": "_4072", "section": "SOSTAC - Contrôle", "name": "Installation ou prévision des pixels",
     "ratings": {2.5: ("Les pixels nécessaires sont identifiés selon les canaux utilisés: Meta Pixel, Google Ads tag, TikTok Pixel, Linkedin Insight Tag ou autre. Leur rôle est expliqué.", "_1604"),
                 2.0: ("Les pixels principaux sont indiqués et cohérents avec les campagnes prévues.", "_9994"),
                 1.0: ("Les pixels sont mentionnés, mais sans expliquer lesquels utiliser ni pourquoi.", "_9339"),
                 0.0: ("Aucun pixel ou tag publicitaire n'est prévu.", "_3206")}},
    {"id": "_826", "section": "SOSTAC - Contrôle", "name": "Utilisation des UTM",
     "ratings": {2.5: ("L'apprenant prévoit une logique UTM claire pour suivre les campagnes: source, medium, campaign, content ou term.", "_2279"),
                 2.0: ("Les UTM sont prévus et globalement cohérents, même si la nomenclature peut être améliorée.", "_37"),
                 1.0: ("Les UTM sont mentionnés, mais sans structure claire ni exemple exploitable.", "_6401"),
                 0.0: ("Aucun UTM n'est prévu.", "_844")}},
    {"id": "_356", "section": "SOSTAC - Contrôle", "name": "Tableau de bord KPI",
     "ratings": {2.5: ("Le tableau de bord regroupe les KPI importants par objectif ou canal: acquisition, activation, conversion, rétention, revenu.", "_542"),
                 2.0: ("Un tableau de bord est proposé avec les principaux KPI, même s'il reste simple.", "_2850"),
                 1.0: ("Le tableau de bord est incomplet, désorganisé ou ne permet pas vraiment de piloter la stratégie.", "_8913"),
                 0.0: ("Aucun tableau de bord KPI n'est proposé.", "_7045")}},
    {"id": "_5213", "section": "SOSTAC - Contrôle", "name": "Sources de données du tableau de bord",
     "ratings": {2.5: ("Les sources de données sont clairement indiquées: GA4, Google Search Console, Meta Ads, Google Ads, CRM, email marketing, site web, formulaire ou outil d'automation.", "_2668"),
                 2.0: ("Les principales sources de données sont identifiées.", "_8565"),
                 1.0: ("Les sources sont évoquées, mais de manière incomplète ou peu claire.", "_440"),
                 0.0: ("Aucune source de données n'est indiquée.", "_314")}},
    {"id": "_615", "section": "SOSTAC - Contrôle", "name": "Fréquence de suivi",
     "ratings": {2.5: ("L'apprenant définit à quelle fréquence les performances seront suivies: quotidiennement pendant les campagnes, chaque semaine, chaque mois ou après chaque phase importante.", "_8411"),
                 2.0: ("Une fréquence de suivi est indiquée et globalement cohérente.", "_9958"),
                 1.0: ("La fréquence est vague, par exemple 'régulièrement', sans rythme précis.", "_3379"),
                 0.0: ("Aucune fréquence de suivi n'est définie.", "_7371")}},
    {"id": "_2019", "section": "SOSTAC - Contrôle", "name": "Méthode d'analyse des résultats",
     "ratings": {2.5: ("L'apprenant explique comment les résultats seront analysés: comparaison avec les objectifs, lecture des écarts, identification des meilleurs canaux, analyse des coûts et repérage des points de blocage.", "_4931"),
                 2.0: ("Une méthode d'analyse est présente, même si elle reste simple.", "_6486"),
                 1.0: ("L'analyse est évoquée, mais sans méthode claire.", "_6004"),
                 0.0: ("Aucune méthode d'analyse n'est proposée.", "_5428")}},
    {"id": "_3537", "section": "SOSTAC - Contrôle", "name": "Plan d'optimisation",
     "ratings": {2.5: ("L'apprenant prévoit quoi faire selon les résultats ajuster le budget, modifier les audiences, changer les messages, améliorer la landing page, tester un nouveau canal ou corriger le tracking.", "_735"),
                 2.0: ("Des actions d'optimisation sont proposées et cohérentes avec les KPI.", "_1341"),
                 1.0: ("Les optimisations sont vagues, par exemple 'améliorer la campagne' sans préciser comment.", "_9275"),
                 0.0: ("Aucun plan d'optimisation n'est prévu.", "_9488")}},
    {"id": "_3924", "section": "SOSTAC - Contrôle", "name": "Seuils d'alerte",
     "ratings": {2.5: ("L'apprenant définit des seuils qui indiquent qu'une performance est problématique: CPL trop élevé, CTR trop faible, taux de conversion faible, trafic insuffisant, taux de rebond élevé ou emails peu ouverts.", "_3743"),
                 2.0: ("Des seuils d'alerte sont indiqués pour les KPI principaux.", "_7201"),
                 1.0: ("Les seuils sont évoqués, mais ils restent peu précis ou incomplets.", "_5662"),
                 0.0: ("Aucun seuil d'alerte n'est défini.", "_8926")}},
    {"id": "_3839", "section": "SOSTAC - Contrôle", "name": "Plan d'A/B testing",
     "ratings": {2.5: ("L'apprenant prévoit des tests clairs: tester deux messages, deux visuels, deux audiences, deux CTA, deux objets d'email ou deux versions de landing page, avec un KPI de comparaison.", "_9986"),
                 2.0: ("Un plan de test simple est proposé et cohérent avec les objectifs.", "_8766"),
                 1.0: ("L'A/B testing est mentionné, mais sans préciser ce qui sera testé ni comment mesurer le résultat", "_766"),
                 0.0: ("Aucun test A/B n'est prévu.", "_2996")}},
    {"id": "_5058", "section": "SOSTAC - Contrôle", "name": "Nomenclature de tracking",
     "ratings": {2.5: ("L'apprenant propose une convention claire de nommage pour les campagnes, UTM, événements ou audiences afin de faciliter le suivi et éviter la confusion.", "_855"),
                 2.0: ("Une logique de nommage est présente, même si elle peut être améliorée.", "_5616"),
                 1.0: ("Le nommage est évoqué, mais sans structure claire.", "_9590"),
                 0.0: ("Aucune nomenclature n'est prévue.", "_5818")}},
    {"id": "_9270", "section": "SOSTAC - Contrôle", "name": "Responsabilité du suivi",
     "ratings": {2.5: ("L'apprenant précise qui suit les performances et qui prend les décisions d'optimisation consultant, media buyer, community manager, responsable CRM ou autre rôle simulé.", "_3890"),
                 2.0: ("Le responsable du suivi est indiqué pour les principales analyses.", "_7589"),
                 1.0: ("Le suivi est prévu, mais sans personne ou rôle clairement responsable.", "_792"),
                 0.0: ("Aucun responsable du suivi n'est indiqué.", "_5129")}},
    {"id": "_1286", "section": "SOSTAC - Contrôle", "name": "Reporting final",
     "ratings": {2.5: ("L'apprenant prévoit un format de reporting final résumé des résultats, KPI atteints/non atteints, écarts, enseignements, recommandations et prochaines actions.", "_8984"),
                 2.0: ("Le reporting final est prévu, même si sa structure peut être plus détaillée.", "_9065"),
                 1.0: ("Le reporting est mentionné, mais sans préciser ce qu'il contiendra.", "_5889"),
                 0.0: ("Aucun reporting final n'est prévu.", "_9302")}},
    {"id": "_8268", "section": "SOSTAC - Contrôle", "name": "Qualité de présentation de la partie Contrôle",
     "ratings": {2.5: ("La partie Contrôle est claire, structurée et directement exploitable: KPI, outils, événements, conversions, dashboard, fréquence, optimisation et reporting sont faciles à lire.", "_9360"),
                 2.0: ("La présentation est compréhensible, même si elle peut être mieux organisée.", "_2054"),
                 1.0: ("La présentation est confuse, désorganisée ou difficile à utiliser.", "_6796"),
                 0.0: ("Aucun support exploitable n'est fourni.", "_5260")}},
]

assert len(RUBRIC_CRITERIA) == 137, f"Expected 137 criteria, got {len(RUBRIC_CRITERIA)}"


def build_evaluation_prompt(student_id: str, content: str, word_count: int, extracted_files: list) -> str:
    """Build the prompt for evaluating a student's work against the rubric."""
    
    rubric_summary = ""
    current_section = None
    for i, crit in enumerate(RUBRIC_CRITERIA):
        if crit["section"] != current_section:
            current_section = crit["section"]
            rubric_summary += f"\n## {current_section}\n"
        rubric_summary += f"Critère #{i+1} [{crit['id']}]: {crit['name']}\n"
        for pts, (desc, _) in sorted(crit["ratings"].items(), reverse=True):
            rubric_summary += f"  {pts}pts: {desc}\n"
        rubric_summary += "\n"
    
    files_list = "\n".join(f"- {f}" for f in extracted_files) if extracted_files else "- (fichiers non listés)"
    
    return f"""Tu es un formateur expert en marketing digital qui évalue le chef-d'œuvre d'un apprenant d'une école de formation au numérique (Kadea Academy, Kinshasa).

## Contexte
- Apprenant ID: {student_id}
- Documents soumis ({word_count} mots extraits) :
{files_list}
- Points possibles: 342.5 pts (137 critères × max 2.5 pts)

## Grille d'évaluation (137 critères)
{rubric_summary}

## Travail de l'apprenant (contenu extrait des PDF)
---BEGIN STUDENT WORK---
{content[:25000]}
---END STUDENT WORK---

## Instructions d'évaluation
Pour CHAQUE critère, tu dois:
1. Attribuer une note parmi: 2.5, 2.0, 1.0, ou 0.0 pts UNIQUEMENT
2. Rédiger un commentaire en français de 1-3 phrases expliquant la note et ce qui manque/est bien

Sois équitable mais rigoureux. Si l'information n'est pas dans les documents, attribue 0.0.
Si les données sont présentes mais incomplètes/vagues, attribue 1.0 ou 2.0 selon le détail.

Réponds UNIQUEMENT avec un JSON valide de ce format exact (aucun texte avant ou après):
{{
  "student_id": "{student_id}",
  "total_points": <somme de tous les points>,
  "evaluations": {{
    "<criterion_id>": {{
      "points": <2.5|2.0|1.0|0.0>,
      "rating_id": "<rating_id_matching_the_points>",
      "comment": "<commentaire en français>"
    }},
    ...
  }}
}}

Inclus TOUS les 137 critères dans le JSON (de _9714 jusqu'à _8268).
"""


def already_evaluated(student_id: str) -> bool:
    path = EVALUATIONS_DIR / f"evaluation_{student_id}.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        return "evaluations" in data and len(data["evaluations"]) == 137
    except Exception:
        return False


def evaluate_with_claude(prompt: str, api_key: str) -> dict:
    """Call Claude API to evaluate a student."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    # Extract JSON if wrapped in markdown code block
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def evaluate_student(student_id: str, api_key: str, dry_run: bool = False, force: bool = False) -> dict | None:
    """Load student content and evaluate against rubric."""
    text_path = STUDENT_TEXTS_DIR / f"student_{student_id}.json"
    if not text_path.exists():
        print(f"ERROR: No extracted content for student {student_id}")
        return None
    
    data = json.loads(text_path.read_text())
    if not data.get("content"):
        print(f"ERROR: Student {student_id} has no content (error: {data.get('error')})")
        return None
    
    if not force and already_evaluated(student_id):
        print(f"Student {student_id}: already evaluated, skipping")
        path = EVALUATIONS_DIR / f"evaluation_{student_id}.json"
        return json.loads(path.read_text())
    
    content = data["content"]
    word_count = data.get("word_count", 0)
    extracted_files = data.get("extracted_files", data.get("all_files", []))
    
    print(f"Evaluating student {student_id} ({word_count} words from {len(extracted_files)} files)...")
    
    prompt = build_evaluation_prompt(student_id, content, word_count, extracted_files)
    
    if dry_run:
        print(f"\n=== PROMPT PREVIEW (first 3000 chars) ===")
        print(prompt[:3000])
        print("...")
        return None
    
    result = evaluate_with_claude(prompt, api_key)
    
    # Validate
    evals = result.get("evaluations", {})
    if len(evals) < 130:
        print(f"WARNING: Only got {len(evals)} evaluations (expected 137)")
    
    total = sum(v["points"] for v in evals.values())
    result["total_points"] = round(total, 1)
    
    EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVALUATIONS_DIR / f"evaluation_{student_id}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  -> Saved to {out_path} (total: {result['total_points']}/342.5 pts)")
    
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--student-id", help="Single student ID to evaluate")
    parser.add_argument("--all", action="store_true", help="Evaluate all students with extracted content")
    parser.add_argument("--batch", type=int, default=5, help="Number of students to evaluate in --all mode")
    parser.add_argument("--dry-run", action="store_true", help="Show prompt without calling API")
    parser.add_argument("--force", action="store_true", help="Re-evaluate already-done students")
    parser.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    args = parser.parse_args()
    
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: No Anthropic API key. Use --api-key or set ANTHROPIC_API_KEY env var")
        sys.exit(1)
    
    if args.student_id:
        evaluate_student(args.student_id, api_key, dry_run=args.dry_run, force=args.force)
    elif args.all:
        text_files = sorted(STUDENT_TEXTS_DIR.glob("student_*.json"))
        evaluated = 0
        for tf in text_files:
            sid = tf.stem.replace("student_", "")
            data = json.loads(tf.read_text())
            if not data.get("content"):
                continue
            if not args.force and already_evaluated(sid):
                continue
            result = evaluate_student(sid, api_key, dry_run=args.dry_run, force=args.force)
            if result:
                evaluated += 1
            if evaluated >= args.batch:
                break
        print(f"\nDone: evaluated {evaluated} students")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
