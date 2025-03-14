from io import BytesIO
from typing import List

from atproto import models

from lib.bs.client import get_client
from lib.common_converter import get_did_from_post_uri
from lib.log import get_logger
from settings import settings
from watermarking.bucketio import get_author_app_passwd, get_images, get_metadata

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")

    metadata = get_metadata(settings.ORIGINAL_IMAGE_BUCKET_NAME, event["metadata"])
    metadatas = [i for i in metadata["value"]["embed"]["images"]]

    images: List = []
    image_alts: List = []
    image_aspect_ratios: List = []

    for image, prop in zip(get_images(event["out_image_paths"]), metadatas, strict=True):
        img_byte_arr = BytesIO()
        image.save(img_byte_arr, format=image.format)
        images.append(img_byte_arr.getvalue())
        image_alts.append(prop["alt"])
        prop_height: int = prop["aspect_ratio"]["height"]
        prop_width: int = prop["aspect_ratio"]["width"]
        image_aspect_ratios.append(
            models.AppBskyEmbedDefs.AspectRatio(height=prop_height, width=prop_width)
        )

    author_did = get_did_from_post_uri(metadata["uri"])
    author_app_passwd = get_author_app_passwd(author_did)
    user_client = get_client(author_did, author_app_passwd)
    resp: models.app.bsky.feed.post.CreateRecordResponse = user_client.send_images(
        text=metadata["value"]["text"],
        images=images,
        image_alts=image_alts,
        image_aspect_ratios=image_aspect_ratios,
        langs=metadata["value"]["langs"],
        facets=metadata["value"]["facets"],
        reply_to=metadata["value"]["reply"],
    )
    event["repost"] = resp.model_dump_json()
    return event


if __name__ == "__main__":
    data = {
        "metadata": "bafyreicrzbngyafoii5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum/yzw3jty3wrlfejayynmp6oh7/post.json",
        "image_paths": [
            "bafyreicrzbngyafoii5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum/yzw3jty3wrlfejayynmp6oh7/0.jpg"
        ],
        "post": '{"uri":"at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lkbbgnagi22s","value":{"created_at":"2025-03-13T14:07:55.542Z","text":"","embed":{"images":[{"alt":"","image":{"mime_type":"image/jpeg","size":243366,"ref":{"link":"bafkreifknnz267ikq25n2bclqz3w66c7viugjvqlz6cixowz7su6e57nya"},"py_type":"blob"},"aspect_ratio":{"height":744,"width":572,"py_type":"app.bsky.embed.defs#aspectRatio"},"py_type":"app.bsky.embed.images#image"}],"py_type":"app.bsky.embed.images"},"entities":null,"facets":null,"labels":null,"langs":["ja"],"reply":null,"tags":null,"py_type":"app.bsky.feed.post"},"cid":"bafyreicrzbngyafoii5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum"}',
        "out_image_paths": [
            "bafyreicrzbngyafoii5detj5qdjxjobogle5kqq763swj4rlan2dvjxkum/yzw3jty3wrlfejayynmp6oh7/0.png"
        ],
    }
    handler(data, {})
