import json

from atproto import Client

from lib.bs.client import get_client
from lib.common_converter import get_did_from_post_uri
from lib.log import get_logger
from settings import settings
from watermarking.bucketio import get_author_app_passwd, get_metadata

logger = get_logger(__name__)


def delete_repost(user_client: Client, repost_uri: str):
    if user_client.delete_post(repost_uri):
        msg = f"Watermarked deleted successfully, uri: {repost_uri}"
        logger.info(msg)
        return {"status": "success", "message": msg, "status_code": 200}
    else:
        msg = f"Failed to delete watermarked post, uri: {repost_uri}"
        logger.error(msg)
        return {"status": "error", "message": msg, "status_code": 500}


def handler(event, context):
    logger.info(f"Received event: {event}")

    metadata = get_metadata(settings.ORIGINAL_IMAGE_BUCKET_NAME, event["metadata"])
    original_post_uri = metadata["uri"]
    author_did = get_did_from_post_uri(original_post_uri)
    author_app_passwd = get_author_app_passwd(author_did)
    user_client = get_client(author_did, author_app_passwd)
    if user_client.delete_post(original_post_uri):
        msg = f"Original post deleted successfully, uri: {original_post_uri}"
        logger.info(msg)
        return {"status": "success", "message": msg, "status_code": 200}
    else:
        # This is a critical error, so we should raise an exception
        return delete_repost(user_client, json.loads(event["repost"])["uri"])


if __name__ == "__main__":
    data = {
        "metadata": "bafyreicrzbngyafoii5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum/yzw3jty3wrlfejayynmp6oh7/post.json",
        "image_paths": [
            "bafyreicrzbngyafoii5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum/yzw3jty3wrlfejayynmp6oh7/0.jpg"
        ],
        "post": '{"uri":"at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lkbbgnagi22s","valu...5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum"}',
        "out_image_paths": [
            "bafyreicrzbngyafoii5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum/yzw3jty3wrlfejayynmp6oh7/0.png"
        ],
        "repost": '{"uri":"at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lkbiwp3xbn2k","cid"...4673qll2azpj4tfwghcpj2y5v33bpwgdhix4p5xm"}',
    }
    handler(data, {})
