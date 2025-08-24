import os
import discord
from discord import app_commands
from discord.ext import commands
from keep_alive import keep_alive
import random
import asyncio

# --- TOKEN ET INTENTS ---
token = os.environ['TOKEN_BOT_DISCORD']

# Remplacer les IDs par les vôtres
ID_SALON_LOTERIE = 1366369136648654871
ID_CROUPIER = 1401471414262829066
ID_ROLE_ALERTE_LOTERIE = 1366378672281620495

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# Dictionnaire pour stocker les loteries en cours
loteries = {}

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)

# Vue pour le bouton "Participer"
class LoterieView(discord.ui.View):
    def __init__(self, message_id, montant):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.montant = montant
        self.participants = set()

        self.participer_button = discord.ui.Button(label="🎟️ Participer", style=discord.ButtonStyle.green, custom_id="participer_loterie")
        self.participer_button.callback = self.participer
        self.add_item(self.participer_button)

    async def participer(self, interaction: discord.Interaction):
        if interaction.user.id in self.participants:
            await interaction.response.send_message("❌ Tu es déjà inscrit à cette loterie.", ephemeral=True)
            return

        self.participants.add(interaction.user.id)
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Participants", value=f"{len(self.participants)} participant(s)", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ Tu as bien été inscrit à la loterie.", ephemeral=True)
        
        loteries[self.message_id]["participants"] = self.participants

# Vue pour le croupier avec le bouton "Tirer au sort"
class CroupierView(discord.ui.View):
    def __init__(self, message_id, participants, montant):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.participants = participants
        self.montant = montant

        self.tirer_au_sort_button = discord.ui.Button(label="🎰 Tirer au sort", style=discord.ButtonStyle.success, custom_id="tirer_loterie")
        self.tirer_au_sort_button.callback = self.tirer_au_sort
        self.add_item(self.tirer_au_sort_button)

    async def tirer_au_sort(self, interaction: discord.Interaction):
        role_croupier = interaction.guild.get_role(ID_CROUPIER)
        if not role_croupier or role_croupier not in interaction.user.roles:
            await interaction.response.send_message("❌ Tu n'as pas la permission de `croupier` pour lancer le tirage.", ephemeral=True)
            return

        if not self.participants:
            await interaction.response.send_message("❌ Il n'y a aucun participant inscrit.", ephemeral=True)
            return

        # Désactiver le bouton
        self.tirer_au_sort_button.disabled = True
        await interaction.response.edit_message(view=self)

        participants_list = list(self.participants)
        gagnant = None
        
        while participants_list:
            gagnant_id = random.choice(participants_list)
            
            try:
                gagnant = await interaction.guild.fetch_member(gagnant_id)
                if gagnant:
                    break
            except discord.NotFound:
                participants_list.remove(gagnant_id)
            except Exception:
                participants_list.remove(gagnant_id)

        if not gagnant:
            await interaction.followup.send("❌ Aucun participant valide n'a pu être trouvé. Le tirage est annulé.")
            del loteries[self.message_id]
            return

        montant_total = self.montant
        
        # Créer la mention de rôle
        role_a_ping_resultat = f"<@&{ID_ROLE_ALERTE_LOTERIE}>"

        result_embed = discord.Embed(
            title="🎉 Le grand gagnant est...",
            description=f"Le tirage de la loterie a eu lieu !",
            color=discord.Color.gold()
        )
        result_embed.add_field(name="Gagnant", value=f"{gagnant.mention}", inline=False)
        result_embed.add_field(name="Somme remportée", value=f"**{montant_total:,.0f}".replace(",", " ") + " kamas** 💰", inline=False)
        result_embed.set_footer(text="Félicitations au gagnant !")
        
        await interaction.followup.send(content=f"{gagnant.mention} Félicitations ! 🎉 {role_a_ping_resultat}", embed=result_embed)
        
        del loteries[self.message_id]
        
# --- COMMANDES ---

@bot.tree.command(name="loterie", description="Lancer une loterie.")
@app_commands.describe(montant="Montant total des kamas à gagner")
@app_commands.checks.has_role(ID_CROUPIER)
async def loterie(interaction: discord.Interaction, montant: int):
    if interaction.channel.id != ID_SALON_LOTERIE:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon de la loterie.", ephemeral=True)
        return

    if montant <= 0:
        await interaction.response.send_message("❌ Le montant doit être supérieur à 0.", ephemeral=True)
        return

    if loteries:
        await interaction.response.send_message("❌ Une loterie est déjà en cours. Attendez qu'elle se termine avant d'en lancer une nouvelle.", ephemeral=True)
        return

    # Créer la mention de rôle
    role_a_ping_lancement = f"<@&{ID_ROLE_ALERTE_LOTERIE}>"

    embed = discord.Embed(
        title="🎰 Nouvelle Loterie !",
        description=f"**{interaction.user.mention}** a lancé une loterie avec **{montant:,.0f}".replace(",", " ") + " kamas** à gagner. "
                     "La participation est gratuite ! Clique sur le bouton ci-dessous pour tenter de gagner la cagnotte !",
        color=discord.Color.gold()
    )
    embed.add_field(name="Participants", value="0 participant(s)", inline=False)

    view = LoterieView(None, montant)
    
    await interaction.response.send_message(
        content=f"{role_a_ping_lancement}",
        embed=embed,
        view=view,
        ephemeral=False,
    )

    sent_message = await interaction.original_response()
    
    loteries[sent_message.id] = {
        "montant": montant,
        "participants": set(),
        "croupier_view_sent": False
    }
    view.message_id = sent_message.id
    
@bot.tree.command(name="participants", description="Affiche la liste des participants de la loterie en cours.")
async def participants(interaction: discord.Interaction):
    if interaction.channel.id != ID_SALON_LOTERIE:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon de la loterie.", ephemeral=True)
        return

    if not loteries:
        await interaction.response.send_message("❌ Il n'y a aucune loterie en cours.", ephemeral=True)
        return

    message_id = list(loteries.keys())[0]
    loterie_data = loteries[message_id]
    
    participants_list = loterie_data.get("participants", set())
    
    if not participants_list:
        await interaction.response.send_message("Il n'y a pas encore de participants inscrits.", ephemeral=True)
        return
        
    participants_mentions = [f"<@{user_id}>" for user_id in participants_list]
    participants_str = "\n".join(participants_mentions)
    
    embed = discord.Embed(
        title="Liste des participants",
        description=f"**{len(participants_list)} participant(s) inscrit(s)**",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Participants", value=participants_str, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="terminer_inscriptions", description="Termine les inscriptions de la loterie et passe à la phase de tirage.")
@app_commands.checks.has_role(ID_CROUPIER)
async def terminer_inscriptions(interaction: discord.Interaction):
    if interaction.channel.id != ID_SALON_LOTERIE:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon de la loterie.", ephemeral=True)
        return

    if not loteries:
        await interaction.response.send_message("❌ Il n'y a aucune loterie en cours à terminer.", ephemeral=True)
        return

    message_id = list(loteries.keys())[0]
    loterie_data = loteries[message_id]

    if loterie_data.get("croupier_view_sent"):
        await interaction.response.send_message("❌ La phase de tirage a déjà été lancée pour cette loterie.", ephemeral=True)
        return
        
    original_message = await interaction.channel.fetch_message(message_id)
    participants = loterie_data["participants"]
    montant = loterie_data["montant"]

    tirage_embed = discord.Embed(
        title="🎰 Inscriptions Terminées !",
        description=f"La loterie avec **{montant:,.0f}".replace(",", " ") + " kamas** à gagner est prête à être tirée au sort.",
        color=discord.Color.green()
    )
    tirage_embed.add_field(name="Participants", value=f"{len(participants)} participant(s)", inline=False)
    tirage_embed.set_footer(text="Un croupier doit cliquer sur le bouton pour lancer le tirage.")
    
    croupier_view = CroupierView(message_id, participants, montant)

    await original_message.edit(embed=tirage_embed, view=croupier_view)
    
    loteries[message_id]["croupier_view_sent"] = True
    
    await interaction.response.send_message("✅ Inscriptions terminées. Un croupier peut maintenant lancer le tirage.", ephemeral=False)

@bot.event
async def on_ready():
    print(f"{bot.user} est prêt !")
    try:
        await bot.tree.sync()
        print("✅ Commandes synchronisées.")
    except Exception as e:
        print(f"Erreur : {e}")

keep_alive()
bot.run(token)
