import json
import re

from atproto import models

from lib.aws.s3 import post_string_object
from lib.bs.client import get_dm_client
from lib.fernet import encrypt
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


class AppPasswordNotFoundError(Exception):
    pass


app_pass_pattern = re.compile(
    r"^\s*([a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4})\s*$"
)
"""Bluesky アプリパスワードの正規表現"""


def get_encrypted_app_password_from_convo(dm, convo_id) -> dict | None:
    """DMで送られたアプリパスワードを暗号化して取得する"""
    convo = dm.get_convo(models.ChatBskyConvoGetConvo.ParamsDict(convo_id=convo_id)).convo
    convo_sender_did = [
        member.did for member in convo.members if member.handle != settings.BOT_USERID
    ].pop()
    messages = dm.get_messages(
        models.ChatBskyConvoGetMessages.ParamsDict(convo_id=convo.id)
    ).messages

    latest_app_passwd_in_convo = None

    for m in messages:
        if m.sender.did == convo_sender_did and app_pass_pattern.match(m.text):
            latest_app_passwd_in_convo = encrypt(m.text.strip())
            logger.info(
                f"found App Password in Convo, message_id=`{m.id}`, from=`{m.sender.did}`, at=`{m.sent_at}`"
            )
    return {"app_password": latest_app_passwd_in_convo, "did": convo_sender_did}


def handler(event, context):
    logger.info(f"Received event: {event}")
    convo_id = event["convo_id"]
    dm_client = get_dm_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    dm = dm_client.chat.bsky.convo
    enc_passwd = get_encrypted_app_password_from_convo(dm, convo_id)
    if enc_passwd is None or len(enc_passwd) == 0:
        # アプリパスワードが見つからなかった場合は例外とし後続処理に流さない
        raise AppPasswordNotFoundError("No encrypted app password")

    post_string_object(settings.USERINFO_BUCKET_NAME, enc_passwd["did"], json.dumps(enc_passwd))
    logger.info(f"Saved metadata to `{settings.USERINFO_BUCKET_NAME}`")

    return {"convo_id": convo_id}


if __name__ == "__main__":
    handler({"convo_id": "3lji2m35guy2l"}, {})
