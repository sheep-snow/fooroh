from lib.bs.client import get_dm_client
from lib.bs.convos import send_dm_to_did
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)

msg = """Thanks for the follow-up 😀.
Please send your app password to this chat (DM).
The password you give us will be encrypted and stored securely,
and will only be used to provide the functionality of this bot."""


def handler(event, context):
    """ユーザにアプリパスワードの提供をDMで依頼する"""
    logger.info(f"Received event: {event}")

    did = event["did"]
    client = get_dm_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    send_dm_to_did(client.chat.bsky.convo, did, msg)
    return {"did": did}
