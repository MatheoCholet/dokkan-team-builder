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
# UTILITAIRES ET GESTION D'ÉTAT
# ==========================================
def normaliser_personnage(item: dict) -> dict:
    """Standardise les clés JSON pour accepter différentes nomenclatures et assigne un UUID unique."""
    nom = item.get("nom", item.get("name", "Personnage inconnu"))
    doublons = item.get("doublons", item.get("doublon", 0))
    rarete = item.get("rarete", item.get("rarity", "SSR"))
    type_perso = item.get("type", "Inconnu")
    z_tur = item.get("z_tur", item.get("ztur", False))
    url = item.get("url", item.get("lien", ""))
    
    # Nettoyage de base du nom pour la tolérance (espaces superflus)
    nom = " ".join(nom.split())
    
    return {
        "_id": str(uuid.uuid4()), # Identifiant unique pour éviter la KeyError des widgets Streamlit
        "nom": nom,
        "type": type_perso,
        "rarete": rarete,
        "doublons": int(doublons) if str(doublons).isdigit() else 0,
        "z_tur": bool(z_tur),
        "url": url
    }

if 'box' not in st.session_state:
    st.session_state.box = []

def maj_doublons(char_id: str, widget_key: str):
    """Callback sécurisé : Met à jour les doublons sans lire st.session_state dans les arguments."""
    for char in st.session_state.box:
        if char["_id"] == char_id:
            char["doublons"] = st.session_state[widget_key]
            break

def supprimer_personnage(char_id: str):
    """Supprime un personnage de manière sécurisée en filtrant par son UUID."""
    st.session_state.box = [c for c in st.session_state.box if c["_id"] != char_id]

@st.cache_data(show_spinner=False, ttl=86400)
def scrape_dokkan_card(url: str) -> str:
    """Scrape intelligemment le contenu d'une fiche Dokkan avec mise en cache."""
    if not url or "dbz-dokkanbattle.com" not in url:
        return ""
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.extract()
            
        text = soup.get_text(separator=' | ', strip=True)
        return text[:4000]
    except Exception:
        return "Erreur d'extraction de l'URL."

# ==========================================
# BARRE LATÉRALE : SÉCURITÉ ET DONNÉES
# ==========================================
st.sidebar.title("⚙️ Paramètres")

# Gestion ultra-sécurisée de l'API Key
api_key = None
has_secret_key = False

try:
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        has_secret_key = True
except Exception:
    pass

if has_secret_key and api_key:
    st.sidebar.success("🟢 Service IA connecté")
else:
    api_key = st.sidebar.text_input(
        "Clé API Gemini", 
        type="password",
        help="Votre clé ne sera jamais enregistrée publiquement ni affichée."
    )

st.sidebar.divider()
st.sidebar.header("📦 Import / Export")

fichier_upload = st.sidebar.file_uploader("Importer une box (.json)", type=["json"])
if fichier_upload is not None:
    try:
        data = json.load(fichier_upload)
        if isinstance(data, list):
            st.session_state.box = [normaliser_personnage(item) for item in data]
            st.sidebar.success("✅ Box importée et normalisée avec succès !")
        else:
            st.sidebar.error("❌ Format JSON invalide (liste attendue).")
    except Exception:
        st.sidebar.error("❌ Impossible de lire ce fichier JSON.")

if st.session_state.box:
    # On retire l'_id interne avant l'export pour garder un JSON propre
    box_export = []
    for c in st.session_state.box:
        c_copy = c.copy()
        c_copy.pop("_id", None)
        box_export.append(c_copy)
        
    box_json_str = json.dumps(box_export, indent=4, ensure_ascii=False)
    st.sidebar.download_button(
        label="📥 Exporter ma Box",
        data=box_json_str,
        file_name="dokkan_box.json",
        mime="application/json",
        use_container_width=True
    )

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
st.title("🐉 Dokkan Team Builder")
st.markdown("Optimisez vos équipes de façon stratégique en exploitant le plein potentiel de votre box.")

onglet_box, onglet_event, onglet_analyse = st.tabs(["🛡️ Ma Box", "🎯 Boss & Événement", "🧠 Génération d'Équipe"])

# ------------------------------------------
# ONGLET 1 : GESTION DE LA BOX
# ------------------------------------------
with onglet_box:
    st.subheader("Ajouter un nouveau personnage")
    
    with st.form("ajout_perso_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nom_perso = st.text_input("Nom du personnage (ex: Son Gohan Beast, Goku SSJ4)")
        with col2:
            url_perso = st.text_input("URL dbz-dokkanbattle.com (Optionnel)")
            
        c_type, c_rar, c_dup, c_ztur = st.columns(4)
        with c_type:
            type_perso = st.selectbox("Type", ["AGI", "TEC", "INT", "PUI", "END"])
        with c_rar:
            rarete_perso = st.selectbox("Rareté actuelle", ["SSR", "UR", "LR"])
        with c_dup:
            doublons_perso = st.number_input("Doublons", min_value=0, max_value=4, step=1)
        with c_ztur:
            st.write("") # Espacement
            ztur_perso = st.checkbox("Possède un Z-TUR ?")
            
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
                st.success(f"✅ {nom_perso.strip()} ajouté !")
                st.rerun()
            else:
                st.error("⚠️ Le nom est obligatoire.")

    st.divider()
    st.subheader(f"Collection actuelle ({len(st.session_state.box)} personnages)")
    
    if st.session_state.box:
        for perso in st.session_state.box:
            c_nom, c_infos, c_doublon, c_action = st.columns([4, 3, 2, 1])
            
            lien = f" [🔗]({perso['url']})" if perso.get('url') else ""
            c_nom.markdown(f"**{perso['nom']}**{lien}")
            
            ztur_txt = " | Z-TUR ✅" if perso['z_tur'] else ""
            c_infos.markdown(f"{perso['type']} | {perso['rarete']}{ztur_txt}")
            
            # Utilisation de l'UUID pour sécuriser la modification d'état
            cle_widget = f"doublon_widget_{perso['_id']}"
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
        st.info("La box est vide.")

# ------------------------------------------
# ONGLET 2 : LE BOSS
# ------------------------------------------
with onglet_event:
    st.subheader("Configuration du combat")
    
    nom_boss = st.text_input("Nom de l'Événement / Boss (ex: Red Zone Broly, SBR Extrême)")
    details_boss = st.text_area(
        "Mécaniques spécifiques (Optionnel mais recommandé)",
        placeholder="Décrivez les phases, le type du boss, s'il bloque l'esquive, s'il fait des attaques de zone (AOE), les dégâts attendus...",
        height=150
    )
    
    st.session_state.nom_boss = nom_boss
    st.session_state.details_boss = details_boss

# ------------------------------------------
# ONGLET 3 : GÉNÉRATION D'ÉQUIPE (GEMINI)
# ------------------------------------------
with onglet_analyse:
    st.subheader("Analyse Tactique par l'IA")
    
    if st.button("🚀 Lancer l'analyse et créer l'équipe", type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ Veuillez configurer votre clé API Gemini dans le panneau latéral.")
        elif len(st.session_state.box) < 6:
            st.error("⚠️ Il vous faut au minimum 6 personnages dans votre box pour former une équipe.")
        elif not st.session_state.get('nom_boss'):
            st.error("⚠️ Veuillez indiquer le nom du Boss dans l'onglet précédent.")
        else:
            with st.spinner("Analyse du plein potentiel de vos cartes et calcul de l'équipe optimale..."):
                try:
                    # 1. Préparation des données de la box
                    contexte_box = ""
                    for p in st.session_state.box:
                        contexte_box += f"\n- {p['nom']} (Type: {p['type']}, Rareté dans la box: {p['rarete']}, Doublons: {p['doublons']})\n"
                        # Extraction des infos si l'URL est fournie
                        texte_scrappe = scrape_dokkan_card(p.get('url', ''))
                        if texte_scrappe:
                            contexte_box += f"  Stats/Passif/Liens: {texte_scrappe}\n"

                    # 2. Construction du System Prompt ultra strict
                    instructions = (
                        "Tu es le meilleur théorycrafteur et expert mondial du jeu Dragon Ball Z: Dokkan Battle.\n"
                        "RÈGLES ABSOLUES ET IMPÉRATIVES :\n"
                        "1. LANGUE : Tu dois t'exprimer EXCLUSIVEMENT en français, avec le vocabulaire officiel du jeu.\n"
                        "2. RESPECT STRICT DE LA BOX : Tu dois former une équipe de 6 personnages choisis UNIQUEMENT "
                        "parmi la liste fournie par l'utilisateur. Seul le 7ème personnage ('Ami Leader') peut être extérieur à la box.\n"
                        "3. PLEIN POTENTIEL (RÈGLE D'OR) : Ne juge JAMAIS une carte sur sa rareté actuelle. "
                        "Si l'utilisateur a une carte notée 'SSR', évalue-la à son plein potentiel maximum possible (Éveil Dokkan UR ou LR, ainsi que Z-TUR ou Super Z-TUR si disponible dans le jeu). "
                        "Si tu intègres à l'équipe une carte qui est actuellement 'SSR' dans la box de l'utilisateur, tu dois OBLIGATOIREMENT "
                        "ajouter cette mention exacte à côté de son nom : '⚠️ À éveiller en UR/LR / Z-TUR pour ce combat'.\n"
                        "4. STRATÉGIE : Pense à la survie (Garde, Réduction de Dégâts, Esquive, Stack de DEF) face aux mécaniques spécifiques du boss ciblé.\n\n"
                        "FORMAT DE RÉPONSE EXIGÉ (Markdown clair) :\n"
                        "🏆 Leader (Préciser le % du Leader Skill)\n"
                        "👥 Sous-unités (Les 5 autres membres de la box)\n"
                        "🤝 Ami Leader (Le meilleur allié possible pour accompagner)\n"
                        "🔄 Rotations (Rotation 1 : Slot 1 et 2 | Rotation 2 : Slot 1 et 2)\n"
                        "🎈 Flotteurs (Les 3 unités en Slot 3)\n"
                        "📜 Stratégie (Explication des synergies, qui encaisse les attaques, gestion des objets de soutien comme Whis/Icarus)."
                    )

                    # 3. Prompt utilisateur
                    prompt_utilisateur = f"""
                    **Boss cible :** {st.session_state.nom_boss}
                    **Détails du boss :** {st.session_state.details_boss}

                    **Ma Box (Inventaire STRICT - Pioche uniquement 6 personnages ici) :**
                    {contexte_box}
                    """

                    # 4. Appel API sécurisé
                    client = genai.Client(api_key=api_key)
                    reponse = client.models.generate_content(
                        model='gemini-2.5-pro',
                        contents=prompt_utilisateur,
                        config=types.GenerateContentConfig(
                            system_instruction=instructions,
                            temperature=0.2 # Très analytique
                        )
                    )

                    st.success("✅ Analyse terminée avec succès !")
                    st.markdown("---")
                    st.markdown(reponse.text)

                except Exception as e:
                    # Sécurisation absolue : Remplacement de l'API key par des étoiles si elle fuite dans l'erreur réseau
                    message_erreur = str(e)
                    if api_key:
                        message_erreur = message_erreur.replace(api_key, "******")
                    st.error(f"❌ Une erreur système est survenue : {message_erreur}")
