import discord

from discord.ext import commands

import asyncio

from choices import CATEGORY_CHOICES
from constants import CATEGORIES, LINKED, REQUIRED_REWARDS, REWARD_NAMES, REWARD_TYPES
from database import (
    set_reward_stock,
    set_reward_limit,
    get_rewards,
    clear_queue,
    clear_rewards,
    get_max_queue_no,
    get_party_plan,
    set_day_closed,
    set_party_plan,
    set_used_queue_start,
)

from generator import check_categories, generate_all
from parties import assign_cards, card_summary_lines, end_day, preview_party_plan

# Stock can still be configured separately per category.
SET_CATEGORY_CHOICES = [
    discord.app_commands.Choice(name=cat, value=cat)
    for cat in (*CATEGORIES, "All")
]

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="setallstock", description="Set stock for all rewards at once"
    )
    @discord.app_commands.choices(category=SET_CATEGORY_CHOICES)
    @discord.app_commands.describe(
        card="Total Card stock", light_dark="Total Light-Dark stock",
        time_space="Total Time-Space stock",
        destroyer_stardust="Total Destroyer Stardust Pack stock (leave empty to keep current)",
        destroyer_starcore="Total Destroyer Starcore stock (leave empty to keep current)",
        guardian_stardust="Total Guardian Stardust Pack stock (leave empty to keep current)",
        guardian_starcore="Total Guardian Starcore stock (leave empty to keep current)",
        category="Which category to apply (All by default)",
    )
    async def setallstock(
        self,
        interaction: discord.Interaction,
        card: int,
        light_dark: int,
        time_space: int,
        destroyer_stardust: int | None = None,
        destroyer_starcore: int | None = None,
        guardian_stardust: int | None = None,
        guardian_starcore: int | None = None,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        stock_values = {
            "CARD": card,
            "FEATHER_S": light_dark,
            "FEATHER_A": time_space,
            "ASTRO_DS": destroyer_stardust,
            "ASTRO_DC": destroyer_starcore,
            "ASTRO_GS": guardian_stardust,
            "ASTRO_GC": guardian_starcore,
        }
        # Optional rewards that were left empty are not touched.
        stock_values = {r: v for r, v in stock_values.items() if v is not None}
        if any(stock < 0 for stock in stock_values.values()):
            await interaction.response.send_message("❌ Stock must be 0 or greater for all rewards", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        category_value = category.value if category is not None else "All"
        targets = list(CATEGORIES) if category_value == "All" else [category_value]
        for target in targets:
            for reward, stock in stock_values.items():
                set_reward_stock(guild_id, reward, stock, target)
        lines = ["✅ Reward stock updated"]
        lines.extend(f"{REWARD_NAMES[reward]}: {stock_values[reward]}" for reward in REWARD_TYPES if reward in stock_values)
        lines.append(f"Applied to: {', '.join(targets)}")
        await interaction.response.send_message("\n".join(lines))

    @discord.app_commands.command(name="setalllimit", description="Set limits for all rewards at once")
    @discord.app_commands.choices(category=CATEGORY_CHOICES)
    @discord.app_commands.describe(
        card="Card amount per queue (0 = Extra only)",
        light_dark="Light-Dark amount per queue (0 = Extra only)",
        time_space="Time-Space amount per queue (0 = Extra only)",
        destroyer_stardust="Destroyer Stardust Pack per queue (0 = Extra only, empty = keep current)",
        destroyer_starcore="Destroyer Starcore per queue (0 = Extra only, empty = keep current)",
        guardian_stardust="Guardian Stardust Pack per queue (0 = Extra only, empty = keep current)",
        guardian_starcore="Guardian Starcore per queue (0 = Extra only, empty = keep current)",
        category="Which category to apply. Guild League / League Prize are linked.",
    )
    async def setalllimit(
        self,
        interaction: discord.Interaction,
        card: int,
        light_dark: int,
        time_space: int,
        destroyer_stardust: int | None = None,
        destroyer_starcore: int | None = None,
        guardian_stardust: int | None = None,
        guardian_starcore: int | None = None,
        category: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        limit_values = {
            "CARD": card,
            "FEATHER_S": light_dark,
            "FEATHER_A": time_space,
            "ASTRO_DS": destroyer_stardust,
            "ASTRO_DC": destroyer_starcore,
            "ASTRO_GS": guardian_stardust,
            "ASTRO_GC": guardian_starcore,
        }
        # Optional rewards that were left empty are not touched.
        limit_values = {r: v for r, v in limit_values.items() if v is not None}
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
        lines = ["✅ Queue limits updated"]
        lines.extend(f"{REWARD_NAMES[reward]}: {limit_values[reward]}" for reward in REWARD_TYPES if reward in limit_values)
        lines.append(f"Applied to: {', '.join(targets)}")
        await interaction.response.send_message("\n".join(lines))

    @discord.app_commands.command(
        name="setparty",
        description="Set the party rotation for Guild League / League Prize",
    )
    @discord.app_commands.describe(
        queue_start="Party of queue 1 today (example: 5 for P5)",
        card_start="Party that gets the first Card today (example: 11 for P11)",
        party_count="Number of parties in the rotation (keeps the current value, 16 at first)",
    )
    async def setparty(
        self,
        interaction: discord.Interaction,
        queue_start: int,
        card_start: int,
        party_count: int | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        current = get_party_plan(guild_id)
        if party_count is None:
            party_count = current["party_count"] if current is not None else 16
        if not 1 <= party_count <= 100:
            await interaction.response.send_message("❌ Party count must be between 1 and 100", ephemeral=True)
            return
        for name, value in (("Queue start", queue_start), ("Card start", card_start)):
            if not 1 <= value <= party_count:
                await interaction.response.send_message(
                    f"❌ {name} must be a party between 1 and {party_count}", ephemeral=True
                )
                return
        set_party_plan(guild_id, party_count, queue_start, card_start)
        lines = [
            "✅ Party plan updated",
            f"Parties: {party_count}",
            f"Queue 1: P{queue_start}",
            f"Cards start at: P{card_start}",
        ]
        if get_max_queue_no(guild_id, LINKED) > 0:
            lines.extend(["", "ℹ️ Run /generate again so the queues and Cards follow the new plan."])
        await interaction.response.send_message("\n".join(lines))

    @discord.app_commands.command(
        name="endday",
        description="Close today and move the party pointers to tomorrow",
    )
    async def endday(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        result = end_day(guild_id)
        error = result.get("error")
        if error == "no_plan":
            await interaction.response.send_message("❌ No party plan yet. Use /setparty first.", ephemeral=True)
            return
        if error == "closed":
            await interaction.response.send_message(
                "❌ Today is already closed. Run /generate for the next day first.", ephemeral=True
            )
            return
        if error == "no_queues":
            await interaction.response.send_message(
                "❌ No Guild League / League Prize queues generated. Use /generate first.", ephemeral=True
            )
            return
        if result["last_card_party"] is not None:
            card_line = f"Last Card: P{result['last_card_party']}"
        else:
            card_line = "No Card was placed today, so the Card start stays the same"
        await interaction.response.send_message(
            "\n".join([
                "✅ Day closed",
                f"Last queue: #{result['last_queue']} (P{result['last_party']})",
                card_line,
                "",
                "Tomorrow:",
                f"- Queue 1 = P{result['new_queue_start']}",
                f"- Cards start at P{result['new_card_start']}",
                "",
                "Then run /generate for the next day.",
            ])
        )

    @discord.app_commands.command(
        name="partyplan",
        description="Quick calculation of the queue - party table and Cards (saves nothing)",
    )
    @discord.app_commands.choices(
        view=[
            discord.app_commands.Choice(name="Both", value="both"),
            discord.app_commands.Choice(name="Queue - party table", value="queue"),
            discord.app_commands.Choice(name="Card per party", value="card"),
        ]
    )
    @discord.app_commands.describe(
        date="Heading date, example 19/11",
        view="What to show (Both by default)",
    )
    async def partyplan(
        self,
        interaction: discord.Interaction,
        date: str,
        view: discord.app_commands.Choice[str] | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        plan = get_party_plan(guild_id)
        if plan is None:
            await interaction.response.send_message("❌ No party plan yet. Use /setparty first.", ephemeral=True)
            return
        date = date.strip()
        # The plan is always posted as the "Win" case.
        header = f"{date} condition Win"
        result = preview_party_plan(
            guild_id, plan, view.value if view is not None else "both", header
        )
        if "error" in result:
            lines = ["❌ Nothing to calculate yet. Set stock and limits for Guild League / League Prize first."]
            if result["notes"]:
                lines.extend(["", "Skipped:"])
                lines.extend(f"- {note}" for note in result["notes"])
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
            return
        messages = result["messages"]
        await interaction.response.send_message(messages[0])
        for message in messages[1:]:
            await interaction.followup.send(message)
        # Remarks are only for the person who ran the command.
        await interaction.followup.send("\n".join(f"ℹ️ {note}" for note in result["notes"]), ephemeral=True)

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
                    if reward not in REQUIRED_REWARDS:
                        continue
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

        plan = get_party_plan(guild_id)
        if plan is not None and any(target in LINKED for target in targets):
            embed.add_field(
                name="🎉 Party plan (Guild League / League Prize)",
                value=(
                    f"Parties: **{plan['party_count']}**\n"
                    f"Queue 1: **P{plan['queue_start']}**\n"
                    f"Cards start at: **P{plan['card_start']}**\n"
                    f"Day: **{'closed' if plan['day_closed'] else 'open'}**"
                ),
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
            card_result = None
            linked_done = [cat for cat in LINKED if cat in results]
            plan = get_party_plan(guild_id)
            if linked_done and plan is not None:
                set_day_closed(guild_id, False)
                set_used_queue_start(guild_id, plan["queue_start"])
                plan = get_party_plan(guild_id)
                card_result = await asyncio.to_thread(assign_cards, guild_id, plan, linked_done)
                if remaining_extra is not None:
                    placed = sum(info["count"] for info in card_result["per_category"].values())
                    remaining_extra = dict(remaining_extra)
                    remaining_extra["CARD"] = max(remaining_extra["CARD"] - placed, 0)
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
                if card_result is not None:
                    card_lines = card_summary_lines(card_result)
                    if card_lines:
                        lines.extend(["", "🃏 Card (by party)"])
                        lines.extend(card_lines)
            for cat in ("Emperium Overrun", "Designed Auction"):
                if cat not in results: continue
                data = results[cat]; lines.extend(["", f"📂 {cat}"])
                lines.append(f"- {data['count']} (Queue {data['start']}-{data['end']})" if data["count"] > 0 else "- 0")
            if skipped_categories:
                lines.extend(["", "Skipped:"])
                for cat, reason in skipped_categories: lines.append(f"- {cat}: {reason}")
            if remaining_extra is not None:
                lines.extend(["", "Remaining GL/LP Extra:"])
                lines.extend(
                    f"- {REWARD_NAMES[reward]}: {remaining_extra[reward]}"
                    for reward in REWARD_TYPES
                    if remaining_extra[reward] > 0 or reward in REQUIRED_REWARDS
                )
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
