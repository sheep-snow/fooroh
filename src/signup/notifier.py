from atproto import models

from lib.bs.client import get_dm_client
from lib.bs.convos import leave_convo
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


msg = """Your App Password has been received and your user registration has been completed 🥳.

Next, please submit a watermark image with the Alt of 'fr'.
If you successfully received the password, this bot will notify you by DM.

You can re-register your watermark image as many times as you like!"""


def send_dm(dm, convo_id=None) -> models.ChatBskyConvoDefs.MessageView:
    resp = dm.send_message(
        models.ChatBskyConvoSendMessage.Data(
            convo_id=convo_id, message=models.ChatBskyConvoDefs.MessageInput(text=msg)
        )
    )
    leave_convo(dm, convo_id)
    return resp


def handler(event, context):
    logger.info(f"Received event: {event}")
    convo_id = event["convo_id"]
    dm_client = get_dm_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    dm = dm_client.chat.bsky.convo
    send_dm(dm, convo_id)
    # 見終わったDMは二度と見ないよう会話から脱退する
    leave_convo(dm, convo_id)
    logger.info(f"Left the convo `{convo_id}`.")
    return {"message": "OK", "status": 200}


# if __name__ == "__main__":
#     handler({"convo_id": "3lji2m35guy2l"}, {})
