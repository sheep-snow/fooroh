import re

import atproto
from atproto import Client, models

from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def is_follower(client: atproto.Client, did: str) -> bool:
    """Check if the event is a follow event"""
    resp: models.AppBskyGraphGetFollowers.Response = client.get_followers(settings.BOT_USERID)
    if len([i for i in resp.followers if i.did == did]) > 0:
        return True
    else:
        return False


def get_followers(client: Client):
    """Get the list of users that are following the bot"""
    cursor = None
    followers = []

    while True:
        fetched: models.AppBskyGraphGetFollowers.Response = client.get_followers(
            actor=client.me.did, cursor=cursor
        )
        followers = followers + fetched.followers
        if not fetched.cursor:
            break
        cursor = fetched.cursor
    return set([i.did for i in followers])


def get_follows(client: Client):
    """Get the list of users that the bot is following"""
    cursor = None
    follows = []

    while True:
        fetched: models.AppBskyGraphGetFollows.Response = client.get_follows(
            actor=client.me.did, cursor=cursor
        )
        follows = follows + fetched.follows
        if not fetched.cursor:
            break
        cursor = fetched.cursor
    return set([i.did for i in follows])


def get_list_members(client: Client, list_uri: str):
    """Get the list of users in the list"""
    try:
        mat = re.match(
            r"^https://bsky.app/profile/(did:plc:[a-z0-9]+)/lists/([a-z0-9]+)$", list_uri
        )
        if mat.groups() is None:
            logger.warning(f"Invalid list uri: `{list_uri}`")
            return set()
        list_did, id = mat.groups()
        aturi = f"at://{list_did}/app.bsky.graph.list/{id}"
        ignore_list = client.app.bsky.graph.get_list(models.AppBskyGraphGetList.Params(list=aturi))
        return set([item.subject.did for item in ignore_list.items])
    except Exception as e:
        logger.warning(f"Failed to get ignore list members: `{str(e)}`")
        return set()
