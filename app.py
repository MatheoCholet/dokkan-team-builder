import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
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
# GESTION DE LA SESSION (STATE)
# ==========================================
if 'box' not in st.session_state:
    st.session_state.box = []  # Liste de dictionnaires pour stocker les personnages

# ==========================================
# FONCTIONS UTILITAIRES ET DE SCRAPING
# ==========================================
@st.cache_data(show_spinner=False, ttl=86400)
def scrape_dokkan_card(url: str) -> str:
    """
    Extrait le contenu textuel d'une fiche personnage sur dbz-dokkanbattle.com.
    Le cache Streamlit (@st.cache_data) évite de refaire la requête pour une même URL.
    """
    if not url or "dbz-dokkanbattle.com" not in url:
        return "Aucun lien dbz-dokkanbattle fourni ou lien invalide."
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nettoyage des balises inutiles pour isoler le texte (stats, passifs, liens)
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.extract()
            
        text = soup.get_text(separator='\n', strip=True)
        return text[:4500]  # Limite pour ne pas saturer le contexte de l'IA
    except Exception as e:
        return f"Erreur lors de l'extraction des données : {str(e)}"

def maj_doublons(index: int, new_value: int):
    """Met à jour le nombre de doublons d'un personnage dans la session."""
    st.session_state.box[index]['doublons'] = new_value

def supprimer_personnage(index: int):
    """Supprime un personnage de la box."""
    st.session_state.box.pop(index)

# ==========================================
# BARRE LATÉRALE : SÉCURITÉ API & GESTION JSON
# ==========================================
st.sidebar.title("⚙️ Configuration")

# SÉCURITÉ STRICTE : Récupération et masquage de la clé API
api_key = None
has_secret_key = False

try:
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        has_secret_key = True
except Exception:
    pass

if has_secret_key and api_key:
    st.sidebar.success("🟢 Connecté au service d'analyse")
else:
    # Champ de saisie strictement masqué si aucune clé n'est dans st.secrets
    api_key = st.sidebar.text_input(
        "Clé API Gemini", 
        type="password",
        help="Saisissez votre clé API Google GenAI. Vos saisies sont masquées."
    )

st.sidebar.divider()
st.sidebar.header("📦 Import / Export de la Box")

# Fichier JSON - Import
fichier_upload = st.sidebar.file_uploader("Importer un fichier (box.json)", type=["json"])
if fichier_upload is not None:
    try:
        data = json.load(fichier_upload)
        if isinstance(data, list):
            st.session_state.box = data
            st.sidebar.success("✅ Box importée avec succès !")
        else:
            st.sidebar.error("❌ Le fichier JSON doit contenir une liste valide.")
    except Exception:
        st.sidebar.error("❌ Erreur de lecture du fichier JSON.")

# Fichier JSON - Export
if st.session_state.box:
    box_json_str = json.dumps(st.session_state.box, indent=4, ensure_ascii=False)
    st.sidebar.download_button(
        label="📥 Sauvegarder ma Box (box.json)",
        data=box_json_str,
        file_name="box.json",
        mime="application/json",
        use_container_width=True
    )

# ==========================================
# INTERFACE PRINCIPALE (ONGLETS)
# ==========================================
st.title("🐉 Dokkan Team Builder")
st.markdown("Optimisez vos équipes pour le contenu difficile en exploitant le plein potentiel de vos cartes.")

onglet_box, onglet_event, onglet_analyse = st.tabs(["🛡️ Ma Box", "🎯 L'Événement", "🧠 Analyse & Stratégie"])

# ------------------------------------------
# ONGLET 1 : GESTION DE LA BOX
# ------------------------------------------
with onglet_box:
    st.header("Ajouter un personnage")
    
    with st.form("ajout_personnage_form", clear_on_submit=True):
        col_n, col_u = st.columns(2)
        with col_n:
            nom_perso = st.text_input("Nom de la carte (ex: Son Gohan Beast, Goku Ultra Instinct)")
        with col_u:
            url_perso = st.text_input("URL dbz-dokkanbattle.com (Optionnel mais recommandé pour la précision)")
            
        col_t, col_r, col_d, col_z = st.columns(4)
        with col_t:
            type_perso = st.selectbox("Type", ["AGI", "TEC", "INT", "PUI", "END"])
        with col_r:
            rarete_perso = st.selectbox("Rareté actuelle", ["SSR", "UR", "LR"])
        with col_d:
            doublons_perso = st.number_input("Doublons (Arbre)", min_value=0, max_value=4, step=1)
        with col_z:
            ztur_perso = st.checkbox("Possède un Z-TUR / Super Z-TUR ?")
            
        bouton_ajout = st.form_submit_button("➕ Ajouter à ma Box")
        if bouton_ajout:
            if nom_perso.strip():
                nouveau_perso = {
                    "nom": nom_perso.strip(),
                    "url": url_perso.strip(),
                    "type": type_perso,
                    "rarete": rarete_perso,
                    "doublons": doublons_perso,
                    "z_tur": ztur_perso
                }
                st.session_state.box.append(nouveau_perso)
                st.success(f"✅ {nom_perso} ajouté à votre box !")
                st.rerun()
            else:
                st.error("⚠️ Le nom du personnage est obligatoire.")

    st.divider()
    st.header(f"Ma Collection ({len(st.session_state.box)} personnages)")
    
    if st.session_state.box:
        # Affichage dynamique de la liste avec possibilité de modifier/supprimer
        for i, perso in enumerate(st.session_state.box):
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 2, 1])
            
            # Affichage du nom et du lien éventuel
            lien = f" [🔗]({perso.get('url')})" if perso.get('url') else ""
            c1.markdown(f"**{perso['nom']}**{lien}")
            
            c2.markdown(f"{perso['type']} | {perso['rarete']}")
            
            ztur_texte = "Z-TUR ✅" if perso.get('z_tur') else "Z-TUR ❌"
            c3.markdown(ztur_texte)
            
            # Selectbox pour mettre à jour les doublons en direct
            c4.selectbox(
                "Doublons",
                options=[0, 1, 2, 3, 4],
                index=perso['doublons'],
                key=f"doublon_{i}",
                on_change=maj_doublons,
                args=(i, st.session_state[f"doublon_{i}"]),
                label_visibility="collapsed"
            )
            
            if c5.button("🗑️ Retirer", key=f"del_{i}"):
                supprimer_personnage(i)
                st.rerun()
    else:
        st.info("Votre box est vide. Veuillez importer un fichier JSON ou ajouter des personnages manuellement.")

# ------------------------------------------
# ONGLET 2 : L'ÉVÉNEMENT (BOSS)
# ------------------------------------------
with onglet_event:
    st.header("Définir le défi")
    
    nom_boss = st.text_input("Nom de l'événement ou du Boss (ex: Red Zone Fusion Zamasu, SBR Survie de l'Univers)")
    details_boss = st.text_area(
        "Détails stratégiques (Optionnel)",
        placeholder="Décrivez les phases du boss, son type, s'il bloque l'esquive, s'il annule la réduction de dégâts, les dégâts estimés de son attaque spéciale, etc.",
        height=200
    )
    
    st.session_state.nom_boss = nom_boss
    st.session_state.details_boss = details_boss

# ------------------------------------------
# ONGLET 3 : ANALYSE ET GÉNÉRATION (IA)
# ------------------------------------------
with onglet_analyse:
    st.header("Création de l'équipe optimale")
    
    if st.button("🚀 Générer la meilleure équipe", type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ La clé API Gemini est manquante. Veuillez vérifier votre configuration.")
        elif len(st.session_state.box) < 6:
            st.error("⚠️ Vous devez avoir au moins 6 personnages dans votre box pour former une équipe complète.")
        elif not st.session_state.get('nom_boss'):
            st.error("⚠️ Veuillez renseigner le nom de l'événement dans l'onglet précédent.")
        else:
            with st.spinner("Analyse approfondie en cours (Extraction des données, calcul des synergies, éveils potentiels)..."):
                try:
                    # 1. Préparation du contexte (Scraping des unités)
                    contexte_box = ""
                    for perso in st.session_state.box:
                        contexte_box += f"\n### Personnage: {perso['nom']} (Type: {perso['type']}, Rareté actuelle: {perso['rarete']}, Doublons: {perso['doublons']}, Z-TUR possédé: {perso['z_tur']})\n"
                        if perso.get('url'):
                            contexte_box += f"Données du jeu extraites : {scrape_dokkan_card(perso['url'])}\n"
                        else:
                            contexte_box += "Utilise tes connaissances internes pour les aptitudes de cette carte.\n"

                    # 2. Instructions Système (Règles strictes imposées à l'IA)
                    instructions_systeme = (
                        "Tu es l'expert stratégique absolu de Dragon Ball Z: Dokkan Battle. "
                        "Ton objectif est de créer la meilleure équipe pour vaincre le boss spécifié.\n\n"
                        "RÈGLES STRICTES ET IMPÉRATIVES :\n"
                        "1. LANGUE : Tu dois répondre 100% en français (terminologie du jeu en français).\n"
                        "2. RESPECT DE LA BOX : L'équipe DOIT être composée UNIQUEMENT de 1 Leader et 5 sous-unités piochés EXACTEMENT dans la liste de la box fournie. "
                        "Tu as seulement le droit d'inventer/proposer l'Ami Leader idéal (qui peut ne pas être dans la box).\n"
                        "3. PLEIN POTENTIEL D'ÉVEIL : Tu ne dois JAMAIS juger une carte sur son état SSR actuel. "
                        "Tu dois obligatoirement évaluer chaque carte à son stade d'éveil maximum (UR, LR, Z-TUR, Super Z-TUR) d'après les bases de données du jeu. "
                        "Si tu sélectionnes une unité qui est actuellement SSR dans la box mais qui est forte une fois éveillée, "
                        "tu dois l'inclure dans l'équipe et écrire explicitement à côté de son nom : '(À éveiller en UR/LR / Z-TUR pour ce niveau)'.\n"
                        "4. FORMAT DE RÉPONSE OBLIGATOIRE en Markdown :\n"
                        "   - 🏆 Leader (préciser le leader skill)\n"
                        "   - 👥 Membres de l'équipe (les 5 unités, avec mention d'éveil si nécessaire)\n"
                        "   - 🤝 Ami Leader recommandé\n"
                        "   - 🔄 Rotations Principales (Rotation 1 : Slot 1 et 2 / Rotation 2 : Slot 1 et 2)\n"
                        "   - 🎈 Unités Flottantes (Slot 3)\n"
                        "   - 📜 Stratégie détaillée (Comment survivre aux attaques, gestion des objets de soutien comme Whis ou Princesse Hebi)."
                    )

                    # 3. Prompt de l'utilisateur
                    prompt_utilisateur = f"""
                    **Défi / Boss à affronter :** {st.session_state.nom_boss}
                    **Détails de l'événement :** {st.session_state.details_boss}

                    **Ma Box (Inventaire disponible) :**
                    {contexte_box}

                    Construis l'équipe optimale selon tes directives système.
                    """

                    # 4. Appel de l'API via le SDK officiel
                    client = genai.Client(api_key=api_key)
                    
                    reponse = client.models.generate_content(
                        model='gemini-2.5-pro',
                        contents=prompt_utilisateur,
                        config=types.GenerateContentConfig(
                            system_instruction=instructions_systeme,
                            temperature=0.2 # Température basse pour privilégier la logique et respecter la box
                        )
                    )

                    st.success("✅ Analyse terminée avec succès !")
                    st.markdown("---")
                    st.markdown(reponse.text)

                except Exception as e:
                    # Protection stricte de l'API Key dans les logs d'erreur
                    message_erreur = str(e)
                    if api_key:
                        message_erreur = message_erreur.replace(api_key, "******")
                    st.error(f"❌ Une erreur est survenue lors de l'analyse : {message_erreur}")
