import logging
from typing import Union, Dict, List, Optional

from kantex.md import *
from spamwatch.types import Permission
from telethon.utils import get_display_name
from telethon.tl.custom import Forward, Message
from telethon.tl.types import MessageEntityMention, MessageEntityMentionName, User, Channel

from kantek import Database
from kantek.utils import helpers, constants
from kantek import Client
from kantek.utils.errors import Error
from kantek.utils.pluginmgr import k
from kantek.utils.tags import Tags

tlog = logging.getLogger('kantek-channel-log')


@k.command('user', 'u')
async def user_info(msg: Message, tags: Tags, client: Client, db: Database,
                    args: List, kwargs: Dict) -> Optional[KanTeXDocument]:
    """Show information about a user. Can be used in reply to a message.

    Arguments:
        `ids`: List of User IDs
        `-mention`: Mention the user
        `-id`: Output information in a `name: id` format
        `-full`: Output the full message a user was banned for
        `-sw`: Output all information from the SpamWatch API
        `-gban`: Output user ids space seperated for `{prefix}gban`
        `-all`: Enable all of the flags below
        `-general`: General info, enabled by default
        `-bot`: Output bot specific information
        `-misc`: Output miscellaneous information

    Tags:
        strafanzeige:
            True: Append a short value to autofill user id and message link for {prefix}gban

    Examples:
        {cmd} 777000
        {cmd} 777000 -mention
        {cmd} 777000 -mention -id
        {cmd} @username
        {cmd} 777000 -all
        {cmd} 777000 -sw
        {cmd} -sa
        {cmd} 777000 mention:True
    """
    if not args and msg.is_reply:
        return await _info_from_reply(client, msg, db, kwargs, tags)
    elif args:
        return await _info_from_arguments(client, msg, db, args, kwargs)


async def _info_from_arguments(client, msg, db, args, kwargs) -> KanTeXDocument:
    gban_format = kwargs.get('gban', False)
    entities = []
    for entity in msg.get_entities_text():
        obj, text = entity
        if isinstance(obj, MessageEntityMentionName):
            entities.append(obj.user_id)
        elif isinstance(obj, MessageEntityMention):
            entities.append(text)
    # append any user ids to the list
    for uid in args:
        if isinstance(uid, int):
            entities.append(uid)

    users = []
    errors = []
    for entity in entities:
        try:
            user: User = await client.get_entity(entity)
            if isinstance(user, Channel):
                errors.append(str(entity))
                continue
            users.append(str(await _collect_user_info(client, user, db, **kwargs)))
        except constants.GET_ENTITY_ERRORS:
            errors.append(str(entity))
    if users and gban_format:
        users = [Code(' '.join(users))]
    if users or errors:
        return KanTeXDocument(*users, (Section('Errors for', Code(', '.join(errors)))) if errors else '')


async def _info_from_reply(client, msg, db, kwargs, tags) -> KanTeXDocument:
    get_forward = kwargs.get('forward', True)
    anzeige = tags.get('strafanzeige', False) or kwargs.get('sa', False)

    reply_msg: Message = await msg.get_reply_message()

    if get_forward and reply_msg.forward is not None:
        forward: Forward = reply_msg.forward
        if forward.sender_id is None:
            raise Error('User has forward privacy enabled')
        user: User = await client.get_entity(forward.sender_id)
    else:
        user: User = await client.get_entity(reply_msg.sender_id)
    user_section = await _collect_user_info(client, user, db, **kwargs)
    if anzeige and isinstance(user_section, Section):
        data = await helpers.create_strafanzeige(user.id, reply_msg)
        key = await db.strafanzeigen.add(data)
        user_section.append(SubSection('Strafanzeige', KeyValueItem('code', Code(f'sa: {key}'))))
    return KanTeXDocument(user_section)


async def _collect_user_info(client, user, db, **kwargs) -> Union[str, Section, KeyValueItem]:
    id_only = kwargs.get('id', False)
    gban_format = kwargs.get('gban', False)
    show_general = kwargs.get('general', True)
    show_bot = kwargs.get('bot', False)
    show_misc = kwargs.get('misc', False)
    show_all = kwargs.get('all', False)
    full_ban_msg = kwargs.get('full', False)
    show_spamwatch = kwargs.get('sw', False)

    if show_all:
        show_general = True
        show_bot = True
        show_misc = True
        show_spamwatch = True

    mention_name = kwargs.get('mention', False)

    full_name = get_display_name(user)
    if mention_name:
        title = Link(full_name, f'tg://user?id={user.id}')
    else:
        title = Bold(full_name)

    sw_ban = None
    ban_reason = await db.banlist.get(user.id)
    if ban_reason:
        ban_reason = ban_reason.reason
    if client.sw and client.sw.permission.value <= Permission.User.value:
        sw_ban = client.sw.get_ban(int(user.id))
        if sw_ban:
            ban_message = sw_ban.message
            if ban_message and not full_ban_msg:
                ban_message = f'{ban_message[:128]}{"[...]" if len(ban_message) > 128 else ""}'

    if id_only:
        return KeyValueItem(title, Code(user.id))
    elif gban_format:
        return str(user.id)
    else:
        general = SubSection(
            Bold('General'),
            KeyValueItem('id', Code(user.id)),
            KeyValueItem('first_name', Code(user.first_name)))
        if user.last_name is not None or show_all:
            general.append(KeyValueItem('last_name', Code(user.last_name)))
        if user.username is not None or show_all:
            general.append(KeyValueItem('username', Code(user.username)))

        if user.scam or show_all:
            general.append(KeyValueItem('scam', Code(user.scam)))

        if ban_reason:
            general.append(KeyValueItem('ban_reason', Code(ban_reason)))
        elif not show_spamwatch:
            general.append(KeyValueItem('gbanned', Code('False')))
        if sw_ban and not show_spamwatch:
            general.append(KeyValueItem('ban_msg', Code(ban_message)))

        spamwatch = SubSection('SpamWatch')
        if sw_ban:
            spamwatch.extend([
                KeyValueItem('reason', Code(sw_ban.reason)),
                KeyValueItem('date', Code(sw_ban.date)),
                KeyValueItem('timestamp', Code(sw_ban.timestamp)),
                KeyValueItem('admin', Code(sw_ban.admin)),
                KeyValueItem('message', Code(ban_message)),
            ])
        elif not client.sw:
            spamwatch.append(Italic('Disabled'))
        else:
            spamwatch.append(KeyValueItem('banned', Code('False')))

        bot = SubSection(
            Bold('Bot'),
            KeyValueItem('bot', Code(user.bot)),
            KeyValueItem('bot_chat_history', Code(user.bot_chat_history)),
            KeyValueItem('bot_info_version', Code(user.bot_info_version)),
            KeyValueItem('bot_inline_geo', Code(user.bot_inline_geo)),
            KeyValueItem('bot_inline_placeholder',
                         Code(user.bot_inline_placeholder)),
            KeyValueItem('bot_nochats', Code(user.bot_nochats)))
        misc = SubSection(
            Bold('Misc'),
            KeyValueItem('mutual_contact', Code(user.mutual_contact)),
            KeyValueItem('restricted', Code(user.restricted)),
            KeyValueItem('restriction_reason', Code(user.restriction_reason)),
            KeyValueItem('deleted', Code(user.deleted)),
            KeyValueItem('verified', Code(user.verified)),
            KeyValueItem('min', Code(user.min)),
            KeyValueItem('lang_code', Code(user.lang_code)))

        return Section(title,
                       general if show_general else None,
                       spamwatch if show_spamwatch else None,
                       misc if show_misc else None,
                       bot if show_bot else None)
