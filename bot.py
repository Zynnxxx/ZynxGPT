import os
import logging
import json
from dotenv import load_dotenv
import discord
from discord.ext import commands
import google.generativeai as genai
import datetime
from datetime import timezone


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))
PERSONAS_FILE = "personas.json"
CONTEXT_TIMEOUT_MINUTES = 2
MAX_HISTORY_ITEMS = 20

genai.configure(api_key=GEMINI_API_KEY)
try: model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e: logging.error(f"Erreur init Gemini: {e}"); model = None


def load_personas(bot_ref: commands.Bot):
    """Charge les personnalités depuis les fichiers dans bot_ref.personas."""
    logging.info("Début chargement personnalités...")

    bot_ref.personas = {
        "default": {"name": "Fent-Droid (Défaut)", "description": "Base", "prompt": "IA de base."}
    }

    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            default_prompt = f.read().strip()
            if default_prompt:
                bot_ref.personas["default"]["prompt"] = default_prompt
                logging.info("Prompt default chargé depuis prompt.txt.")
            else: logging.warning("prompt.txt vide.")
    except FileNotFoundError: logging.warning("prompt.txt non trouvé.")
    except Exception as e: logging.error(f"Erreur lecture prompt.txt: {e}")

    try:
        if os.path.exists(PERSONAS_FILE):
            logging.info(f"Chargement {PERSONAS_FILE}...")
            with open(PERSONAS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    
                    valid_personas = {k: v for k, v in loaded.items() if isinstance(v, dict)}
                    default_in_file = valid_personas.pop('default', None) 
                    bot_ref.personas.update(valid_personas) 
                    if default_in_file:
                        if 'prompt' not in default_in_file or not default_in_file['prompt']:
                            default_in_file['prompt'] = bot_ref.personas['default']['prompt']
                        bot_ref.personas['default'].update(default_in_file)

                    logging.info(f"{len(valid_personas)} (+default) personnalités chargées/mises à jour depuis {PERSONAS_FILE}.")
                else: logging.warning(f"Format incorrect {PERSONAS_FILE}.")
            logging.info(f"Clés dans bot.personas après chargement : {list(bot_ref.personas.keys())}")
        else:
            logging.info(f"{PERSONAS_FILE} non trouvé. Création avec default seulement.")
            save_personas(bot_ref)
    except json.JSONDecodeError as e: logging.error(f"Erreur JSON {PERSONAS_FILE}: {e}")
    except Exception as e: logging.error(f"Erreur chargement {PERSONAS_FILE}: {e}")


def save_personas(bot_ref: commands.Bot):
    """Sauvegarde le contenu de bot_ref.personas dans le fichier JSON."""
    try:
        logging.info(f"Sauvegarde de bot.personas dans {PERSONAS_FILE}...")
        personas_to_save = getattr(bot_ref, 'personas', {})
        if not isinstance(personas_to_save, dict):
             logging.error(f"Tentative de sauvegarde d'un type invalide pour personas: {type(personas_to_save)}")
             return

        with open(PERSONAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(personas_to_save, f, ensure_ascii=False, indent=4)
        logging.info(f"Sauvegarde réussie. Clés actuelles dans bot.personas: {list(personas_to_save.keys())}")
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde de bot.personas: {e}")


def format_history_for_prompt(history):

    if not history: return "Pas d'historique récent."
    formatted = ""
    for msg in history:
        role = msg.get("role", "unknown").replace("model", "Fent-Droid").replace("user", "User")
        parts = msg.get("parts", [""])
        content = " ".join(parts)
        formatted += f"{role}: {content}\n"
    return formatted.strip()

intents = discord.Intents.default(); intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)


bot.personas = {} 
bot.active_persona_id = "default" 
bot.conversation_history = []
bot.last_message_timestamp = None

load_personas(bot)

if bot.active_persona_id not in bot.personas:
    logging.warning(f"ID actif initial '{bot.active_persona_id}' invalide après chargement. Retour à 'default'.")
    bot.active_persona_id = "default"
    if "default" not in bot.personas:
         logging.critical("ERREUR: Personnalité 'default' non trouvée après chargement initial !")
         bot.personas['default'] = {"name":"Fallback Default","description":"Fallback","prompt":"Fallback IA"}
         bot.active_persona_id = "default"

logging.info(f"État initialisé: Persona='{bot.active_persona_id}', History=[], Timestamp=None")
logging.info(f"Clés Personas initiales sur bot: {list(bot.personas.keys())}")

@bot.event
async def on_ready():
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
    if message.author == bot.user or isinstance(message.channel, discord.DMChannel): return

    now = datetime.datetime.now(timezone.utc)
    reset_due_to_timeout = False 
    if bot.last_message_timestamp:
        time_diff = now - bot.last_message_timestamp
        if time_diff > datetime.timedelta(minutes=CONTEXT_TIMEOUT_MINUTES):
            logging.info(f"Inactivité détectée ({time_diff}). Reset historique et persona.")
            bot.conversation_history = []
            bot.active_persona_id = "default"
            reset_due_to_timeout = True 

    should_respond = False; user_message = message.content
    if bot.user.mentioned_in(message):
        should_respond = True; user_message = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if not user_message: return
    elif TARGET_CHANNEL_ID != 0 and message.channel.id == TARGET_CHANNEL_ID: should_respond = True
    if not should_respond: return
    if not model: await message.channel.send("Cerveau IA non dispo."); return

    try:
        current_persona_id = bot.active_persona_id
        personas_dict = bot.personas
        logging.info(f"Réponse avec persona_id='{current_persona_id}' depuis bot.personas")

        if current_persona_id in personas_dict:
            active_persona_data = personas_dict[current_persona_id]
            retrieved_id_for_log = current_persona_id
        else:
            logging.warning(f"ID actif '{current_persona_id}' NON TROUVÉ dans bot.personas ({list(personas_dict.keys())}). Fallback 'default'.")
            active_persona_data = personas_dict.get("default")
            if not active_persona_data:
                 logging.error("CRITIQUE: 'default' non trouvé dans bot.personas pour fallback.")
                 await message.channel.send("Erreur config personnalité (default manquant).")
                 return
            bot.active_persona_id = "default"
            retrieved_id_for_log = "default (fallback)"

        logging.info(f"Données utilisées: ID={retrieved_id_for_log}")
        active_prompt = active_persona_data.get("prompt", "Prompt manquant.")

        history_string = format_history_for_prompt(bot.conversation_history)
        contextual_prompt = f"{active_prompt}\n\n--- HISTORIQUE ---\n{history_string}\n--- FIN HISTORIQUE ---\n\nMsg ({message.author.display_name}): {user_message}\n\nFent-Droid:"
        logging.info(f"Prompt Gemini (début): {contextual_prompt[:300]}...")

        async with message.channel.typing():
            response = await model.generate_content_async(contextual_prompt)
            if not response.parts:
                 logging.warning(f"Réponse Gemini bloquée/vide pour: '{user_message}'"); await message.channel.send("Je... bloque."); return
            response_text = response.text

            bot.conversation_history.append({"role": "user", "parts": [user_message]})
            bot.conversation_history.append({"role": "model", "parts": [response_text]})
            if len(bot.conversation_history) > MAX_HISTORY_ITEMS:
                bot.conversation_history = bot.conversation_history[-MAX_HISTORY_ITEMS:]
                logging.info(f"Historique limité à {MAX_HISTORY_ITEMS} items.")

            bot.last_message_timestamp = datetime.datetime.now(timezone.utc)
            logging.info(f"Interaction réussie. Timestamp mis à jour. Longueur historique: {len(bot.conversation_history)}")

            chunks = [response_text[i:i+2000] for i in range(0, len(response_text), 2000)]
            if chunks: await message.reply(chunks[0], mention_author=False)
            for chunk in chunks[1:]: await message.channel.send(chunk)

    except KeyError as e: logging.exception(f"Clé persona non trouvée: {e}"); await message.channel.send("Erreur config personnalité.")
    except Exception as e: logging.exception("Erreur inattendue on_message:"); await message.channel.send("Erreur système Fent-Droid.")

if __name__ == "__main__":
    if not DISCORD_TOKEN or not GEMINI_API_KEY: print("ERREUR CRITIQUE: .env")
    else:
        try: bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure: logging.critical("TOKEN DISCORD INVALIDE ?")
        except Exception as e: logging.critical(f"Erreur fatale lancement: {e}")

