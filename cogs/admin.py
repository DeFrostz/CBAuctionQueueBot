import discord

from discord.ext import commands

import asyncio

from choices import CATEGORY_CHOICES
from constants import CATEGORIES, LINKED, REWARD_NAMES, REWARD_TYPES
from database import (
    set_reward_stock,
    set_reward_limit,
    get_rewards,
    clear_queue,
    clear_rewards,
)

from generator import check_categories, generate_all

# Stock can still be configured separately per category.
SET_CATEGORY_CHOICES = [
    discord.app_commands.Choice(name=cat, value=cat)
    for cat in (*CATEGORIES, "All")
]

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="setallstock", description="Set stock for all three rewards at once"
    )
    @discord.app_commands.choices(category=SET_CATEGORY_CHOICES)
    @discord.app_commands.describe(
        card="Total Card stock", light_dark="Total Light-Dark stock",
        time_space="Total Time-Space stock", category="Which category to apply (All by default)",
    )
    async def setallstock(self, interaction: discord.Interaction, card: int, light_dark: int, time_space: int, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        stock_values = {"CARD": card, "FEATHER_S": light_dark, "FEATHER_A": time_space}
        if any(stock < 0 for stock in stock_values.values()):
            await interaction.response.send_message("❌ Stock must be 0 or greater for all rewards", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else "All"
        targets = list(CATEGORIES) if category_value == "All" else [category_value]
        for target in targets:
            for reward, stock in stock_values.items():
                set_reward_stock(guild_id, reward, stock, target)
        await interaction.response.send_message(
            "✅ All reward stock updated\n" f"🃏 Card: {card}\n" f"🌗 Light-Dark: {light_dark}\n"
            f"⏳ Time-Space: {time_space}\n" f"Applied to: {', '.join(targets)}"
        )

    @discord.app_commands.command(name="setalllimit", description="Set limits for all three rewards at once")
    @discord.app_commands.choices(category=CATEGORY_CHOICES)
    @discord.app_commands.describe(
        card="Card amount per queue (0 = Extra only)",
        light_dark="Light-Dark amount per queue (0 = Extra only)",
        time_space="Time-Space amount per queue (0 = Extra only)",
        category="Which category to apply. Guild League / League Prize are linked.",
    )
    async def setalllimit(self, interaction: discord.Interaction, card: int, light_dark: int, time_space: int, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        limit_values = {"CARD": card, "FEATHER_S": light_dark, "FEATHER_A": time_space}
        if any(limit < 0 for limit in limit_values.values()):
            await interaction.response.send_message("❌ Every limit must be 0 or greater", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else CATEGORIES[0]
        if category_value == "All":
            targets = list(CATEGORIES)
        elif category_value in LINKED:
            targets = list(LINKED)
        else:
            targets = [category_value]
        for target in targets:
            for reward, limit in limit_values.items():
                set_reward_limit(guild_id, reward, limit, target)
        await interaction.response.send_message(
            "✅ All queue limits updated\n" f"🃏 Card: {card}\n" f"🌗 Light-Dark: {light_dark}\n"
            f"⏳ Time-Space: {time_space}\n" f"Applied to: {', '.join(targets)}"
        )

    @discord.app_commands.command(name="checkconfig", description="View current reward stock and queue limits")
    @discord.app_commands.choices(category=CATEGORY_CHOICES)
    @discord.app_commands.describe(category="Which category to check (All by default)")
    async def checkconfig(self, interaction: discord.Interaction, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else "All"

        if category_value == "All":
            targets = list(CATEGORIES)
        elif category_value in LINKED:
            targets = list(LINKED)
        else:
            targets = [category_value]

        embed = discord.Embed(
            title="⚙️ Auction Configuration",
            description="Current reward stock and queue limits",
        )

        for target in targets:
            rewards = {
                row["reward_type"]: row
                for row in get_rewards(guild_id, target)
            }

            if not rewards:
                embed.add_field(
                    name=f"📂 {target}",
                    value="Not configured",
                    inline=False,
                )
                continue

            lines = []

            for reward in REWARD_TYPES:
                row = rewards.get(reward)

                if row is None:
                    lines.append(
                        f"{REWARD_NAMES[reward]}\n"
                        "Stock: Not configured\n"
                        "Limit / Queue: Not configured"
                    )
                    continue

                lines.append(
                    f"{REWARD_NAMES[reward]}\n"
                    f"Stock: **{row['stock']}**\n"
                    f"Limit / Queue: **{row['limit_per_queue']}**"
                )

            embed.add_field(
                name=f"📂 {target}",
                value="\n\n".join(lines),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.app_commands.command(name="clearqueues", description="Clear generated auction queues")
    @discord.app_commands.choices(category=CATEGORY_CHOICES)
    @discord.app_commands.describe(category="Which category to clear, or All")
    async def clearqueues(self, interaction: discord.Interaction, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else "All"
        if category_value == "All":
            clear_queue(guild_id); message = "all categories"
        elif category_value in LINKED:
            for target in LINKED:
                clear_queue(guild_id, target)
            message = "**Guild League / League Prize**"
        else:
            clear_queue(guild_id, category_value); message = f"**{category_value}**"
        await interaction.response.send_message(f"🗑️ Cleared queues for {message}.")

    @discord.app_commands.command(name="generate", description="Generate auction queue")
    @discord.app_commands.choices(category=CATEGORY_CHOICES)
    async def generate(self, interaction: discord.Interaction, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else "All"
        if category_value == "All": to_generate = list(CATEGORIES)
        elif category_value in LINKED: to_generate = list(LINKED)
        else: to_generate = [category_value]
        category_rewards, skipped_categories = check_categories(guild_id, to_generate)
        if not category_rewards:
            lines = ["❌ No categories are ready to generate."]
            if skipped_categories:
                lines.extend(["", "Skipped:"])
                for cat, reason in skipped_categories: lines.append(f"- {cat}: {reason}")
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            summary = await asyncio.to_thread(generate_all, guild_id, category_rewards)
            results = summary["results"]
            extra_count = summary["extra_count"]
            remaining_extra = summary["remaining_extra"]
            lines = ["✅ Queue Generated", ""]
            if any(cat in results for cat in LINKED):
                lines.append("🏆 Guild League / League Prize")
                for cat in LINKED:
                    if cat not in results: continue
                    data = results[cat]
                    if data["count"] > 0:
                        lines.append(f"- {cat}: {data['count']} (Queue {data['start']}-{data['end']})")
                if extra_count > 0:
                    lines.append(f"- GL/LP Extra: {extra_count} (Queue {summary['extra_start']}-{summary['extra_end']})")
                if summary["linked_limits_differ"]:
                    lines.append(
                        f"⚠️ Guild League and League Prize limits differ. Extra used the "
                        f"{summary['extra_limits_from']} limits. Run /setalllimit to sync them."
                    )
            for cat in ("Emperium Overrun", "Designed Auction"):
                if cat not in results: continue
                data = results[cat]; lines.extend(["", f"📂 {cat}"])
                lines.append(f"- {data['count']} (Queue {data['start']}-{data['end']})" if data["count"] > 0 else "- 0")
            if skipped_categories:
                lines.extend(["", "Skipped:"])
                for cat, reason in skipped_categories: lines.append(f"- {cat}: {reason}")
            if remaining_extra is not None:
                lines.extend(["", "Remaining GL/LP Extra:", f"- Card: {remaining_extra['CARD']}",
                              f"- Light-Dark: {remaining_extra['FEATHER_S']}", f"- Time-Space: {remaining_extra['FEATHER_A']}"])
            total_generated = sum(data["count"] for data in results.values()) + extra_count
            lines.extend(["", f"Total generated queues: {total_generated}", "", "Use: /queuelist"])
            await interaction.followup.send("\n".join(lines))
        except Exception as e:
            print("Error generating queues:", e)
            await interaction.followup.send(f"❌ Failed to generate queue: {e}", ephemeral=True)

    @discord.app_commands.command(name="clearconfig", description="Clear stock, limits and generated queues")
    @discord.app_commands.choices(category=CATEGORY_CHOICES)
    async def clearconfig(self, interaction: discord.Interaction, category: discord.app_commands.Choice[str] | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else "All"
        if category_value == "All": targets = list(CATEGORIES)
        elif category_value in LINKED: targets = list(LINKED)
        else: targets = [category_value]
        for target in targets:
            clear_rewards(guild_id, target)
            clear_queue(guild_id, target)
        await interaction.response.send_message("✅ Configuration cleared\n\n" f"Category: {', '.join(targets)}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
