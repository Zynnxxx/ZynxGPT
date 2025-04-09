import os
import logging
import json
from dotenv import load_dotenv
import discord
from discord.ext import commands
import google.generativeai as genai
import datetime
from datetime import timezone

# Configuration logging (inchangé)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')

# --- Constantes et Chargement Initial ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))
PERSONAS_FILE = "personas.json"
CONTEXT_TIMEOUT_MINUTES = 2
MAX_HISTORY_ITEMS = 20

# Initialisation Gemini (inchangé)
genai.configure(api_key=GEMINI_API_KEY)
try: model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e: logging.error(f"Erreur init Gemini: {e}"); model = None

# !!! PAS DE PERSONAS GLOBAL ICI !!!

# --- Fonctions de Gestion (prennent bot en argument) ---
def load_personas(bot_ref: commands.Bot):
    """Charge les personnalités depuis les fichiers dans bot_ref.personas."""
    logging.info("Début chargement personnalités...")
    # Initialise avec une structure de base au cas où tout échoue
    bot_ref.personas = {
        "default": {"name": "Fent-Droid (Défaut)", "description": "Base", "prompt": "IA de base."}
    }
    # Charger prompt.txt pour default
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            default_prompt = f.read().strip()
            if default_prompt:
                bot_ref.personas["default"]["prompt"] = default_prompt
                logging.info("Prompt default chargé depuis prompt.txt.")
            else: logging.warning("prompt.txt vide.")
    except FileNotFoundError: logging.warning("prompt.txt non trouvé.")
    except Exception as e: logging.error(f"Erreur lecture prompt.txt: {e}")

    # Charger personas.json et fusionner
    try:
        if os.path.exists(PERSONAS_FILE):
            logging.info(f"Chargement {PERSONAS_FILE}...")
            with open(PERSONAS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    # S'assurer que chaque valeur est un dict
                    valid_personas = {k: v for k, v in loaded.items() if isinstance(v, dict)}
                    # Fusionner intelligemment: la version chargée écrase, sauf pour 'default' où on garde le prompt déjà chargé si celui du fichier manque.
                    default_in_file = valid_personas.pop('default', None) # Retire 'default' du fichier pour le traiter séparément
                    bot_ref.personas.update(valid_personas) # Met à jour avec les autres personas
                    if default_in_file:
                        # Met à jour 'default' depuis le fichier, mais garde le prompt de prompt.txt si le fichier n'en a pas
                        if 'prompt' not in default_in_file or not default_in_file['prompt']:
                            default_in_file['prompt'] = bot_ref.personas['default']['prompt']
                        bot_ref.personas['default'].update(default_in_file) # Met à jour 'default' avec les infos du fichier

                    logging.info(f"{len(valid_personas)} (+default) personnalités chargées/mises à jour depuis {PERSONAS_FILE}.")
                else: logging.warning(f"Format incorrect {PERSONAS_FILE}.")
            logging.info(f"Clés dans bot.personas après chargement : {list(bot_ref.personas.keys())}")
        else:
            logging.info(f"{PERSONAS_FILE} non trouvé. Création avec default seulement.")
            save_personas(bot_ref) # Sauvegarde l'état actuel (juste default)
    except json.JSONDecodeError as e: logging.error(f"Erreur JSON {PERSONAS_FILE}: {e}")
    except Exception as e: logging.error(f"Erreur chargement {PERSONAS_FILE}: {e}")


def save_personas(bot_ref: commands.Bot):
    """Sauvegarde le contenu de bot_ref.personas dans le fichier JSON."""
    try:
        logging.info(f"Sauvegarde de bot.personas dans {PERSONAS_FILE}...")
        # S'assure qu'on a bien un dictionnaire à sauvegarder
        personas_to_save = getattr(bot_ref, 'personas', {})
        if not isinstance(personas_to_save, dict):
             logging.error(f"Tentative de sauvegarde d'un type invalide pour personas: {type(personas_to_save)}")
             return # Ne pas sauvegarder si ce n'est pas un dict

        with open(PERSONAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(personas_to_save, f, ensure_ascii=False, indent=4)
        logging.info(f"Sauvegarde réussie. Clés actuelles dans bot.personas: {list(personas_to_save.keys())}")
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde de bot.personas: {e}")


def format_history_for_prompt(history):
    # ... (fonction inchangée) ...
    if not history: return "Pas d'historique récent."
    formatted = ""
    for msg in history:
        role = msg.get("role", "unknown").replace("model", "Fent-Droid").replace("user", "User")
        parts = msg.get("parts", [""])
        content = " ".join(parts)
        formatted += f"{role}: {content}\n"
    return formatted.strip()

# --- Initialisation Bot et État sur l'Instance ---
intents = discord.Intents.default(); intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)

# Initialiser les attributs d'état sur l'instance bot AVANT de charger les personas
bot.personas = {} # Initialisation importante
bot.active_persona_id = "default" # Défaut initial
bot.conversation_history = []
bot.last_message_timestamp = None

# Charger les personnalités DANS l'attribut bot.personas
load_personas(bot)

# Vérifier et corriger l'ID actif initial si nécessaire après chargement
if bot.active_persona_id not in bot.personas:
    logging.warning(f"ID actif initial '{bot.active_persona_id}' invalide après chargement. Retour à 'default'.")
    bot.active_persona_id = "default"
    if "default" not in bot.personas:
         logging.critical("ERREUR: Personnalité 'default' non trouvée après chargement initial !")
         # Que faire ici? Le bot risque de ne pas marcher.
         # On peut créer un default minimal en dernier recours.
         bot.personas['default'] = {"name":"Fallback Default","description":"Fallback","prompt":"Fallback IA"}
         bot.active_persona_id = "default"

logging.info(f"État initialisé: Persona='{bot.active_persona_id}', History=[], Timestamp=None")
logging.info(f"Clés Personas initiales sur bot: {list(bot.personas.keys())}")

# --- Événements Discord ---
@bot.event
async def on_ready():
    # ... (code on_ready inchangé, appelle setup_commands(bot)) ...
    logging.info(f'Bot connecté: {bot.user}')
    if not DISCORD_TOKEN or not GEMINI_API_KEY or not model: await bot.close(); return
    from commands import setup as setup_commands
    try: setup_commands(bot); logging.info("Commandes chargées.")
    except Exception as e: logging.exception("Erreur chargement commandes:")
    try: synced = await bot.tree.sync(); logging.info(f"Commandes sync ({len(synced)})")
    except Exception as e: logging.error(f"Erreur sync commandes: {e}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="vos messages"))
    logging.info(f"Bot prêt. État: bot.active_persona_id: {bot.active_persona_id}, bot.personas keys: {list(bot.personas.keys())}")


@bot.event
async def on_message(message):
    # ... (vérifications initiales: bot, DM) ...
    if message.author == bot.user or isinstance(message.channel, discord.DMChannel): return

    # --- Vérification Timeout (Lit bot.last_message_timestamp) ---
    now = datetime.datetime.now(timezone.utc)
    reset_due_to_timeout = False # Flag pour savoir si on a reset
    if bot.last_message_timestamp:
        time_diff = now - bot.last_message_timestamp
        if time_diff > datetime.timedelta(minutes=CONTEXT_TIMEOUT_MINUTES):
            logging.info(f"Inactivité détectée ({time_diff}). Reset historique et persona.")
            bot.conversation_history = []
            bot.active_persona_id = "default"
            reset_due_to_timeout = True # Marquer qu'on a reset ici
            # Le timestamp sera mis à jour à la fin si on répond.
    # -------------------------------------------

    # ... (logique should_respond / user_message) ...
    should_respond = False; user_message = message.content
    # ... (code pour déterminer should_respond et user_message) ...
    if bot.user.mentioned_in(message):
        should_respond = True; user_message = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if not user_message: return
    elif TARGET_CHANNEL_ID != 0 and message.channel.id == TARGET_CHANNEL_ID: should_respond = True
    if not should_respond: return
    if not model: await message.channel.send("Cerveau IA non dispo."); return

    try:
        # --- Lecture État depuis l'Instance Bot ---
        current_persona_id = bot.active_persona_id
        personas_dict = bot.personas # Utilise le dictionnaire sur l'instance bot
        logging.info(f"Réponse avec persona_id='{current_persona_id}' depuis bot.personas")

        # Vérification et récupération des données (depuis bot.personas)
        if current_persona_id in personas_dict:
            active_persona_data = personas_dict[current_persona_id]
            retrieved_id_for_log = current_persona_id
        else:
            # Si l'ID actif n'est pas/plus valide, fallback 'default'
            logging.warning(f"ID actif '{current_persona_id}' NON TROUVÉ dans bot.personas ({list(personas_dict.keys())}). Fallback 'default'.")
            active_persona_data = personas_dict.get("default")
            if not active_persona_data:
                 logging.error("CRITIQUE: 'default' non trouvé dans bot.personas pour fallback.")
                 await message.channel.send("Erreur config personnalité (default manquant).")
                 return
            # Corriger l'ID actif sur le bot pour la prochaine fois
            bot.active_persona_id = "default"
            retrieved_id_for_log = "default (fallback)"

        logging.info(f"Données utilisées: ID={retrieved_id_for_log}")
        active_prompt = active_persona_data.get("prompt", "Prompt manquant.")

        # --- Construction Prompt avec Historique (depuis bot.conversation_history) ---
        history_string = format_history_for_prompt(bot.conversation_history)
        contextual_prompt = f"{active_prompt}\n\n--- HISTORIQUE ---\n{history_string}\n--- FIN HISTORIQUE ---\n\nMsg ({message.author.display_name}): {user_message}\n\nFent-Droid:"
        logging.info(f"Prompt Gemini (début): {contextual_prompt[:300]}...")

        # --- Génération Réponse & Mise à Jour État Bot ---
        async with message.channel.typing():
            response = await model.generate_content_async(contextual_prompt)
            if not response.parts: # Gérer réponse bloquée/vide
                 logging.warning(f"Réponse Gemini bloquée/vide pour: '{user_message}'"); await message.channel.send("Je... bloque."); return
            response_text = response.text

            # Mise à jour historique (sur bot.conversation_history)
            bot.conversation_history.append({"role": "user", "parts": [user_message]})
            bot.conversation_history.append({"role": "model", "parts": [response_text]})
            # Limiter taille historique
            if len(bot.conversation_history) > MAX_HISTORY_ITEMS:
                bot.conversation_history = bot.conversation_history[-MAX_HISTORY_ITEMS:]
                logging.info(f"Historique limité à {MAX_HISTORY_ITEMS} items.")

            # Mise à jour timestamp (sur bot.last_message_timestamp)
            bot.last_message_timestamp = datetime.datetime.now(timezone.utc)
            logging.info(f"Interaction réussie. Timestamp mis à jour. Longueur historique: {len(bot.conversation_history)}")

            # Envoi réponse (inchangé)
            chunks = [response_text[i:i+2000] for i in range(0, len(response_text), 2000)]
            # ... (envoi chunks) ...
            if chunks: await message.reply(chunks[0], mention_author=False)
            for chunk in chunks[1:]: await message.channel.send(chunk)

    # ... (except KeyError, Exception) ...
    except KeyError as e: logging.exception(f"Clé persona non trouvée: {e}"); await message.channel.send("Erreur config personnalité.")
    except Exception as e: logging.exception("Erreur inattendue on_message:"); await message.channel.send("Erreur système Fent-Droid.")

# --- Lancement Bot (inchangé) ---
if __name__ == "__main__":
    # ... (vérifications token/api key) ...
    if not DISCORD_TOKEN or not GEMINI_API_KEY: print("ERREUR CRITIQUE: .env")
    else:
        try: bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure: logging.critical("TOKEN DISCORD INVALIDE ?")
        except Exception as e: logging.critical(f"Erreur fatale lancement: {e}")