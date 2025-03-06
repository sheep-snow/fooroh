from atproto import Client, models

from lib.bs.client import get_client
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def get_followee(client: Client, did: str):
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
    folowee = [i for i in follows if i.did == did]
    return folowee.pop() if len(folowee) else None


def unfollow(client: Client, did: str):
    """フォローを解除する"""
    folowee = get_followee(client, did)
    if folowee is None:
        logger.info(f"User did `{did}` is not found.")
        return False
    follow_uri = folowee.viewer.following
    return client.unfollow(follow_uri=follow_uri)


def handler(event, context):
    logger.info(f"Received event: {event}")
    did = event["did"]
    logger.info(f"Unfollowing {did} ...")
    client = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    if unfollow(client, did):
        logger.info(f"Unfollowed `{did}` .")
    else:
        logger.info(f"Unfollowing `{did}` Skipped.")

    return {"did": did}


if __name__ == "__main__":
    print(handler({}, {}))
