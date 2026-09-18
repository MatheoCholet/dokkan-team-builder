import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import uuid
from google import genai
from google.genai import types

# ==========================================
# CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(
    page_title="Dokkan Team Builder",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# GESTION D'ÉTAT & NORMALISATION (SANS BOGUE)
# ==========================================
def normaliser_personnage(item: dict) -> dict:
    """Standardise les clés JSON pour accepter différentes nomenclatures et assigne un UUID unique."""
    nom = item.get("nom", item.get("name", "Personnage inconnu"))
    doublons = item.get("doublons", item.get("doublon", 0))
    rarete = item.get("rarete", item.get("rarity", "SSR"))
    type_perso = item.get("type", "Inconnu")
    z_tur = item.get("z_tur", item.get("ztur", False))
    url = item.get("url", item.get("lien", ""))
    
    # Nettoyage de base du nom
    nom = " ".join(str(nom).split())
    
    return {
        "_id": str(uuid.uuid4()),
        "nom": nom,
        "type": type_perso,
        "rarete": rarete,
        "doublons": int(doublons) if str(doublons).isdigit() else 0,
        "z_tur": bool(z_tur),
        "url": url
    }

# Initialisation de la Box en mémoire
if 'box' not in st.session_state:
    st.session_state.box = []

def maj_doublons(char_id: str, widget_key: str):
    """Callback sécurisé pour mettre à jour les doublons sans KeyError de Streamlit."""
    for char in st.session_state.box:
        if char["_id"] == char_id:
            char["doublons"] = st.session_state[widget_key]
            break

def supprimer_personnage(char_id: str):
    """Supprime un personnage de manière sécurisée en filtrant par son UUID."""
    st.session_state.box = [c for c in st.session_state.box if c["_id"] != char_id]

# ==========================================
# SCRAPING AUTO-ADAPTATIF & RÉSILIENT
# ==========================================
@st.cache_data(show_spinner=False, ttl=86400)
def extraire_texte_brut(url: str) -> str:
    """Récupère uniquement le texte brut de la page avec protection Anti-Bot."""
    if not url or "dbz-dokkanbattle.com" not in url:
        return ""
    
    try:
        # Contournement Anti-Bot obligatoire
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nettoyage des balises invisibles ou parasites
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.extract()
            
        # Extraction du texte brut avec espacement pour éviter les mots fusionnés
        texte = soup.get_text(separator=' ', strip=True)
        return texte[:8000] # Limite prudente pour le contexte LLM
    except Exception as e:
        return f"Erreur d'extraction : {str(e)}"

@st.cache_data(show_spinner=False, ttl=86400)
def structurer_donnees_llm(texte_brut: str, type_donnee: str, api_key: str) -> str:
    """Utilise Gemini pour parser le texte brut et renvoyer un JSON validé et nettoyé."""
    if not texte_brut or not api_key or "Erreur d'extraction" in texte_brut:
        return "{}"

    try:
        client = genai.Client(api_key=api_key)
        
        # Adaptation dynamique du prompt selon la cible (Carte vs Boss)
        if type_donnee == "carte":
            instruction = (
                "Tu es un extracteur de données strict. Analyse ce texte brut de Dokkan Battle "
                "et réponds UNIQUEMENT en format JSON avec les clés exactes suivantes : 'leader_skill', "
                "'aptitude_passive' (incluant garde, esquive, réduction, stack), 'liens', et 'statistiques_max' "
                "(incluant Z-TUR ou Super Z-TUR si mentionné). Ne rajoute aucun commentaire."
            )
        else:
            instruction = (
                "Tu es un extracteur de données strict. Analyse ce texte brut d'événement Dokkan Battle "
                "et réponds UNIQUEMENT en format JSON avec les clés exactes suivantes : 'type_elementaire', "
                "'immunites' (stun, blocage d'attaque spéciale), 'attaques_de_zone' et 'mecaniques_speciales' (annulation d'esquive, etc.). "
                "Ne rajoute aucun commentaire."
            )

        # Appel API avec Modèle exigé et contrainte JSON native
        reponse = client.models.generate_content(
            model='gemini-3.1-pro-preview',
            contents=texte_brut,
            config=types.GenerateContentConfig(
                system_instruction=instruction,
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        # Nettoyage strict des balises Markdown éventuelles avant de parser le JSON
        clean_json_str = reponse.text.replace("```json", "").replace("```", "").strip()
        
        # Validation Python absolue via json.loads()
        try:
            parsed_json = json.loads(clean_json_str)
            return json.dumps(parsed_json, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # En cas de structure récalcitrante, on renvoie la chaîne nettoyée par défaut
            return clean_json_str
            
    except Exception:
        return '{"erreur": "Impossible de structurer les données avec l\'IA."}'

# ==========================================
# BARRE LATÉRALE : SÉCURITÉ ET DONNÉES
# ==========================================
st.sidebar.title("⚙️ Paramètres")

# Sécurité Absolue : Masquage total de la clé
api_key = st.secrets.get("GEMINI_API_KEY", None)

if api_key:
    st.sidebar.success("🟢 Service IA connecté")
else:
    api_key = st.sidebar.text_input(
        "Clé API Gemini", 
        type="password",
        help="Votre clé ne sera jamais stockée publiquement ni affichée en clair."
    )

st.sidebar.divider()
st.sidebar.header("📦 Import / Export de la Box")

fichier_upload = st.sidebar.file_uploader("Importer une box (.json)", type=["json"])
if fichier_upload is not None:
    try:
        data = json.load(fichier_upload)
        if isinstance(data, list):
            st.session_state.box = [normaliser_personnage(item) for item in data]
            st.sidebar.success("✅ Box importée et normalisée avec succès !")
        else:
            st.sidebar.error("❌ Format JSON invalide (une liste est attendue).")
    except Exception:
        st.sidebar.error("❌ Erreur de décodage du fichier JSON.")

if st.session_state.box:
    # Exclure l'_id interne avant l'export pour garder un fichier vierge
    box_export = [{k: v for k, v in c.items() if k != "_id"} for c in st.session_state.box]
    box_json_str = json.dumps(box_export, indent=4, ensure_ascii=False)
    st.sidebar.download_button(
        label="📥 Exporter ma Box",
        data=box_json_str,
        file_name="dokkan_box.json",
        mime="application/json",
        use_container_width=True
    )

# ==========================================
# INTERFACE PRINCIPALE (ONGLETS)
# ==========================================
st.title("🐉 Dokkan Team Builder")
st.markdown("La stratégie à l'état pur. L'IA analyse les données en temps réel pour former l'équipe parfaite.")

onglet_box, onglet_event, onglet_analyse = st.tabs(["🛡️ Ma Box", "🎯 Boss & Événement", "🧠 Génération d'Équipe"])

# ------------------------------------------
# ONGLET 1 : GESTION DE LA BOX
# ------------------------------------------
with onglet_box:
    st.subheader("Ajouter un personnage")
    
    with st.form("ajout_perso_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nom_perso = st.text_input("Nom du personnage (ex: Son Goku Ultra Instinct)")
        with col2:
            url_perso = st.text_input("URL dbz-dokkanbattle.com (Indispensable pour l'auto-analyse)")
            
        c_type, c_rar, c_dup, c_ztur = st.columns(4)
        with c_type:
            type_perso = st.selectbox("Type", ["AGI", "TEC", "INT", "PUI", "END"])
        with c_rar:
            rarete_perso = st.selectbox("Rareté actuelle", ["SSR", "UR", "LR"])
        with c_dup:
            doublons_perso = st.number_input("Doublons", min_value=0, max_value=4, step=1)
        with c_ztur:
            st.write("") # Alignement vertical
            ztur_perso = st.checkbox("Possède un Z-TUR / Super Z-TUR ?")
            
        if st.form_submit_button("➕ Ajouter à la Box"):
            if nom_perso.strip():
                nouvel_item = {
                    "nom": nom_perso.strip(),
                    "url": url_perso.strip(),
                    "type": type_perso,
                    "rarete": rarete_perso,
                    "doublons": doublons_perso,
                    "z_tur": ztur_perso
                }
                st.session_state.box.append(normaliser_personnage(nouvel_item))
                st.success(f"✅ {nom_perso.strip()} a été ajouté !")
                st.rerun()
            else:
                st.error("⚠️ Le nom du personnage est requis.")

    st.divider()
    st.subheader(f"Inventaire ({len(st.session_state.box)} cartes disponibles)")
    
    if st.session_state.box:
        for perso in st.session_state.box:
            c_nom, c_infos, c_doublon, c_action = st.columns([4, 3, 2, 1])
            
            lien = f" [🔗]({perso['url']})" if perso.get('url') else ""
            c_nom.markdown(f"**{perso['nom']}**{lien}")
            
            ztur_txt = " | Z-TUR ✅" if perso['z_tur'] else ""
            c_infos.markdown(f"{perso['type']} | {perso['rarete']}{ztur_txt}")
            
            cle_widget = f"doublon_{perso['_id']}"
            c_doublon.selectbox(
                "Doublons",
                options=[0, 1, 2, 3, 4],
                index=perso['doublons'],
                key=cle_widget,
                on_change=maj_doublons,
                args=(perso['_id'], cle_widget),
                label_visibility="collapsed"
            )
            
            if c_action.button("🗑️", key=f"del_{perso['_id']}"):
                supprimer_personnage(perso['_id'])
                st.rerun()
    else:
        st.info("La box est vide. Importez un fichier JSON ou ajoutez des cartes manuellement.")

# ------------------------------------------
# ONGLET 2 : LE BOSS (SCRAPING INTELLIGENT)
# ------------------------------------------
with onglet_event:
    st.subheader("Configuration et Analyse de l'Événement")
    
    nom_boss = st.text_input("Nom de l'événement (ex: Red Zone Broly, Combat de l'achèvement)")
    url_boss = st.text_input("URL dbz-dokkanbattle.com du boss (Optionnel mais recommandé)")
    details_manuels = st.text_area("Détails supplémentaires ou notes manuelles", height=100)
    
    st.session_state.nom_boss = nom_boss
    
    if st.button("🔍 Extraire les mécaniques du boss via l'URL", type="secondary"):
        if not api_key:
            st.error("⚠️ Clé API Gemini requise pour extraire les données.")
        elif not url_boss:
            st.error("⚠️ Veuillez renseigner une URL valide.")
        else:
            with st.spinner("Extraction de la page et génération du profil du boss par l'IA..."):
                texte_boss_brut = extraire_texte_brut(url_boss)
                donnees_boss_json = structurer_donnees_llm(texte_boss_brut, "boss", api_key)
                st.session_state.details_boss_auto = donnees_boss_json
                
                if "erreur" in donnees_boss_json.lower():
                    st.error("❌ Échec de l'analyse du boss. L'URL est-elle correcte ?")
                else:
                    st.success("✅ Mécaniques du boss extraites avec succès.")
                    st.code(donnees_boss_json, language="json")
                
    st.session_state.details_manuels = details_manuels

# ------------------------------------------
# ONGLET 3 : GÉNÉRATION D'ÉQUIPE
# ------------------------------------------
with onglet_analyse:
    st.subheader("Génération Stratégique de l'Équipe")
    
    if st.button("🚀 Créer l'équipe optimale", type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ Clé API Gemini manquante. Veuillez vérifier les paramètres.")
        elif len(st.session_state.box) < 6:
            st.error("⚠️ Il faut au minimum 6 cartes dans la box pour concevoir une équipe.")
        elif not st.session_state.get('nom_boss'):
            st.error("⚠️ Veuillez renseigner le nom du Boss dans l'onglet 'Boss & Événement'.")
        else:
            barre_progression = st.progress(0)
            texte_statut = st.empty()
            
            try:
                # 1. Compilation des données brutes de la box
                contexte_box = ""
                total_persos = len(st.session_state.box)
                
                for index, perso in enumerate(st.session_state.box):
                    texte_statut.write(f"Scraping et analyse de la carte : {perso['nom']} ({index+1}/{total_persos})...")
                    barre_progression.progress((index + 1) / total_persos)
                    
                    contexte_box += f"\n### Personnage de la Box : {perso['nom']}\n"
                    contexte_box += f"- Attributs bruts : Type {perso['type']}, Rareté possédée : {perso['rarete']}, Doublons : {perso['doublons']}\n"
                    
                    if perso.get('url'):
                        texte_carte_brut = extraire_texte_brut(perso['url'])
                        donnees_carte_json = structurer_donnees_llm(texte_carte_brut, "carte", api_key)
                        contexte_box += f"- Kit de compétences (Extrait du site) : {donnees_carte_json}\n"
                    else:
                        contexte_box += "- (Aucune URL. Utilise ta propre base de données interne pour cette unité.)\n"

                texte_statut.write("Génération de l'équipe avec Gemini 3.1 Pro Preview...")

                # 2. Règles Métiers Strictes pour l'IA
                instructions = (
                    "Tu es le meilleur théorycrafteur mondial de Dragon Ball Z: Dokkan Battle.\n"
                    "RÈGLES ABSOLUES ET IMPÉRATIVES :\n"
                    "1. LANGUE : Toutes tes explications et ton formatage DOIVENT être 100% en français.\n"
                    "2. EXCLUSIVITÉ DE LA BOX : Sélectionne EXACTEMENT 6 personnages (1 Leader, 5 Sous-unités) "
                    "UNIQUEMENT parmi l'inventaire fourni. Ne propose jamais de cartes absentes de la box en sous-unités. "
                    "Seul le 7ème personnage ('Ami Leader') peut être extérieur.\n"
                    "3. ÉVALUATION AU PLEIN POTENTIEL : Si une carte est notée 'SSR' ou 'UR' dans la box mais possède un éveil LR ou un Z-TUR "
                    "dans les données du JSON extrait, tu DOIS l'évaluer selon ses statistiques et son passif à son STADE MAXIMAL "
                    "(UR, LR, Z-TUR ou Super Z-TUR). Ne juge jamais une carte sur sa rareté SSR initiale. "
                    "Si tu intègres une telle carte, ajoute OBLIGATOIREMENT cette mention à côté de son nom : "
                    "'⚠️ À éveiller en UR/LR / Z-TUR pour ce combat'.\n"
                    "4. STRATÉGIE FONDÉE SUR LES DONNÉES : Appuie tes décisions de survie (Garde, Réduction, Esquive) sur le JSON des cartes et du boss fourni.\n\n"
                    "FORMAT ATTENDU (Markdown) :\n"
                    "🏆 **Leader de l'équipe** (et son bonus Leader Skill)\n"
                    "👥 **Membres de l'équipe** (les 5 cartes avec mention d'éveil si nécessaire)\n"
                    "🤝 **Ami Leader recommandé**\n"
                    "🔄 **Rotations Optimisées** (Rotation 1 : Slot 1 et 2 | Rotation 2 : Slot 1 et 2)\n"
                    "🎈 **Unités Flottantes** (Les 3 personnages en Slot 3)\n"
                    "📜 **Stratégie Détaillée** (Comment survivre, rotations, objets de soutien)."
                )

                # 3. Prompt Final
                infos_boss_auto = st.session_state.get('details_boss_auto', "Non extraites via l'URL.")
                details_manuels = st.session_state.get('details_manuels', "Aucune précision manuelle.")
                
                prompt_utilisateur = f"""
                **Cible à abattre :** {st.session_state.nom_boss}
                **Mécaniques du Boss (JSON) :** {infos_boss_auto}
                **Notes manuelles du joueur :** {details_manuels}

                **Mon Inventaire (Évalue ces cartes à leur plein potentiel) :**
                {contexte_box}
                """

                # 4. Requête API finale (Modèle 3.1 Pro Preview)
                client = genai.Client(api_key=api_key)
                reponse_equipe = client.models.generate_content(
                    model='gemini-3.1-pro-preview',
                    contents=prompt_utilisateur,
                    config=types.GenerateContentConfig(
                        system_instruction=instructions,
                        temperature=0.1 # Décisions strictes et factuelles
                    )
                )

                texte_statut.empty()
                barre_progression.empty()
                
                st.success("✅ Stratégie d'équipe générée avec succès !")
                st.markdown("---")
                st.markdown(reponse_equipe.text)

            except Exception as e:
                texte_statut.empty()
                barre_progression.empty()
                # Censure totale de la clé API
                message_erreur = str(e)
                if api_key:
                    message_erreur = message_erreur.replace(api_key, "******-MASQUÉ-******")
                st.error(f"❌ Erreur critique lors de l'exécution de l'IA : {message_erreur}")
