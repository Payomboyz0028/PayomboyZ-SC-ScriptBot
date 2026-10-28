# -*- coding: utf-8 -*-
"""
PAYOMBØYZ Industrial HTML Transcript Exporter
Exports full Discord channel message history into a self-contained, beautifully styled HTML document.
"""

from __future__ import annotations
import io
import re
import html
import time
from typing import Tuple
import discord


async def generate_ticket_transcript(channel: discord.TextChannel) -> Tuple[discord.File, int]:
    """Fetches all messages from channel and renders a modern Discord-styled HTML transcript."""
    messages = []
    async for msg in channel.history(limit=1000, oldest_first=True):
        messages.append(msg)

    html_lines = [
        "<!DOCTYPE html>",
        "<html lang='th'>",
        "<head>",
        "<meta charset='utf-8'>",
        f"<title>PAYOMBØYZ Dispatch Transcript - {html.escape(channel.name)}</title>",
        "<style>",
        "  body { background: #1e1f22; color: #dbdee1; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 25px; margin: 0; line-height: 1.5; }",
        "  .header { border-bottom: 2px solid #35363c; padding-bottom: 15px; margin-bottom: 25px; }",
        "  .header h1 { color: #f1c40f; margin: 0 0 6px 0; font-size: 24px; font-weight: 700; }",
        "  .meta { color: #949ba4; font-size: 13px; }",
        "  .meta b { color: #ffffff; }",
        "  .msg-container { display: flex; flex-direction: column; gap: 8px; }",
        "  .msg { display: flex; padding: 6px 12px; border-radius: 6px; transition: background 0.15s ease; }",
        "  .msg:hover { background: #2b2d31; }",
        "  .avatar { width: 42px; height: 42px; border-radius: 50%; margin-right: 14px; object-fit: cover; flex-shrink: 0; }",
        "  .msg-body { flex: 1; min-width: 0; }",
        "  .author-row { display: flex; align-items: baseline; gap: 8px; margin-bottom: 3px; }",
        "  .author { font-weight: 600; color: #f2f3f5; font-size: 15px; }",
        "  .bot-tag { background: #5865f2; color: #ffffff; font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: 700; vertical-align: middle; }",
        "  .time { font-size: 12px; color: #949ba4; }",
        "  .content { word-break: break-word; color: #dbdee1; font-size: 14px; }",
        "  .embed { border-left: 4px solid #f1c40f; background: #2b2d31; padding: 12px 16px; margin-top: 8px; border-radius: 4px; max-width: 640px; }",
        "  .embed-title { font-weight: 700; color: #ffffff; margin-bottom: 6px; font-size: 15px; }",
        "  .embed-desc { color: #dbdee1; font-size: 13.5px; white-space: pre-wrap; }",
        "  .attachment { margin-top: 8px; }",
        "  .attachment img { max-width: 400px; max-height: 300px; border-radius: 6px; border: 1px solid #35363c; }",
        "  .attachment-link { display: inline-block; padding: 4px 8px; background: #2b2d31; color: #00a8fc; border-radius: 4px; text-decoration: none; font-size: 12px; }",
        "</style>",
        "</head>",
        "<body>",
        "<div class='header'>",
        f"  <h1>👑 PAYOMBØYZ Dispatch Transcript</h1>",
        f"  <div class='meta'>ห้อง: <b>#{html.escape(channel.name)}</b> | วันที่ส่งออก: <b>{time.strftime('%Y-%m-%d %H:%M:%S')}</b> | ทั้งหมด: <b>{len(messages):,}</b> ข้อความ</div>",
        "</div>",
        "<div class='msg-container'>"
    ]

    for m in messages:
        avatar_url = m.author.display_avatar.url if m.author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        time_str = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
        bot_badge = "<span class='bot-tag'>BOT</span>" if m.author.bot else ""
        escaped_text = html.escape(m.clean_content).replace("\n", "<br>")

        # Embeds parsing
        embeds_html = []
        for emb in m.embeds:
            color_hex = f"#{emb.color.value:06x}" if emb.color else "#f1c40f"
            e_title = html.escape(emb.title) if emb.title else ""
            e_desc = html.escape(emb.description or "").replace("\n", "<br>")
            
            e_block = f"<div class='embed' style='border-left-color: {color_hex};'>"
            if e_title:
                e_block += f"<div class='embed-title'>{e_title}</div>"
            if e_desc:
                e_block += f"<div class='embed-desc'>{e_desc}</div>"
            e_block += "</div>"
            embeds_html.append(e_block)

        # Attachments parsing
        attachments_html = []
        for att in m.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                attachments_html.append(f"<div class='attachment'><img src='{att.url}' alt='{html.escape(att.filename)}'></div>")
            else:
                attachments_html.append(f"<div class='attachment'><a class='attachment-link' href='{att.url}' target='_blank'>📎 {html.escape(att.filename)} ({att.size:,} bytes)</a></div>")

        html_lines.append(
            f"  <div class='msg'>"
            f"    <img class='avatar' src='{avatar_url}'>"
            f"    <div class='msg-body'>"
            f"      <div class='author-row'>"
            f"        <span class='author'>{html.escape(m.author.display_name)}</span>"
            f"        {bot_badge}"
            f"        <span class='time'>{time_str}</span>"
            f"      </div>"
            f"      <div class='content'>{escaped_text}</div>"
            f"      {''.join(embeds_html)}"
            f"      {''.join(attachments_html)}"
            f"    </div>"
            f"  </div>"
        )

    html_lines.append("</div></body></html>")
    full_html = "\n".join(html_lines)

    buffer = io.BytesIO(full_html.encode("utf-8"))
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', channel.name)
    discord_file = discord.File(buffer, filename=f"Transcript_{safe_name}.html")
    return discord_file, len(messages)
