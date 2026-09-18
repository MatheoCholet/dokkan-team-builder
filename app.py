import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import uuid
from google import genai
from google.genai import types

# ==========================================
# CONFIGURATION DE LA PAGE & DESIGN DBZ
# ==========================================
st.set_page_config(
    page_title="Dokkan Team Builder",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injection de CSS personnalisé (Thème Dragon Ball Z)
st.markdown("""
<style>
    /* Arrière-plan global : Cosmos / Aura */
    .stApp {
        background-color: #0b1120;
        background-image: radial-gradient(circle at top right, #1a2235, #0b1120);
        color: #f1f5f9;
    }
    
    /* Typographie des titres : Orange emblématique */
    h1, h2, h3 {
        color: #ff9800 !important;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.9);
        font-family: 'Arial Black', Impact, sans-serif;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Boutons d'action : Style Super Saiyan */
    .stButton>button {
        background: linear-gradient(45deg, #e65100, #ffb300);
        color: #ffffff !important;
        border: 2px solid #fff59d;
        border-radius: 8px;
        font-weight: 900;
        text-transform: uppercase;
        box-shadow: 0 0 15px rgba(255, 152, 0, 0.5);
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        box-shadow: 0 0 25px rgba(255, 193, 7, 1);
        transform: scale(1.03);
        border-color: #ffffff;
    }
    
    /* Champs de saisie : Sombres avec focus orange */
    .stTextInput>div>div>input, .stSelectbox>div>div>select, .stNumberInput>div>div>input, .stTextArea>div>div>textarea {
        background-color: #151a30 !important;
        color: #ffffff !important;
        border: 1px solid #ff9800 !important;
        border-radius: 5px;
    }
    .stTextInput>div>div>input:focus {
        box-shadow: 0 0 10px rgba(255, 152, 0, 0.5) !important;
    }
    
    /* Design des onglets */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
        border-bottom: 2px solid #ff9800;
    }
    .stTabs [data-baseweb="tab"] {
        color: #ffffff;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ff9800 !important;
        color: #000000 !important;
        border-radius: 5px 5px 0 0;
    }
    
    /* Cartes de la box stylisées */
    .dbz-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border-left: 6px solid #ff9800;
        border-right: 1px solid #334155;
        border-top: 1px solid #334155;
        border-bottom: 1px solid #334155;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.8);
    }
    
    /* Panneau latéral */
    [data-testid="stSidebar"] {
        background-color: #080c17;
        border-right: 2px solid #ffb300;
    }
</style>
""", unsafe_allow_html=True)

# Image de bannière (URL publique et stable)
st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Dragon_Ball_Super_logo.svg/1024px-Dragon_Ball_Super_logo.svg.png", width=300)

# ==========================================
# GESTION D'ÉTAT & ROBUSTESSE
# ==========================================
# Initialisation sécurisée des variables de session
if 'box' not in st.session_state:
    st.session_state.box = []
if 'nom_boss' not in st.session_state:
    st.session_state.nom_boss = ""
if 'details_boss_auto' not in st.session_state:
    st.session_state.details_boss_auto = "{}"
if 'details_manuels' not in st.session_state:
    st.session_state.details_manuels = ""

def normaliser_personnage(item: dict) -> dict:
    """Normalise les clés JSON et génère un UUID unique pour éviter les KeyErrors de Streamlit."""
    nom = item.get("nom", item.get("name", "Personnage inconnu"))
    doublons = item.get("doublons", item.get("doublon", 0))
    rarete = item.get("rarete", item.get("rarity", "SSR"))
    type_perso = item.get("type", "Inconnu")
    z_tur = item.get("z_tur", item.get("ztur", False))
    url = item.get("url", item.get("lien", ""))
    
    return {
        "_id": str(uuid.uuid4()),
        "nom": " ".join(str(nom).split()),
        "type": type_perso,
        "rarete": rarete,
        "doublons": int(doublons) if str(doublons).isdigit() else 0,
        "z_tur": bool(z_tur),
        "url": url
    }

def maj_doublons(char_id: str, widget_key: str):
    """Callback sécurisé pour la mise à jour des doublons."""
    for char in st.session_state.box:
        if char["_id"] == char_id:
            char["doublons"] = st.session_state[widget_key]
            break

def supprimer_personnage(char_id: str):
    """Supprime un personnage par son UUID."""
    st.session_state.box = [c for c in st.session_state.box if c["_id"] != char_id]

# ==========================================
# SCRAPING ANTI-BOT & FALLBACK INTELLIGENT
# ==========================================
@st.cache_data(show_spinner=False, ttl=86400)
def extraire_texte_brut(url: str) -> str:
    """Tente un scraping classique. Détecte le blocage Cloudflare pour activer le fallback."""
    if not url or "dbz-dokkanbattle.com" not in url:
        return ""
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Fast-fail si Cloudflare bloque
        if response.status_code in [401, 403] or "cloudflare" in response.text.lower() or "just a moment" in response.text.lower():
            return "ERREUR_BLOCAGE"
            
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.extract()
            
        texte = soup.get_text(separator=' ', strip=True)
        return texte[:8000]
    except Exception:
        return "ERREUR_BLOCAGE"

@st.cache_data(show_spinner=False, ttl=86400)
def structurer_donnees_llm(texte_brut: str, type_donnee: str, api_key: str, nom_entite: str = "", url: str = "") -> str:
    """Parse le texte avec Gemini 3.1 Pro. Si bloqué, utilise Google Search Grounding pour trouver les stats."""
    if not api_key:
        return "{}"

    client = genai.Client(api_key=api_key)
    echec_scraping = not texte_brut or "ERREUR_BLOCAGE" in texte_brut

    try:
        if type_donnee == "carte":
            instruction = (
                "Tu es l'expert absolu de Dokkan Battle. Réponds UNIQUEMENT en format JSON avec les clés : "
                "'leader_skill', 'aptitude_passive' (incluant garde, réduction, esquive, stack), 'liens', et 'statistiques_max'. "
                "Aucun commentaire en dehors du JSON."
            )
            if echec_scraping:
                prompt = (
                    f"Le site a bloqué la connexion. Utilise ton outil de recherche Google pour trouver "
                    f"des informations précises sur la carte Dokkan Battle nommée '{nom_entite}' (Lien de réf: {url}). "
                    f"Trouve son passif, ses liens et statistiques à son éveil maximal (UR/LR/Z-TUR), puis génère le JSON."
                )
            else:
                prompt = f"Analyse ce texte extrait de la carte '{nom_entite}' :\n\n{texte_brut}"
                
        else: # type_donnee == "boss"
            instruction = (
                "Tu es l'expert absolu de Dokkan Battle. Réponds UNIQUEMENT en format JSON avec les clés : "
                "'type_elementaire', 'immunites' (stun, blocage), 'attaques_de_zone' et 'mecaniques_speciales'. "
                "Aucun commentaire en dehors du JSON."
            )
            if echec_scraping:
                prompt = (
                    f"Le site a bloqué la connexion. Lance une recherche web (Google Search) pour trouver "
                    f"les spécificités et mécaniques du Boss/Événement Dokkan Battle nommé '{nom_entite}' (Lien de réf: {url}). "
                    f"Identifie ses immunités, ses dégâts et particularités, puis génère le JSON."
                )
            else:
                prompt = f"Analyse ce texte brut pour l'événement '{nom_entite}' :\n\n{texte_brut}"

        # Paramétrage dynamique de l'API (JSON natif VS Outil de Recherche)
        config_args = {
            "system_instruction": instruction,
            "temperature": 0.2 if echec_scraping else 0.0
        }
        
        if echec_scraping:
            config_args["tools"] = [{"google_search": {}}]
        else:
            config_args["response_mime_type"] = "application/json"

        reponse = client.models.generate_content(
            model='gemini-3.1-pro-preview',
            contents=prompt,
            config=types.GenerateContentConfig(**config_args)
        )
        
        # Nettoyage strict (sécurité contre les balises markdown)
        clean_json_str = reponse.text.replace("```json", "").replace("```", "").strip()
        
        try:
            parsed_json = json.loads(clean_json_str)
            return json.dumps(parsed_json, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            return clean_json_str
            
    except Exception as e:
        return f'{{"erreur": "Échec de l\'IA : {str(e)}"}}'

# ==========================================
# BARRE LATÉRALE : SÉCURITÉ ET SAUVEGARDES
# ==========================================
st.sidebar.title("⚙️ Radar Dragon")

api_key = st.secrets.get("GEMINI_API_KEY", None)
if api_key:
    st.sidebar.success("🟢 Connexion établie avec l'IA")
else:
    api_key = st.sidebar.text_input(
        "Clé API Gemini", 
        type="password",
        help="Votre clé est strictement confidentielle et masquée."
    )

st.sidebar.divider()
st.sidebar.header("📦 Capsule Corporation")

fichier_upload = st.sidebar.file_uploader("Importer une sauvegarde (.json)", type=["json"])
if fichier_upload is not None:
    try:
        data = json.load(fichier_upload)
        if isinstance(data, list):
            st.session_state.box = [normaliser_personnage(item) for item in data]
            st.sidebar.success("✅ Données de la box chargées !")
        else:
            st.sidebar.error("❌ Format invalide (liste attendue).")
    except Exception:
        st.sidebar.error("❌ Erreur de lecture du fichier JSON.")

if st.session_state.box:
    box_export = [{k: v for k, v in c.items() if k != "_id"} for c in st.session_state.box]
    st.sidebar.download_button(
        label="📥 Sauvegarder ma Box",
        data=json.dumps(box_export, indent=4, ensure_ascii=False),
        file_name="dokkan_box.json",
        mime="application/json",
        use_container_width=True
    )

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
st.title("🐉 Dokkan Team Builder")
st.markdown("Assemblez votre équipe de guerriers ultime. L'IA analyse les données en temps réel pour contrer les mécaniques des boss.")

onglet_box, onglet_event, onglet_analyse = st.tabs(["🛡️ Inventaire", "🎯 Cible (Boss)", "🧠 Stratégie d'Équipe"])

# ------------------------------------------
# ONGLET 1 : GESTION DE LA BOX
# ------------------------------------------
with onglet_box:
    st.subheader("Recruter un Combattant")
    
    with st.form("ajout_perso_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nom_perso = st.text_input("Nom de la carte (ex: Son Gohan Beast, Goku SSJ4)")
        with col2:
            url_perso = st.text_input("URL dbz-dokkanbattle.com (Utile pour guider l'IA en cas de doute)")
            
        c_type, c_rar, c_dup, c_ztur = st.columns(4)
        with c_type:
            type_perso = st.selectbox("Type", ["AGI", "TEC", "INT", "PUI", "END"])
        with c_rar:
            rarete_perso = st.selectbox("Rareté", ["SSR", "UR", "LR"])
        with c_dup:
            doublons_perso = st.number_input("Doublons", min_value=0, max_value=4, step=1)
        with c_ztur:
            st.write("") 
            ztur_perso = st.checkbox("Z-TUR / Super Z-TUR ?")
            
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
                st.success(f"✅ {nom_perso.strip()} a été ajouté à l'inventaire.")
                st.rerun()
            else:
                st.warning("⚠️ Le nom du personnage est requis.")

    st.divider()
    st.subheader(f"Vos Guerriers ({len(st.session_state.box)})")
    
    if st.session_state.box:
        for perso in st.session_state.box:
            st.markdown('<div class="dbz-card">', unsafe_allow_html=True)
            c_nom, c_infos, c_doublon, c_action = st.columns([4, 3, 2, 1])
            
            lien = f" [🔗]({perso['url']})" if perso.get('url') else ""
            c_nom.markdown(f"<h4 style='margin:0; color:#ff9800;'>{perso['nom']}{lien}</h4>", unsafe_allow_html=True)
            
            ztur_txt = " | 🌟 Z-TUR" if perso['z_tur'] else ""
            c_infos.markdown(f"**{perso['type']}** | {perso['rarete']}{ztur_txt}")
            
            cle_widget = f"doublon_{perso['_id']}"
            c_doublon.selectbox(
                "Doublons :",
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
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("La box est vide. Importez un fichier JSON ou ajoutez des unités.")

# ------------------------------------------
# ONGLET 2 : LE BOSS (AVEC FALLBACK GOOGLE)
# ------------------------------------------
with onglet_event:
    st.subheader("Analyse de la Menace")
    
    nom_boss = st.text_input("Nom de l'événement ou du Boss (Obligatoire, ex: Red Zone Broly, SBR Divin)")
    url_boss = st.text_input("URL dbz-dokkanbattle.com (Optionnelle)")
    details_manuels = st.text_area("Notes manuelles du combat (Optionnel)", height=100)
    
    st.session_state.nom_boss = nom_boss
    st.session_state.details_manuels = details_manuels
    
    if st.button("🔍 Extraire les mécaniques du Boss", type="secondary"):
        if not api_key:
            st.warning("⚠️ Clé API Gemini requise pour utiliser cette fonction.")
        elif not nom_boss:
            st.warning("⚠️ Veuillez indiquer le nom de l'événement pour guider l'analyse.")
        else:
            with st.spinner("Analyse en cours (Scraping ou Recherche web via IA)..."):
                texte_boss_brut = extraire_texte_brut(url_boss) if url_boss else "ERREUR_BLOCAGE"
                
                donnees_boss_json = structurer_donnees_llm(
                    texte_boss_brut, "boss", api_key, nom_entite=nom_boss, url=url_boss
                )
                
                st.session_state.details_boss_auto = donnees_boss_json
                
                if "erreur" in donnees_boss_json.lower():
                    st.error("❌ Échec de l'extraction des données du boss.")
                else:
                    st.success("✅ Mécaniques du boss identifiées et sauvegardées.")
                    st.code(donnees_boss_json, language="json")

# ------------------------------------------
# ONGLET 3 : GÉNÉRATION D'ÉQUIPE (GEMINI 3.1 PRO)
# ------------------------------------------
with onglet_analyse:
    st.subheader("Planification Stratégique")
    
    if st.button("🚀 Créer l'Équipe Ultime", type="primary", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Clé API Gemini manquante. Veuillez vérifier le panneau latéral.")
        elif len(st.session_state.box) < 6:
            st.warning("⚠️ Il faut au moins 6 personnages dans la box pour former une équipe complète.")
        elif not st.session_state.get('nom_boss'):
            st.warning("⚠️ Veuillez renseigner le nom de l'adversaire dans l'onglet 'Cible (Boss)'.")
        else:
            barre_progression = st.progress(0)
            texte_statut = st.empty()
            
            try:
                # 1. Compilation sécurisée des données de la box
                contexte_box = ""
                total_persos = len(st.session_state.box)
                
                for index, perso in enumerate(st.session_state.box):
                    texte_statut.write(f"Analyse approfondie : {perso['nom']} ({index+1}/{total_persos})...")
                    barre_progression.progress((index + 1) / total_persos)
                    
                    contexte_box += f"\n### Carte : {perso['nom']}\n"
                    contexte_box += f"- Attributs : Type {perso['type']}, Rareté actuelle : {perso['rarete']}, Doublons : {perso['doublons']}\n"
                    
                    # Fallback automatique si scraping bloqué
                    texte_carte_brut = extraire_texte_brut(perso['url']) if perso.get('url') else "ERREUR_BLOCAGE"
                    donnees_carte_json = structurer_donnees_llm(
                        texte_carte_brut, "carte", api_key, nom_entite=perso['nom'], url=perso.get('url', '')
                    )
                    contexte_box += f"- Mécaniques (Extraites ou déduites) : {donnees_carte_json}\n"

                texte_statut.write("Formation de l'équipe par Gemini 3.1 Pro Preview...")

                # 2. Instructions Système Strictes
                instructions = (
                    "Tu es le meilleur stratège mondial de Dragon Ball Z: Dokkan Battle.\n"
                    "RÈGLES ABSOLUES ET IMPÉRATIVES :\n"
                    "1. LANGUE : Toutes tes explications DOIVENT être 100% en français.\n"
                    "2. EXCLUSIVITÉ DE LA BOX : Tu DOIS sélectionner EXACTEMENT 6 personnages (1 Leader, 5 Sous-unités) "
                    "UNIQUEMENT à partir de l'inventaire fourni. Ne propose aucune autre unité. L'Ami Leader (7ème perso) est libre.\n"
                    "3. ÉVALUATION AU PLEIN POTENTIEL : C'est primordial. Si une carte de la box est 'SSR' ou 'UR' mais qu'elle a un éveil LR ou Z-TUR "
                    "dans le jeu (ou d'après le JSON extrait), évalue-la OBLIGATOIREMENT selon ses statistiques et son passif au STADE MAXIMAL. "
                    "Ne juge jamais une carte sur sa rareté d'origine. Si tu l'intègres, tu DOIS écrire à côté de son nom : "
                    "'⚠️ À éveiller en UR/LR / Z-TUR pour ce combat'.\n"
                    "4. STRATÉGIE SURVIVALISTE : Appuie-toi sur la Garde, la Réduction et l'Esquive face aux attaques (JSON) du Boss.\n\n"
                    "FORMAT ATTENDU EN MARKDOWN :\n"
                    "🏆 **Leader** (Nom exact + Bonus de Leader)\n"
                    "👥 **Équipe** (Les 5 autres cartes avec mentions d'éveil si nécessaire)\n"
                    "🤝 **Ami Leader recommandé**\n"
                    "🔄 **Rotations Principales** (Rotation 1 : Slots 1 & 2 | Rotation 2 : Slots 1 & 2)\n"
                    "🎈 **Flotteurs** (Les 3 unités en Slot 3)\n"
                    "📜 **Stratégie de Survie** (Explications des rotations et des objets de soutien)."
                )

                # 3. Prompt Final
                infos_boss_auto = st.session_state.get('details_boss_auto', "{}")
                details_manuels = st.session_state.get('details_manuels', "")
                
                prompt_utilisateur = f"""
                **Adversaire :** {st.session_state.nom_boss}
                **Mécaniques du Boss (JSON) :** {infos_boss_auto}
                **Notes manuelles du joueur :** {details_manuels}

                **Mon Inventaire (Pioche UNIQUEMENT 6 cartes ici, et évalue-les à plein potentiel) :**
                {contexte_box}
                """

                # 4. Exécution API
                client = genai.Client(api_key=api_key)
                reponse_equipe = client.models.generate_content(
                    model='gemini-3.1-pro-preview',
                    contents=prompt_utilisateur,
                    config=types.GenerateContentConfig(
                        system_instruction=instructions,
                        temperature=0.1
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
                
                # Masquage absolu de la clé en cas de Timeout ou erreur 503
                message_erreur = str(e)
                if api_key:
                    message_erreur = message_erreur.replace(api_key, "******-MASQUÉ-******")
                st.error(f"❌ Une perturbation est survenue lors de l'appel à l'IA : {message_erreur}")
