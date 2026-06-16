import threading
import tkinter as tk
import pystray
from PIL import Image, ImageDraw
import winreg
import ctypes
import ctypes.wintypes
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import discord
import asyncio
import json
import base64
import re
import subprocess

def send_notification(title, msg):
    try:
        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $template = @"
        <toast>
            <visual>
                <binding template="ToastText02">
                    <text id="1">{title}</text>
                    <text id="2">{msg}</text>
                </binding>
            </visual>
        </toast>
"@
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'}").Show($toast)
        """
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            creationflags=0x08000000
        )
    except Exception:
        pass


GAME_NAME = "blokself"
STREAM_URL = "https://twitch.tv/blokself"
TOKENS_FILE = "tokens.txt"
CONFIG_FILE = "config.json"
config_lock = threading.Lock()
mutex_handle = None

HELP_TEXT = (
    "**blokself — Commands**\n\n"
    "> `?enable` — Enable Rich Presence\n"
    "> `?disable` — Disable Rich Presence\n"
    "> `?rpc <listen|watch|play|stream> [name]` — Custom Rich Presence\n"
    "> `?delay <s>` — Change message auto-deletion delay (0 to disable)\n"
    "> `?delaysettings <s>` — Change command response auto-deletion delay\n"
    "> `?react <emoji>` — Auto-react to messages\n"
    "> `?sup-all` — Delete all your messages\n"
    "> `?close-mp` — Close all DMs\n"
    "> `?close-group` — Leave all groups\n"
    "> `?close-all` — Close all DMs and groups\n"
    "> `?help` — Show this help message"
)

class BlokselfBot(discord.Client):
    def __init__(self, token_str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot_token = token_str.strip()
        self.delete_delay = 0
        self.rpc_enabled = True
        self.waiting_confirm = set()
        self.protected_msgs = set()
        self.blokself_id = None
        self.setting_up_group = False
        self.auto_react_emoji = None
        self.is_active = True
        
        self.custom_presence_type = None  # listen/watch/play/stream
        self.custom_presence_name = None
        self.custom_presence_url = None
        
        self.settings_delay = 3.0

    def load_settings(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with config_lock:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        return
                    data = json.loads(content)
            if self.bot_token in data:
                settings = data[self.bot_token]
                self.rpc_enabled = settings.get("rpc_enabled", self.rpc_enabled)
                self.delete_delay = settings.get("delete_delay", self.delete_delay)
                self.auto_react_emoji = settings.get("auto_react_emoji", self.auto_react_emoji)
                self.is_active = settings.get("is_active", self.is_active)
                self.custom_presence_type = settings.get("custom_presence_type", self.custom_presence_type)
                self.custom_presence_name = settings.get("custom_presence_name", self.custom_presence_name)
                self.custom_presence_url = settings.get("custom_presence_url", self.custom_presence_url)
                self.settings_delay = settings.get("settings_delay", self.settings_delay)
        except Exception:
            pass

    def save_settings(self):
        try:
            with config_lock:
                data = {}
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            try:
                                data = json.loads(content)
                            except Exception:
                                pass
                
                data[self.bot_token] = {
                    "user_name": str(self.user) if getattr(self, 'user', None) else data.get(self.bot_token, {}).get("user_name", "Unknown"),
                    "rpc_enabled": self.rpc_enabled,
                    "delete_delay": self.delete_delay,
                    "auto_react_emoji": self.auto_react_emoji,
                    "is_active": getattr(self, 'is_active', True),
                    "custom_presence_type": self.custom_presence_type,
                    "custom_presence_name": self.custom_presence_name,
                    "custom_presence_url": self.custom_presence_url,
                    "settings_delay": self.settings_delay,
                }
                
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
        except Exception:
            pass

    async def send_help_embed(self, channel):
        embed = discord.Embed(
            title="blokself — Commands",
            description="Here are all available commands:",
            color=0x5865F2,
        )
        embed.add_field(name="`?enable`", value="Enable Rich Presence", inline=False)
        embed.add_field(name="`?disable`", value="Disable Rich Presence", inline=False)
        embed.add_field(name="`?rpc <listen|watch|play|stream> [name]`", value="Custom Rich Presence", inline=False)
        embed.add_field(name="`?delay <s>`", value="Change message auto-deletion delay (0 to disable)", inline=False)
        embed.add_field(name="`?delaysettings <s>`", value="Change command response auto-deletion delay", inline=False)
        embed.add_field(name="`?react <emoji>`", value="Auto-react to messages (empty to disable)", inline=False)
        embed.add_field(name="`?sup-all`", value="Delete all your messages (confirmation required)", inline=False)
        embed.add_field(name="`?close-mp`", value="Close all DMs", inline=False)
        embed.add_field(name="`?close-group`", value="Leave all groups", inline=False)
        embed.add_field(name="`?close-all`", value="Close all DMs and groups", inline=False)
        embed.add_field(name="`?help`", value="Show this help message", inline=False)
        embed.set_footer(text="blokself selfbot")

        try:
            msg = await channel.send(embed=embed)
        except Exception:
            msg = await channel.send(HELP_TEXT)
        self.protected_msgs.add(msg.id)
        return msg

    async def auto_delete(self, message, delay=None):
        await asyncio.sleep(delay if delay is not None else self.delete_delay)
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception as e:
            print(f"[{self.user}] Deletion error: {e}")


    def _build_activity(self, ptype, name, url=None):
        """Build a discord Activity from type string. Falls back to default stream."""
        ptype = (ptype or "stream").lower()
        name = name or GAME_NAME
        url = url or STREAM_URL
        if ptype == "listen":
            return discord.Activity(type=discord.ActivityType.listening, name=name)
        elif ptype == "watch":
            return discord.Activity(type=discord.ActivityType.watching, name=name)
        elif ptype == "play":
            return discord.Activity(type=discord.ActivityType.playing, name=name)
        else:  # stream (default)
            return discord.Streaming(name=name, url=url)


    async def redeem_nitro(self, code, channel_id):
        print(f"[{self.user}] Found Nitro code: {code}")
        try:
            req = await self.http.request(
                discord.http.Route("POST", f"/entitlements/gift-codes/{code}/redeem"),
                json={"channel_id": str(channel_id), "payment_source_id": None}
            )
            print(f"[{self.user}] Successfully redeemed nitro: {code}")
            if self.blokself_id:
                ch = self.get_channel(self.blokself_id)
                if ch: await ch.send(f" **NITRO REDEEMED** Code: `{code}`")
        except discord.HTTPException as e:
            msg = "Unknown error"
            if e.code == 50050: msg = "Code already claimed"
            elif e.code == 10038: msg = "Invalid code"
            print(f"[{self.user}] Failed to redeem {code}: {msg}")
            if self.blokself_id:
                ch = self.get_channel(self.blokself_id)
                if ch: await ch.send(f" Nitro failed (`{code}`): {msg}")

    async def on_ready(self):
        self.login_failed = False
        self.load_settings()
        self.save_settings()
        print(f"Connected: {self.user} ({self.user.id}) | Delay: {self.delete_delay}s")
        send_notification("Blokself", f"Account {self.user} is connected.")

        if self.rpc_enabled:
            
            activity = self._build_activity(
                self.custom_presence_type,
                self.custom_presence_name or GAME_NAME,
                self.custom_presence_url or STREAM_URL
            )
            await self.change_presence(activity=activity)


        await self.setup_blokself_group()
        update_tray_menu()

    async def setup_blokself_group(self):
        if getattr(self, 'setting_up_group', False):
            return
        self.setting_up_group = True
        blokself = None
        try:
            for ch in list(self.private_channels):
                if isinstance(ch, discord.GroupChannel) and ch.name and GAME_NAME.lower() in ch.name.lower():
                    try:
                        print(f"[{self.user}] Deleting old blokself group: {ch.id}")
                        await ch.leave()
                    except Exception:
                        pass

            data = await self.http.request(
                discord.http.Route("POST", "/users/@me/channels"),
                json={"recipients": []},
            )
            channel_id = int(data["id"])
            for _ in range(5):
                await asyncio.sleep(1)
                blokself = self.get_channel(channel_id)
                if blokself:
                    break

            if blokself and isinstance(blokself, discord.GroupChannel):
                await blokself.edit(name=GAME_NAME)
                print(f"[{self.user}] Fresh blokself group created: {channel_id}")
        except Exception as e:
            print(f"[{self.user}] Cannot create group: {e} — fallback DM")
            try:
                blokself = await self.user.create_dm()
            except Exception:
                pass

        if blokself:
            self.blokself_id = blokself.id
            await asyncio.sleep(1)

            if os.path.exists("group.png"):
                try:
                    with open("group.png", "rb") as f:
                        icon_bytes = f.read()
                    icon_b64 = f"data:image/png;base64,{base64.b64encode(icon_bytes).decode('ascii')}"
                    await self.http.request(
                        discord.http.Route("PATCH", f"/channels/{blokself.id}"),
                        json={"icon": icon_b64}
                    )
                except Exception:
                    pass

            await asyncio.sleep(1)
            await self.send_help_embed(blokself)
        self.setting_up_group = False
        print(f"[{self.user}] Commands sent")

    async def on_message_delete(self, message):
        if message.id in self.protected_msgs:
            self.protected_msgs.remove(message.id)
            print(f"[{self.user}] Help message deleted, resending...")
            if self.blokself_id and message.channel.id == self.blokself_id:
                await self.send_help_embed(message.channel)

    async def on_private_channel_delete(self, channel):
        if self.blokself_id and channel.id == self.blokself_id:
            print(f"[{self.user}] blokself group left/deleted, recreating...")
            self.blokself_id = None
            asyncio.create_task(self.setup_blokself_group())

    async def on_private_channel_update(self, before, after):
        """Re-apply group.png if someone changes the group icon."""
        if self.blokself_id and after.id == self.blokself_id:
            if isinstance(after, discord.GroupChannel):
                if getattr(before, 'icon', None) != getattr(after, 'icon', None) and os.path.exists("group.png"):
                    try:
                        await asyncio.sleep(1)
                        with open("group.png", "rb") as f:
                            icon_bytes = f.read()
                        icon_b64 = f"data:image/png;base64,{base64.b64encode(icon_bytes).decode('ascii')}"
                        await self.http.request(
                            discord.http.Route("PATCH", f"/channels/{after.id}"),
                            json={"icon": icon_b64}
                        )
                        print(f"[{self.user}] Group icon restored.")
                    except Exception as e:
                        print(f"[{self.user}] Cannot restore icon: {e}")

    async def on_group_join(self, channel, user):
        if self.blokself_id and channel.id == self.blokself_id:
            try:
                await channel.remove_recipient(user)
                print(f"[{self.user}] Auto-kicked {user} from the group.")
            except Exception as e:
                print(f"[{self.user}] Cannot kick {user}: {e}")

    async def on_message(self, message):
        
        if self.blokself_id and message.channel.id == self.blokself_id:
            =
            if isinstance(message.channel, discord.GroupChannel) and message.channel.recipients:
                for u in list(message.channel.recipients):
                    try:
                        await message.channel.remove_recipient(u)
                        print(f"[{self.user}] Auto-kicked {u} from the group.")
                    except Exception as e:
                        print(f"[{self.user}] Cannot kick {u}: {e}")
            =
            if message.author.id == self.user.id and message.id not in self.protected_msgs:
                if not (message.embeds and message.embeds[0].title == "blokself — Commands"):
                    asyncio.create_task(self.auto_delete(message, delay=60))

        if not getattr(self, 'is_active', True):
            return

        if message.author.id != self.user.id:
            match = re.search(r'(discord\.gift/|discord\.com/gifts/)([a-zA-Z0-9]+)', message.content)
            if match:
                code = match.group(2)
                asyncio.create_task(self.redeem_nitro(code, message.channel.id))

        if message.author.id != self.user.id:
            return

        if message.id in self.protected_msgs:
            return
        if message.embeds and message.embeds[0].title == "blokself — Commands":
            return
        if message.content == HELP_TEXT:
            return

        if message.channel.id in self.waiting_confirm:
            return

        content = message.content.strip().lower()

        if content == "?enable":
            self.rpc_enabled = True
            self.save_settings()
            activity = self._build_activity(
                self.custom_presence_type,
                self.custom_presence_name or GAME_NAME,
                self.custom_presence_url or STREAM_URL
            )
            await self.change_presence(activity=activity)
            name_display = self.custom_presence_name or GAME_NAME
            await message.edit(content=f"Rich Presence **enabled** — {self.custom_presence_type or 'stream'}: {name_display}")
            print(f"[{self.user}] Rich Presence enabled")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content == "?disable":
            self.rpc_enabled = False
            self.save_settings()
            await self.change_presence(activity=None)
            await message.edit(content="Rich Presence **disabled**")
            print(f"[{self.user}] Rich Presence disabled")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content.startswith("?delay") and not content.startswith("?delaysettings"):
            parts = message.content.strip().split()
            if len(parts) == 2:
                try:
                    new_delay = float(parts[1])
                    if new_delay < 0:
                        raise ValueError
                    self.delete_delay = new_delay
                    self.save_settings()
                    if self.delete_delay == 0:
                        await message.edit(content="Auto-deletion **disabled**")
                        print(f"[{self.user}] Auto-deletion disabled")
                    else:
                        await message.edit(content=f"Deletion delay: **{self.delete_delay}s**")
                        print(f"[{self.user}] Delay changed: {self.delete_delay}s")
                except ValueError:
                    await message.edit(content="Usage: `?delay <seconds>` (0 to disable)")
            else:
                status = f"**{self.delete_delay}s**" if self.delete_delay > 0 else "**disabled**"
                await message.edit(content=f"Current delay: {status} — Usage: `?delay <seconds>`")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content.startswith("?delaysettings"):
            parts = message.content.strip().split()
            if len(parts) == 2:
                try:
                    new_delay = float(parts[1])
                    if new_delay < 0:
                        raise ValueError
                    self.settings_delay = new_delay
                    self.save_settings()
                    if self.settings_delay == 0:
                        await message.edit(content="Command response auto-deletion **disabled**")
                        print(f"[{self.user}] Settings delay disabled")
                    else:
                        await message.edit(content=f"Command response delay: **{self.settings_delay}s**")
                        print(f"[{self.user}] Settings delay changed: {self.settings_delay}s")
                except ValueError:
                    await message.edit(content="Usage: `?delaysettings <seconds>`")
            else:
                await message.edit(content=f"Current settings delay: **{self.settings_delay}s** — Usage: `?delaysettings <seconds>`")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content.startswith("?react"):
            parts = message.content.strip().split(maxsplit=1)
            if len(parts) == 2:
                self.auto_react_emoji = parts[1].strip()
                self.save_settings()
                await message.edit(content=f"Auto-reaction enabled: {self.auto_react_emoji}")
                print(f"[{self.user}] Auto-react set to {self.auto_react_emoji}")
            else:
                self.auto_react_emoji = None
                self.save_settings()
                await message.edit(content="Auto-reaction disabled")
                print(f"[{self.user}] Auto-react disabled")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return




        if content.startswith("?rich-presence") or content.startswith("?rpc"):
            
            
            raw_parts = message.content.strip().split()
            if len(raw_parts) >= 2:
                type_str = raw_parts[1].lower()
                
                rest = raw_parts[2:]
                if rest and rest[-1].startswith("http"):
                    url = rest[-1]
                    name_parts = rest[:-1]
                else:
                    url = STREAM_URL  
                    name_parts = rest
                name = " ".join(name_parts) if name_parts else GAME_NAME
                activity = self._build_activity(type_str, name, url)
                
                self.custom_presence_type = type_str
                self.custom_presence_name = name
                self.custom_presence_url = url if type_str == "stream" else None
                self.save_settings()
                await self.change_presence(activity=activity)
                await message.edit(content=f"Rich Presence set to **{type_str}**: {name}")
                print(f"[{self.user}] Rich Presence → {type_str}: {name}")
            else:
                await message.edit(content="Usage: `?rpc <listen|watch|play|stream> [name] [url]`")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return


        if content == "?help":
            await message.edit(content=HELP_TEXT)
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content == "?close-mp":
            count = 0
            for ch in list(self.private_channels):
                if isinstance(ch, discord.DMChannel):
                    try:
                        await ch.close()
                        count += 1
                    except Exception:
                        pass
            await message.edit(content=f"**{count}** DMs closed")
            print(f"[{self.user}] {count} DMs closed")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content == "?close-group":
            count = 0
            for ch in list(self.private_channels):
                if isinstance(ch, discord.GroupChannel):
                    try:
                        await ch.leave()
                        count += 1
                    except Exception:
                        pass
            await message.edit(content=f"**{count}** groups left")
            print(f"[{self.user}] {count} groups left")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content == "?close-all":
            dm_count = 0
            grp_count = 0
            for ch in list(self.private_channels):
                try:
                    if isinstance(ch, discord.DMChannel):
                        await ch.close()
                        dm_count += 1
                    elif isinstance(ch, discord.GroupChannel):
                        await ch.leave()
                        grp_count += 1
                except Exception:
                    pass
            await message.edit(content=f"**{dm_count}** DMs closed, **{grp_count}** groups left")
            print(f"[{self.user}] {dm_count} DMs closed, {grp_count} groups left")
            asyncio.create_task(self.auto_delete(message, delay=self.settings_delay))
            return

        if content == "?sup-all":
            await message.edit(
                content="**Select deletion type:**\n`1` - Servers\n`2` - DMs/Groups\n`3` - All\nWait 30s to cancel."
            )

            self.waiting_confirm.add(message.channel.id)

            def check_type(m):
                return m.author.id == self.user.id and m.channel.id == message.channel.id and m.content.strip() in ("1", "2", "3")

            try:
                choice_msg = await self.wait_for("message", check=check_type, timeout=30)
                choice = choice_msg.content.strip()
                try:
                    await choice_msg.delete()
                except Exception:
                    pass

                guilds_to_delete = []
                dms_to_delete = []

                if choice in ("1", "3"):
                    if choice == "1":
                        servers_list = "\n".join([f"`{i+1}` - {g.name}" for i, g in enumerate(self.guilds)])
                        if len(servers_list) > 1800:
                            servers_list = servers_list[:1800] + "..."
                        await message.edit(content=f"**Select servers (`0` for all):**\n{servers_list}")
                        
                        def check_servers(m):
                            return m.author.id == self.user.id and m.channel.id == message.channel.id
                        
                        srv_msg = await self.wait_for("message", check=check_servers, timeout=60)
                        srv_choice = srv_msg.content.strip().split()
                        try:
                            await srv_msg.delete()
                        except Exception:
                            pass
                            
                        if "0" in srv_choice:
                            guilds_to_delete = self.guilds
                        else:
                            for idx in srv_choice:
                                try:
                                    g_idx = int(idx) - 1
                                    if 0 <= g_idx < len(self.guilds):
                                        guilds_to_delete.append(self.guilds[g_idx])
                                except ValueError:
                                    pass
                    else:
                        guilds_to_delete = self.guilds

                if choice in ("2", "3"):
                    if choice == "2":
                        dms_list = []
                        valid_channels = []
                        for i, ch in enumerate(self.private_channels):
                            name = ch.name if hasattr(ch, 'name') and ch.name else ("DM" if isinstance(ch, discord.DMChannel) else "Group")
                            if isinstance(ch, discord.DMChannel) and ch.recipient:
                                name = f"DM: {ch.recipient.name}"
                            dms_list.append(f"`{i+1}` - {name}")
                            valid_channels.append(ch)
                            
                        dms_text = "\n".join(dms_list)
                        if len(dms_text) > 1800:
                            dms_text = dms_text[:1800] + "..."
                        await message.edit(content=f"**Select DMs/Groups (`0` for all):**\n{dms_text}")
                        
                        def check_dms(m):
                            return m.author.id == self.user.id and m.channel.id == message.channel.id
                            
                        dm_msg = await self.wait_for("message", check=check_dms, timeout=60)
                        dm_choice = dm_msg.content.strip().split()
                        try:
                            await dm_msg.delete()
                        except Exception:
                            pass
                            
                        if "0" in dm_choice:
                            dms_to_delete = valid_channels
                        else:
                            for idx in dm_choice:
                                try:
                                    c_idx = int(idx) - 1
                                    if 0 <= c_idx < len(valid_channels):
                                        dms_to_delete.append(valid_channels[c_idx])
                                except ValueError:
                                    pass
                    else:
                        dms_to_delete = self.private_channels

                await message.edit(content="**Deletion in progress... (0)**")
                status_id = message.id
                count = 0

                for guild in guilds_to_delete:
                    print(f"[{self.user}] Searching in {guild.name}...")
                    while True:
                        try:
                            data = await self.http.request(
                                discord.http.Route("GET", "/guilds/{guild_id}/messages/search", guild_id=guild.id),
                                params={"author_id": str(self.user.id)},
                            )
                        except (discord.Forbidden, discord.HTTPException):
                            break
                        except Exception:
                            break

                        total = data.get("total_results", 0)
                        if total == 0:
                            break

                        msg_groups = data.get("messages", [])
                        if not msg_groups:
                            break

                        deleted_this_batch = False
                        for group in msg_groups:
                            for msg_data in group:
                                if not msg_data.get("hit"):
                                    continue
                                if msg_data["author"]["id"] != str(self.user.id):
                                    continue

                                msg_id = int(msg_data["id"])
                                ch_id = int(msg_data["channel_id"])

                                if msg_id == status_id:
                                    continue

                                try:
                                    ch = self.get_channel(ch_id)
                                    if ch:
                                        target = await ch.fetch_message(msg_id)
                                        await target.delete()
                                        count += 1
                                        deleted_this_batch = True
                                        print(f"[{self.user}] Deleted ({count}) #{ch.name} — {guild.name}")

                                        if count % 10 == 0:
                                            try:
                                                await message.edit(content=f"**Deletion in progress... ({count})**")
                                            except Exception:
                                                pass
                                except Exception:
                                    pass

                                await asyncio.sleep(1)

                        if not deleted_this_batch:
                            break
                        await asyncio.sleep(2)

                for ch in dms_to_delete:
                    print(f"[{self.user}] Searching in DM/Group...")
                    try:
                        async for msg in ch.history(limit=None):
                            if msg.author.id != self.user.id:
                                continue
                            if msg.id == status_id:
                                continue
                            try:
                                await msg.delete()
                                count += 1
                                print(f"[{self.user}] Deleted ({count}) DM/Group")

                                if count % 10 == 0:
                                    try:
                                        await message.edit(content=f"**Deletion in progress... ({count})**")
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            await asyncio.sleep(1)
                    except Exception:
                        pass

                try:
                    await message.edit(content=f"**Done — {count} messages deleted**")
                    await asyncio.sleep(5)
                    await message.delete()
                except Exception:
                    pass

                print(f"[{self.user}]  Done — {count} messages deleted")

            except asyncio.TimeoutError:
                await message.edit(content="Deletion cancelled (timeout).")
                await asyncio.sleep(3)
                try:
                    await message.delete()
                except Exception:
                    pass
            finally:
                self.waiting_confirm.discard(message.channel.id)

            return

        # Skip auto-react and auto-delete for system messages (group rename, member add/remove…)
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return

        if self.auto_react_emoji:
            try:
                await message.add_reaction(self.auto_react_emoji)
            except Exception:
                pass

        if self.delete_delay > 0:
            asyncio.create_task(self.auto_delete(message))



REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Blokself"

def get_auto_launch():
    try:
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        value, regtype = winreg.QueryValueEx(registry_key, APP_NAME)
        winreg.CloseKey(registry_key)
        return True
    except WindowsError:
        return False

def set_auto_launch(enable):
    try:
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE)
        if enable:
            script_path = os.path.abspath(sys.argv[0])
            if script_path.endswith('.py'):
                pythonw_exe = sys.executable.replace("python.exe", "pythonw.exe")
                cmd = f'"{pythonw_exe}" "{script_path}"'
            else:
                cmd = f'"{script_path}"'
            winreg.SetValueEx(registry_key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(registry_key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(registry_key)
    except WindowsError as e:
        print(f"Erreur registre: {e}")

def get_tokens():
    if not os.path.exists(TOKENS_FILE):
        return []
    with open(TOKENS_FILE, "r", encoding="utf-8-sig") as f:
        raw_lines = f.readlines()
    tokens = []
    for line in raw_lines:
        clean = line.strip().strip("\ufeff").strip("\r").strip("\n").strip()
        clean = ''.join(c for c in clean if c.isprintable() and c != ' ')
        if clean and not clean.startswith("#") and len(clean) > 20:
            tokens.append(clean)
    return tokens

def cleanup_config(active_tokens):
    try:
        with config_lock:
            if not os.path.exists(CONFIG_FILE):
                return
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return
                data = json.loads(content)
            
            active_set = {t.strip() for t in active_tokens}
            original_keys = list(data.keys())
            changed = False
            for token_key in original_keys:
                if token_key.strip() not in active_set:
                    del data[token_key]
                    changed = True
            
            if changed:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                print("Cleaned up orphaned configurations from config.json.")
    except Exception as e:
        print(f"Error cleaning up config: {e}")

def remove_token_from_file(token):
    try:
        if not os.path.exists(TOKENS_FILE):
            return
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            clean = line.strip().strip("\ufeff").strip("\r").strip("\n").strip()
            clean = ''.join(c for c in clean if c.isprintable() and c != ' ')
            if clean == token.strip():
                continue
            new_lines.append(line)
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception:
        pass

def check_single_instance():
    global mutex_handle
    mutex_name = "Global\\Blokself_Single_Instance_Mutex"
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.GetLastError.argtypes = []
        kernel32.GetLastError.restype = ctypes.c_ulong
        
        mutex_handle = kernel32.CreateMutexW(None, True, mutex_name)
        last_error = kernel32.GetLastError()
        
        if last_error == 183:
            return False
        return True
    except Exception:
        return True

def release_single_instance():
    global mutex_handle
    if mutex_handle:
        try:
            ctypes.windll.kernel32.CloseHandle(mutex_handle)
        except Exception:
            pass
        mutex_handle = None

bots_list = []
loop = asyncio.new_event_loop()

def update_tray_menu():
    global tray_icon
    if 'tray_icon' in globals() and tray_icon:
        try:
            tray_icon.menu = pystray.Menu(setup_menu)
        except Exception:
            pass


async def run_bots_async(tokens):
    tasks = []
    for token in tokens:
        bot = BlokselfBot(token)
        bot.load_settings()
        bot.login_failed = False
        bots_list.append(bot)
        
        async def start_bot(b, t):
            try:
                await b.start(t)
            except discord.LoginFailure:
                b.login_failed = True
                print(f"Login failed for token ending in ...{t[-10:]}")
                remove_token_from_file(t)
                cleanup_config(get_tokens())
                update_tray_menu()
            except Exception as e:
                b.login_failed = True
                print(f"Error starting bot: {e}")
                update_tray_menu()
                
        if getattr(bot, 'is_active', True):
            tasks.append(loop.create_task(start_bot(bot, token)))
            await asyncio.sleep(2)
            
    update_tray_menu()
        
    if tasks:
        await asyncio.gather(*tasks)

def start_discord_thread():
    tokens = get_tokens()
    if not tokens:
        os._exit(0)  

    cleanup_config(tokens)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bots_async(tokens))

def create_image():
    if os.path.exists("group.png"):
        try:
            return Image.open("group.png")
        except Exception:
            pass
    image = Image.new('RGB', (64, 64), color=(88, 101, 242))
    d = ImageDraw.Draw(image)
    d.text((10, 20), "B", fill=(255, 255, 255))
    return image

def on_quit(icon, item):
    icon.stop()
    for bot in bots_list:
        asyncio.run_coroutine_threadsafe(bot.close(), loop)
    loop.call_soon_threadsafe(loop.stop)
    release_single_instance()
    os._exit(0)

def on_restart(icon, item):
    import subprocess
    import time
    icon.stop()
    for bot in bots_list:
        asyncio.run_coroutine_threadsafe(bot.close(), loop)
    time.sleep(1)  
    release_single_instance()
    script_path = os.path.abspath(sys.argv[0])
    if script_path.endswith('.py'):
        pythonw_exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = sys.executable  
        subprocess.Popen(
            [pythonw_exe, script_path] + sys.argv[1:],
            creationflags=0x08000000  
        )
    else:
        subprocess.Popen(
            [script_path] + sys.argv[1:],
            creationflags=0x08000000
        )
    os._exit(0)

def refresh_tokens(icon=None, item=None):
    """Reload tokens from tokens.txt and start any new bots, stop bots for removed tokens."""
    current_tokens = set(get_tokens())
    existing_tokens = {bot.bot_token for bot in bots_list}
    
    for bot in list(bots_list):
        if bot.bot_token not in current_tokens:
            asyncio.run_coroutine_threadsafe(bot.close(), loop)
            bots_list.remove(bot)
    
    new_tokens = current_tokens - existing_tokens
    if new_tokens:
        asyncio.run_coroutine_threadsafe(start_new_bots(new_tokens), loop)
    cleanup_config(list(current_tokens))
    update_tray_menu()

async def start_new_bots(tokens_set):
    tasks = []
    for token in tokens_set:
        bot = BlokselfBot(token)
        bot.load_settings()
        bot.login_failed = False
        bots_list.append(bot)
        async def start_bot(b, t):
            try:
                await b.start(t)
            except discord.LoginFailure:
                b.login_failed = True
                print(f"Login failed for token ending in ...{t[-10:]}")
                remove_token_from_file(t)
                cleanup_config(get_tokens())
                update_tray_menu()
            except Exception as e:
                b.login_failed = True
                print(f"Error starting bot: {e}")
                update_tray_menu()
        tasks.append(loop.create_task(start_bot(bot, token)))
        await asyncio.sleep(2)
    if tasks:
        await asyncio.gather(*tasks)
        update_tray_menu()

def on_open_tokens(icon, item):
    os.startfile(TOKENS_FILE)

def toggle_auto_launch(icon, item):
    current = get_auto_launch()
    set_auto_launch(not current)

def is_auto_launch_checked(item):
    return get_auto_launch()

def get_bots_menu():
    items = []
    current_bots = list(bots_list)
    for i, bot in enumerate(current_bots):
        last_known_name = None
        try:
            with config_lock:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            data = json.loads(content)
                            last_known_name = data.get(bot.bot_token, {}).get("user_name")
        except Exception:
            pass

        if not getattr(bot, 'is_active', True):
            name = f"{last_known_name or 'Account'} (Disabled)"
        elif bot.is_ready():
            name = str(bot.user)
        elif getattr(bot, 'login_failed', False):
            name = f"{last_known_name or 'Account'} (Login Failed)"
        else:
            name = f"{last_known_name or 'Account'} (Connecting...)"
                
        def make_action(index):
            def action(icon, item):
                if index >= len(bots_list):
                    return
                b = bots_list[index]
                b.is_active = not getattr(b, 'is_active', True)
                b.save_settings()
                if not b.is_active:
                    asyncio.run_coroutine_threadsafe(b.close(), loop)
                else:
                    new_bot = BlokselfBot(b.bot_token)
                    new_bot.load_settings()
                    new_bot.login_failed = False
                    bots_list[index] = new_bot
                    
                    async def start_new_bot():
                        try:
                            await new_bot.start(new_bot.bot_token)
                        except discord.LoginFailure:
                            new_bot.login_failed = True
                            remove_token_from_file(new_bot.bot_token)
                            cleanup_config(get_tokens())
                            update_tray_menu()
                        except Exception:
                            new_bot.login_failed = True
                            update_tray_menu()
                            
                    asyncio.run_coroutine_threadsafe(start_new_bot(), loop)
                update_tray_menu()
            return action
            
        def make_checked(index):
            def checked(item):
                if index < len(bots_list):
                    return getattr(bots_list[index], 'is_active', True)
                return False
            return checked
            
        items.append(pystray.MenuItem(name, make_action(i), checked=make_checked(i)))
    return items

def _enable_dark_menus():
    """Force dark mode for context menus on Windows 10/11."""
    try:
        uxtheme = ctypes.windll.uxtheme
        # Ordinal 135 = SetPreferredAppMode, 136 = FlushMenuThemes
        set_mode = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)(135, uxtheme)
        flush   = ctypes.WINFUNCTYPE(None)(136, uxtheme)
        set_mode(2)   
        flush()
    except Exception:
        pass

def setup_menu():
    items = [
        pystray.MenuItem('\u2b21  Blokself', None, enabled=False),
        pystray.Menu.SEPARATOR,
    ]
    bots_items = get_bots_menu()
    if bots_items:
        items.extend(bots_items)
        items.append(pystray.Menu.SEPARATOR)
        
    items.extend([
        pystray.MenuItem('Open tokens.txt', on_open_tokens),
        pystray.MenuItem('Refresh tokens', refresh_tokens),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Launch on Startup', toggle_auto_launch, checked=is_auto_launch_checked),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Restart', on_restart),
        pystray.MenuItem('Quit', on_quit),
    ])
    return items

def setup_tray():
    global tray_icon
    
    _enable_dark_menus()
    
    tray_icon = pystray.Icon('Blokself', create_image(), 'Blokself', pystray.Menu(setup_menu))

    def delayed_notif():
        import time
        time.sleep(2)
        send_notification('Blokself', 'Blokself application started successfully.')
    threading.Thread(target=delayed_notif, daemon=True).start()
    tray_icon.run()

if __name__ == "__main__":
    
    tokens = get_tokens()
    if tokens and os.path.basename(sys.executable).lower() == "python.exe":
        pythonw_exe = sys.executable.lower().replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw_exe):
            subprocess.Popen(
                [pythonw_exe, os.path.abspath(sys.argv[0])] + sys.argv[1:],
                creationflags=0x08000000  
            )
            sys.exit(0)

    if not check_single_instance():
        print("Blokself is already running in the background.")
        send_notification("Blokself", "Blokself is already running in the background.")
        sys.exit(0)

    if not os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            f.write("# Put your tokens here (one per line)\n")

    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("{}\n")
            
    if not tokens:
        print("BLOKSELF")
        print("No token found.")
        try:
            token = input("Paste your token here: ").strip()
        except (EOFError, KeyboardInterrupt):
            release_single_instance()
            sys.exit(1)
        if len(token) > 20:
            with open(TOKENS_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n{token}\n")
            try:
                ans = input("Do you want the application to start automatically when Windows boots? (y/n): ").strip().lower()
                set_auto_launch(ans == 'y')
            except (EOFError, KeyboardInterrupt):
                set_auto_launch(False)
            print("Setup complete. Starting in background...")
            
            release_single_instance()
            pythonw_exe = sys.executable.lower().replace("python.exe", "pythonw.exe")
            if os.path.exists(pythonw_exe):
                subprocess.Popen(
                    [pythonw_exe, os.path.abspath(sys.argv[0])] + sys.argv[1:],
                    creationflags=0x08000000  
                )
                sys.exit(0)
        else:
            print("Invalid token.")
            release_single_instance()
            sys.exit(1)

    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        kernel32.GetConsoleWindow.argtypes = []
        kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.ShowWindow.restype = ctypes.c_bool
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long

        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            
            user32.ShowWindow(hwnd, 0)
            =
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                  (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    except Exception:
        pass
        
    discord_thread = threading.Thread(target=start_discord_thread, daemon=True)
    discord_thread.start()
    
    setup_tray()
