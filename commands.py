import discord
from discord.ext import commands
import bot as bot_module_for_functions
import datetime
from datetime import timezone
import logging

def setup(bot_instance: commands.Bot):
    """Configure les commandes slash pour le bot."""
    logging.info("Configuration des commandes slash...")
    
    @bot_instance.tree.command(name="help", description="Affiche la liste des commandes disponibles")
    async def help_command(interaction: discord.Interaction):
        embed = discord.Embed(
            title="Aide de Fent-Droid",
            description="Voici les commandes que vous pouvez utiliser:",
            color=0x3498db
        )
        embed.add_field(name="/help", value="Affiche ce message d'aide.", inline=False)
        embed.add_field(name="/ping", value="Vérifie la latence du bot.", inline=False)
        embed.add_field(name="/personas", value="Affiche les personnalités disponibles.", inline=False)
        embed.add_field(name="/persona_set", value="Change la personnalité active du bot.",
                        inline=False)
        embed.add_field(name="/persona_create", value="Crée une nouvelle personnalité.",
                        inline=False)
        embed.add_field(name="/persona_edit", value="Modifie le nom, la description ou le prompt d'une personnalité.",
                        inline=False)
        embed.add_field(name="/persona_delete", value="Supprime une personnalité existante.",
                        inline=False)


        embed.set_footer(text="Fent-Droid - Votre assistant IA pour autistes.")
        await interaction.response.send_message(embed=embed)

    @bot_instance.tree.command(name="ping", description="Vérifiez la latence du bot")
    async def ping_command(interaction: discord.Interaction): # ... code ...
        latency = round(bot_instance.latency * 1000); await interaction.response.send_message(f"Pong! Latence: {latency}ms.")

    @bot_instance.tree.command(name="personas", description="Affiche les personnalités disponibles")
    async def personas_command(interaction: discord.Interaction):
        logging.info(f"Commande /personas reçue de {interaction.user}")
        try:
            embed = discord.Embed(
                title="Personnalités de Zynx GPT",
                description=f"Personnalité active : **{bot_instance.active_persona_id}**",
                color=0x3498db
            )
            personas_dict = getattr(bot_instance, 'personas', {})
            if not personas_dict:
                 embed.add_field(name="Aucune personnalité trouvée", value="L'attribut personas du bot semble vide.", inline=False)
            else:
                for persona_id, persona_data in personas_dict.items():
                    embed.add_field(
                        name=f"{persona_data.get('name', persona_id)} ({persona_id})",
                        value=persona_data.get('description', 'N/A'),
                        inline=False
                    )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logging.exception("Erreur dans /personas:")
            try: await interaction.response.send_message("Impossible d'afficher les personnalités.", ephemeral=True)
            except discord.errors.InteractionResponded: await interaction.followup.send("Impossible d'afficher les personnalités.", ephemeral=True)


    @bot_instance.tree.command(name="persona_set", description="Change la personnalité active du bot.")
    async def persona_set_command(interaction: discord.Interaction, persona_id: str):
        logging.info(f"Commande /persona_set reçue de {interaction.user} pour ID: {persona_id}")
        await interaction.response.defer(ephemeral=False)
        try:
            if persona_id not in bot_instance.personas:
                logging.warning(f"/persona_set: ID '{persona_id}' non trouvé dans bot.personas {list(bot_instance.personas.keys())}")
                await interaction.followup.send(f"Erreur : ID '{persona_id}' introuvable.", ephemeral=True); return
            bot_instance.active_persona_id = persona_id
            persona_name = bot_instance.personas[persona_id].get("name", persona_id)
            logging.info(f"/persona_set: bot_instance.active_persona_id -> {bot_instance.active_persona_id}")
            bot_instance.conversation_history = []
            bot_instance.last_message_timestamp = datetime.datetime.now(timezone.utc)
            logging.info("/persona_set: Historique et timestamp sur bot_instance réinitialisés.")

            await interaction.followup.send(f"OK. Personnalité -> **{persona_name}** ({persona_id}).\n*Mémoire conversationnelle réinitialisée.*")
        except Exception as e:
            logging.exception(f"Erreur /persona_set ID '{persona_id}':"); await interaction.followup.send("Erreur changement personnalité.", ephemeral=True)


    @bot_instance.tree.command(name="persona_create", description="Crée une nouvelle personnalité.")
    async def persona_create_command(
            interaction: discord.Interaction,
            persona_id: str, name: str, description: str, prompt: str
    ):
        logging.info(f"Commande /persona_create reçue de {interaction.user} pour ID: {persona_id}")
        await interaction.response.defer(ephemeral=False)
        try:
            if persona_id in bot_instance.personas:
                 await interaction.followup.send(f"Erreur: ID '{persona_id}' existe déjà.", ephemeral=True); return
            if not persona_id.replace("_", "").isalnum() or not persona_id:
                 await interaction.followup.send("Erreur: ID invalide.", ephemeral=True); return
                
            final_prompt = prompt.strip() if prompt and prompt.strip() else bot_instance.personas.get("default", {}).get("prompt", "Erreur prompt default.")
            prompt_msg = "Prompt fourni." if prompt and prompt.strip() else "Prompt défaut utilisé."

            bot_instance.personas[persona_id] = {"name": name, "description": description, "prompt": final_prompt}
            logging.info(f"/persona_create: Persona '{persona_id}' ajoutée à bot.personas. Clés: {list(bot_instance.personas.keys())}")

            try:
                bot_module_for_functions.save_personas(bot_instance)
            except Exception as e:
                logging.error(f"/persona_create: Échec save_personas pour '{persona_id}': {e}")
                await interaction.followup.send("Erreur sauvegarde nouvelle personnalité.", ephemeral=True); return


            await interaction.followup.send(f"Personnalité '{name}' ({persona_id}) créée. {prompt_msg}")
        except Exception as e:
             logging.exception(f"Erreur /persona_create ID '{persona_id}':"); await interaction.followup.send("Erreur création.", ephemeral=True)

    
    @bot_instance.tree.command(name="persona_edit", description="Modifie nom, descricption ou prompt d'une personnalité")
    async def persona_edit_command(
            interaction: discord.Interaction,
            persona_id: str, name: str = None, description: str = None, prompt: str = None
    ):
        logging.info(f"Commande /persona_edit reçue de {interaction.user} pour ID: {persona_id}")
        await interaction.response.defer(ephemeral=False)
        try:
            if persona_id not in bot_instance.personas:
                 await interaction.followup.send(f"Erreur: ID '{persona_id}' inconnu.", ephemeral=True); return
            if persona_id == "default":
                 await interaction.followup.send("Erreur: 'default' non modifiable.", ephemeral=True); return

            persona = bot_instance.personas[persona_id]; changes = []; prompt_changed = False
            if name is not None: persona["name"] = name; changes.append("nom")
            if description is not None: persona["description"] = description; changes.append("description")
            if prompt is not None: persona["prompt"] = prompt.strip(); changes.append("prompt"); prompt_changed = True

            if changes:
                logging.info(f"/persona_edit: Modifications pour '{persona_id}': {', '.join(changes)}. Sauvegarde...")
                try:
                    bot_module_for_functions.save_personas(bot_instance)
                except Exception as e:
                     logging.error(f"/persona_edit: Échec sauvegarde '{persona_id}': {e}")
                     await interaction.followup.send("Erreur sauvegarde après édition.", ephemeral=True); return


                reset_msg = ""
                if prompt_changed and persona_id == bot_instance.active_persona_id:
                     bot_instance.conversation_history = []; bot_instance.last_message_timestamp = datetime.datetime.now(timezone.utc)
                     reset_msg = "\n*Mémoire réinitialisée car le prompt actif a changé.*"
                     logging.info(f"/persona_edit: Historique réinitialisé car prompt actif ('{persona_id}') modifié.")

                await interaction.followup.send(f"OK. '{persona_id}' modifiée: {', '.join(changes)}.{reset_msg}")
            else:
                await interaction.followup.send("Aucun changement spécifié.", ephemeral=True)
        except Exception as e: 
            logging.exception(f"Erreur /persona_edit ID '{persona_id}':"); await interaction.followup.send("Erreur modification.", ephemeral=True)

    logging.info("Commandes slash configurées.")


    @bot_instance.tree.command(name="persona_delete", description="Supprime une personnalité existante (sauf 'default')")
    async def persona_delete_command(interaction: discord.Interaction, persona_id: str):
        """Supprime une personnalité spécifiée par son ID."""
        logging.info(f"Commande /persona_delete reçue de {interaction.user} pour ID: {persona_id}")
        await interaction.response.defer(ephemeral=False)

        try:
            if persona_id not in bot_instance.personas:
                logging.warning(f"/persona_delete: ID '{persona_id}' non trouvé.")
                await interaction.followup.send(f"Erreur : Personnalité '{persona_id}' introuvable.", ephemeral=True)
                return

            if persona_id == "default":
                logging.warning(f"/persona_delete: Tentative de suppression de 'default' refusée.")
                await interaction.followup.send("Erreur : La personnalité 'default' est essentielle et ne peut pas être supprimée.", ephemeral=True)
                return

            deleted_persona_name = bot_instance.personas[persona_id].get('name', persona_id)

            del bot_instance.personas[persona_id]
            logging.info(f"/persona_delete: Persona '{persona_id}' supprimée de bot.personas.")

            try:
                bot_module_for_functions.save_personas(bot_instance)
            except Exception as e:
                logging.error(f"/persona_delete: Échec de save_personas après suppression de '{persona_id}': {e}")
                await interaction.followup.send(
                    "ERREUR CRITIQUE : La personnalité a été supprimée en mémoire mais la sauvegarde a échoué. "
                    "L'état est incohérent. Contactez un administrateur.",
                    ephemeral=True
                ).
                return

            reset_msg = ""
            if bot_instance.active_persona_id == persona_id:
                logging.info(f"/persona_delete: La personnalité active '{persona_id}' a été supprimée. Retour à 'default'.")
                bot_instance.active_persona_id = "default"
                bot_instance.conversation_history = []
                bot_instance.last_message_timestamp = datetime.datetime.now(timezone.utc)
                reset_msg = f"\nComme c'était la personnalité active, retour à 'default' et réinitialisation de la mémoire."

            await interaction.followup.send(
                f"Personnalité '{deleted_persona_name}' ({persona_id}) supprimée avec succès.{reset_msg}"
            )

        except Exception as e:
            logging.exception(f"Erreur inattendue dans /persona_delete pour ID '{persona_id}':")
            try:
                await interaction.followup.send("Une erreur est survenue lors de la suppression de la personnalité.", ephemeral=True)
            except discord.errors.NotFound:
                logging.error("Impossible d'envoyer l'erreur followup pour /persona_delete.")

