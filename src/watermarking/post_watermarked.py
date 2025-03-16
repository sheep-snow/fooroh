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

    metadata_key = event["metadata"]
    logger.debug(f"Getting metadata from `{settings.ORIGINAL_IMAGE_BUCKET_NAME}/{metadata_key}`...")
    metadata = get_metadata(settings.ORIGINAL_IMAGE_BUCKET_NAME, metadata_key)
    metadatas = [i for i in metadata["value"]["embed"]["images"]]

    images: List = []
    image_alts: List = []
    image_aspect_ratios: List = []

    for image, prop in zip(get_images(event["out_image_paths"]), metadatas, strict=True):
        with BytesIO() as img_byte_arr:
            image.save(img_byte_arr, format=image.format)
            images.append(img_byte_arr.getvalue())
            alt = prop.get("alt") if isinstance(prop.get("alt"), str) else ""
            image_alts.append(f"{alt} {settings.ALT_OF_SKIP_WATERMARKING}")
            prop_height: int = image.height
            prop_width: int = image.width
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
        "metadata": "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/post.json",
        "image_paths": [
            "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/0.jpg",
            "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/1.jpg",
        ],
        "post": '{"uri":"at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lkiwnvqvd22h","value":{"created_at":"2025-03-16T15:16:26.091Z","text":"","embed":{"images":[{"alt":"","image":{"mime_type":"image/jpeg","size":395930,"ref":{"link":"bafkreib72iihfumq2vdnx2wlm6atmop2yzoo4yktu67pxy3yulzky4jply"},"py_type":"blob"},"aspect_ratio":{"height":1022,"width":762,"py_type":"app.bsky.embed.defs#aspectRatio"},"py_type":"app.bsky.embed.images#image"},{"alt":"","image":{"mime_type":"image/jpeg","size":612791,"ref":{"link":"bafkreiflyaojb6gwgmhzlbyj5fh43bhaqdiimg5jthrqzu2n2h5ggtkzqe"},"py_type":"blob"},"aspect_ratio":{"height":1285,"width":1080,"py_type":"app.bsky.embed.defs#aspectRatio"},"py_type":"app.bsky.embed.images#image"}],"py_type":"app.bsky.embed.images"},"entities":null,"facets":null,"labels":null,"langs":["ja"],"reply":null,"tags":null,"py_type":"app.bsky.feed.post"},"cid":"bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy"}',
        "out_image_paths": [
            "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/0.png",
            "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/1.png",
        ],
    }
    handler(data, {})
