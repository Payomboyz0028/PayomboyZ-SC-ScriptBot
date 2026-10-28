# -*- coding: utf-8 -*-
"""
💎 SC-HUB Automated Guild Deployer & Panel Dispatcher
Directly provisions panels, binds roles, and sets up department audit channels
for the ScriptCenter All server (1562827586101317672).
"""

from __future__ import annotations
import sys
import os
import asyncio
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import discord

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from database import db
from views.verify_view import VerificationPanelView, build_verification_panel_embed
from views.category_view import CategoryRouterView, build_category_router_embed
from views.lobby_view import DepartmentLobbyView, build_department_lobby_embed
from views.dispute_view import DisputePanelView, build_dispute_panel_embed

TARGET_GUILD_ID = 1562827586101317672

CHANNELS = {
    "verify": 1563251682375237693,
    "category": 1563251685940531260,
    "lobby_game": 1563612934494486589,
    "lobby_web": 1563251739153403928,
    "lobby_script": 1563613041675997284,
    "dispute": 1563251767674667019,
    "transcript_game": 1563251889041055937,
    "transcript_web": 1563251890916032632,
    "transcript_script": 1563251892958666823,
    "transaction_log": 1563251895332638730
}

ROLES = {
    "owner": 1563251630101766211,
    "head_staff": 1563251634119778346,
    "manager": 1563251632253304872,
    "verified": 1563251669662171216,
    "staff_game": 1563251654520868925,
    "staff_web": 1563251656596918412,
    "staff_script": 1563251658069254206,
    "customer_game": 1563251664192929975,
    "customer_web": 1563251665560408137,
    "customer_script": 1563251667552444499
}

intents = discord.Intents.default()
intents.guilds = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print("=" * 66, flush=True)
    print(f"🚀 SC-HUB AUTO-DEPLOY ENGINE STARTING", flush=True)
    print(f"👤 Logged in as: {client.user} ({client.user.id})", flush=True)
    print("=" * 66, flush=True)

    guild = client.get_guild(TARGET_GUILD_ID)
    if not guild:
        print(f"❌ Bot is not in guild {TARGET_GUILD_ID}!", flush=True)
        await client.close()
        return

    print(f"🏰 Found Target Guild: {guild.name} ({guild.id})", flush=True)

    # 1. Update SQLite Guild Configuration
    dept_roles_cfg = {
        "game": ROLES["customer_game"],
        "web": ROLES["customer_web"],
        "script": ROLES["customer_script"],
        "game_staff_role_id": ROLES["staff_game"],
        "web_staff_role_id": ROLES["staff_web"],
        "script_staff_role_id": ROLES["staff_script"]
    }

    db.update_guild_config(
        guild.id,
        verified_role_id=ROLES["verified"],
        owner_role_id=ROLES["owner"],
        manager_role_id=ROLES["manager"],
        staff_role_id=ROLES["manager"],
        transcript_log_channel_id=CHANNELS["transcript_game"],
        game_transcript_channel_id=CHANNELS["transcript_game"],
        web_transcript_channel_id=CHANNELS["transcript_web"],
        script_transcript_channel_id=CHANNELS["transcript_script"],
        transaction_log_channel_id=CHANNELS["transaction_log"],
        game_admin_channel_id=1563251828425228328,
        web_admin_channel_id=1563251839670034505,
        script_admin_channel_id=1563251851598626927,
        dept_roles=dept_roles_cfg
    )
    print("✅ [1/5] Saved Guild Roles & Database Configurations to SQLite.", flush=True)

    # 2. Deploy Panel 1: Verification Panel
    verify_ch = guild.get_channel(CHANNELS["verify"])
    if isinstance(verify_ch, discord.TextChannel):
        verified_r = guild.get_role(ROLES["verified"])
        verify_embed = build_verification_panel_embed(guild=guild, verified_role=verified_r)
        await verify_ch.send(embed=verify_embed, view=VerificationPanelView())
        print(f"✅ [2/5] Verification Panel sent to #{verify_ch.name} ({verify_ch.id})", flush=True)
    else:
        print(f"⚠️ Channel not found or not TextChannel: {CHANNELS['verify']}", flush=True)

    # 3. Deploy Panel 2: Category Selector Panel
    cat_ch = guild.get_channel(CHANNELS["category"])
    if isinstance(cat_ch, discord.TextChannel):
        cat_embed = build_category_router_embed()
        await cat_ch.send(embed=cat_embed, view=CategoryRouterView())
        print(f"✅ [3/5] Category Selector Panel sent to #{cat_ch.name} ({cat_ch.id})", flush=True)
    else:
        print(f"⚠️ Channel not found or not TextChannel: {CHANNELS['category']}", flush=True)

    # 4. Deploy Panel 3, 4, 5: Department Lobbies
    lobbies = [
        ("game", CHANNELS["lobby_game"]),
        ("web", CHANNELS["lobby_web"]),
        ("script", CHANNELS["lobby_script"])
    ]

    for dept_key, ch_id in lobbies:
        dept_ch = guild.get_channel(ch_id)
        if isinstance(dept_ch, discord.TextChannel):
            lobby_embed = build_department_lobby_embed(dept_key)
            await dept_ch.send(embed=lobby_embed, view=DepartmentLobbyView(dept_key))
            print(f"✅ [4/5] Department Lobby ({dept_key}) sent to #{dept_ch.name} ({dept_ch.id})", flush=True)
        else:
            print(f"⚠️ Lobby channel {ch_id} ({dept_key}) not found or not TextChannel", flush=True)

    # 5. Deploy Panel: Executive Dispute Panel
    dispute_ch = guild.get_channel(CHANNELS["dispute"])
    if isinstance(dispute_ch, discord.TextChannel):
        dispute_embed = build_dispute_panel_embed()
        await dispute_ch.send(embed=dispute_embed, view=DisputePanelView())
        print(f"✅ [5/5] Executive Dispute Panel sent to #{dispute_ch.name} ({dispute_ch.id})", flush=True)
    else:
        print(f"⚠️ Dispute channel {CHANNELS['dispute']} not found or not TextChannel", flush=True)

    print("=" * 66, flush=True)
    print("🎉 ALL PANELS & ROLES SUCCESSFULLY DEPLOYED TO DISCORD!", flush=True)
    print("=" * 66, flush=True)
    await client.close()


if __name__ == "__main__":
    token = config.DISCORD_BOT_TOKEN
    asyncio.run(client.start(token))
