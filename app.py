import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
from google import genai
from google.genai import types

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(
    page_title="Tokan - Optimiseur Dokkan Battle",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. GESTION DE LA SESSION (STATE)
# ==========================================
# Initialisation de la box de personnages si elle n'existe pas
if 'box' not in st.session_state:
    st.session_state.box = []  # Format attendu : [{"name": "...", "url": "..."}]

# ==========================================
# 3. FONCTIONS DE SCRAPING (MISES EN CACHE)
# ==========================================
@st.cache_data(show_spinner=False, ttl=86400) # Cache valide 24h
def scrape_dokkan_card(url: str) -> str:
    """
    Scrape le contenu textuel d'une fiche personnage sur dbz-dokkanbattle.com.
    Le cache Streamlit (@st.cache_data) permet de ne pas surcharger le site web 
    ni de ralentir l'app lors d'analyses répétées.
    """
    if not url or "dbz-dokkanbattle.com" not in url:
        return "URL invalide ou absente."
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nettoyage : on supprime les balises inutiles pour l'analyse des stats
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.extract()
            
        # Extraction du texte en espaçant les éléments
        text = soup.get_text(separator='\n', strip=True)
        
        # On limite la taille pour ne pas saturer le contexte de l'IA (4000 caractères suffisent largement par carte)
        return text[:4000]
    except Exception as e:
        return f"Erreur lors du scraping de la carte : {str(e)}"

# ==========================================
# 4. BARRE LATÉRALE : CLÉ API & GESTION JSON
# ==========================================
st.sidebar.title("⚙️ Configuration")

# Récupération de la clé API (Secrets en priorité, sinon saisie manuelle)
secret_api_key = ""
try:
    secret_api_key = st.secrets.get("GEMINI_API_KEY", "")
except Exception:
    pass # Ignore l'erreur si st.secrets n'est pas configuré localement

api_key = st.sidebar.text_input(
    "🔑 Clé API Google Gemini", 
    value=secret_api_key, 
    type="password",
    help="Saisissez votre clé API Google GenAI. Laissée vide si définie dans st.secrets."
)

st.sidebar.divider()
st.sidebar.header("📦 Gestion de la Box")

# Fonctionnalité d'Import JSON
uploaded_file = st.sidebar.file_uploader("Importer une Box (JSON)", type=["json"])
if uploaded_file is not None:
    try:
        data = json.load(uploaded_file)
        if isinstance(data, list):
            st.session_state.box = data
            st.sidebar.success("✅ Box importée avec succès !")
        else:
            st.sidebar.error("❌ Le fichier JSON doit contenir une liste de personnages.")
    except Exception as e:
        st.sidebar.error(f"❌ Erreur de lecture du JSON : {e}")

# Fonctionnalité d'Export JSON
if st.session_state.box:
    box_json = json.dumps(st.session_state.box, indent=4, ensure_ascii=False)
    st.sidebar.download_button(
        label="📥 Exporter ma Box",
        data=box_json,
        file_name="tokan_box.json",
        mime="application/json",
        use_container_width=True
    )

# ==========================================
# 5. INTERFACE PRINCIPALE (ONGLETS)
# ==========================================
st.title("🐉 Tokan - Dokkan Battle Team Builder")
st.markdown("Optimise tes équipes en te basant **strictement sur les mathématiques et mécaniques du jeu**.")

tab1, tab2, tab3 = st.tabs(["🛡️ Ma Box", "🎯 Niveau & Boss", "🧠 Analyse & Équipe (IA)"])

# ------------------------------------------
# ONGLET 1 : MA BOX
# ------------------------------------------
with tab1:
    st.header("Gestion de tes personnages")
    
    # Formulaire d'ajout
    with st.form("add_char_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            char_name = st.text_input("Nom (ex: Goku Super Saiyan 4 LR)", placeholder="Nom explicite du personnage")
        with col2:
            char_url = st.text_input("URL dbz-dokkanbattle.com", placeholder="https://dbz-dokkanbattle.com/...")
        
        submitted = st.form_submit_button("➕ Ajouter à la Box")
        if submitted:
            if char_name:
                st.session_state.box.append({"name": char_name, "url": char_url})
                st.success(f"{char_name} ajouté !")
                st.rerun()
            else:
                st.error("⚠️ Le nom du personnage est requis.")

    # Affichage et suppression
    if st.session_state.box:
        st.subheader(f"Personnages dans la box ({len(st.session_state.box)})")
        
        for i, char in enumerate(st.session_state.box):
            c_name, c_url, c_del = st.columns([2, 3, 1])
            c_name.write(f"**{char['name']}**")
            c_url.write(f"[Lien de la carte]({char['url']})" if char['url'] else "*(Pas d'URL fournie)*")
            if c_del.button("🗑️ Supprimer", key=f"del_{i}"):
                st.session_state.box.pop(i)
                st.rerun()
    else:
        st.info("ℹ️ Ta box est vide. Ajoute des personnages ci-dessus ou importe un fichier JSON depuis la barre latérale.")

# ------------------------------------------
# ONGLET 2 : NIVEAU & BOSS
# ------------------------------------------
with tab2:
    st.header("Configuration de l'événement")
    
    boss_name = st.text_input("Nom du Boss ou de l'événement", placeholder="Ex: Red Zone Broly, SBR Super Saiyans")
    boss_details = st.text_area(
        "Détails sur l'événement (Optionnel mais recommandé)",
        placeholder="Phases du boss, types (AGI, TEC...), immunités (étourdissement, blocage d'attaque spéciale), dégâts estimés de l'attaque spéciale (ex: tape à 1.5M), etc.",
        height=150
    )
    
    st.session_state.boss_name = boss_name
    st.session_state.boss_details = boss_details

# ------------------------------------------
# ONGLET 3 : ANALYSE & GÉNÉRATION
# ------------------------------------------
with tab3:
    st.header("Génération de l'équipe optimale")
    
    if st.button("🚀 Lancer l'analyse Tokan", type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ Veuillez configurer votre clé API Gemini dans la barre latérale.")
        elif not st.session_state.box:
            st.error("⚠️ Ta box est vide. Ajoute au moins 6 personnages pour former une équipe.")
        elif not st.session_state.get('boss_name'):
            st.error("⚠️ Veuillez renseigner le nom du Boss dans l'onglet 'Niveau & Boss'.")
        else:
            with st.spinner("Scraping des fiches, calcul des synergies et analyse en cours..."):
                try:
                    # 1. Compilation du contexte de la box avec Scraping
                    box_context = ""
                    for char in st.session_state.box:
                        box_context += f"\n### Personnage: {char['name']}\n"
                        if char.get('url'):
                            box_context += f"{scrape_dokkan_card(char['url'])}\n"
                        else:
                            box_context += "*(Pas de lien fourni, utilise tes connaissances internes pour ses stats/passifs)*\n"
                    
                    # 2. Directives Système (System Instruction)
                    # Ce prompt est la clé pour forcer une approche purement mathématique.
                    sys_instruction = (
                        "Tu es 'Tokan', l'ingénieur data analyste ultime de Dragon Ball Z: Dokkan Battle. "
                        "Ton seul but est de construire la meilleure équipe possible à partir de la box fournie pour survivre et vaincre le boss spécifié.\n\n"
                        "RÈGLES IMPÉRATIVES :\n"
                        "1. IGNORE TOTALEMENT la meta de la communauté, les avis de YouTubeurs ou les tier lists.\n"
                        "2. Base tes choix EXCLUSIVEMENT sur les mathématiques : valeur du multiplicateur du Leader Skill, "
                        "mécaniques pures de l'Aptitude Passive (Garde, % de Réduction de Dégâts, % d'Esquive, empilement/stack de DEF), "
                        "et la synergie des Liens (Ki et stats partagées).\n"
                        "3. Sélectionne obligatoirement : 1 Leader de la box, 5 Sous-unités de la box, et propose le meilleur Ami Leader idéal "
                        "(qui peut ne pas être dans la box).\n"
                        "4. Définis les deux rotations principales (Main Rotations) et les trois unités flottantes (Floaters).\n"
                        "5. Justifie chaque choix par une démonstration chiffrée de la survie face aux mécaniques du boss."
                    )

                    # 3. Prompt Utilisateur
                    user_prompt = f"""
                    **Boss / Cible :** {st.session_state.boss_name}
                    **Spécificités du boss :** {st.session_state.boss_details}

                    **Ma Box de personnages (Données extraites du site) :**
                    {box_context}

                    Génère l'équipe optimale en format Markdown propre avec ces sections exactes :
                    - 🏆 **Composition de l'équipe** (Leader, Sous-unités, Ami Leader)
                    - 🔄 **Rotations Optimisées** (Rotation 1, Rotation 2, Flotteurs)
                    - 📊 **Analyse Mathématique & Stratégie** (Démonstration de la synergie des liens et de la survie aux dégâts)
                    """

                    # 4. Appel à l'API via le SDK google-genai
                    client = genai.Client(api_key=api_key)
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-pro', # Utilisation du modèle le plus avancé pour le raisonnement
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=sys_instruction,
                            temperature=0.1 # Température très basse pour un output analytique, factuel et déterministe
                        )
                    )

                    st.success("✅ Analyse terminée avec succès !")
                    st.markdown("---")
                    st.markdown(response.text)

                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Erreur réseau lors du scraping d'une carte : {str(e)}")
                except Exception as e:
                    st.error(f"❌ Une erreur critique est survenue avec l'API ou le traitement : {str(e)}")
