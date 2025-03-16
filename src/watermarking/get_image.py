import mimetypes
import pathlib
from io import BytesIO
from pathlib import PurePosixPath

from atproto import Client, IdResolver, models

from lib.aws.s3 import post_bytes_object, post_string_object
from lib.bs.client import get_client
from lib.bs.get_bsky_post_by_url import get_did_from_url, get_rkey_from_url
from lib.common_converter import get_id_of_did
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def _get_authors_pds_client(author_did: str) -> Client:
    resolver = IdResolver()
    did_doc = resolver.did.resolve(author_did)
    # Since the image to be acquired is stored in the PDS in which the author participates,
    # the Client of the PDS to which the author belongs is obtained from the author's DID.
    authors_pds_endpoint = did_doc.service[0].service_endpoint
    return Client(base_url=authors_pds_endpoint)


def _save_post_text_to_s3(
    base_path: pathlib.PurePosixPath, post: models.AppBskyFeedPost.GetRecordResponse
) -> str:
    """ポストの本文情報をS3に保存する"""
    post_obj_name = base_path.joinpath("post").with_suffix(".json")
    post_obj_name = post_obj_name.as_posix()
    post_string_object(settings.ORIGINAL_IMAGE_BUCKET_NAME, post_obj_name, post.model_dump_json())
    logger.info(f"Saved post to S3 {post_obj_name}")
    return post_obj_name


def handler(event, context):
    """SQSイベントが差すポストから画像を取得しS3バケットに保存する"""
    logger.info(f"Received event: {event}")
    uri = event["uri"]
    author_did = event["author_did"]

    rkey = get_rkey_from_url(uri)
    did = get_did_from_url(uri)
    client = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    post: models.AppBskyFeedPost.GetRecordResponse = client.get_post(
        post_rkey=rkey, profile_identify=did
    )

    authors_pds_client = _get_authors_pds_client(author_did)
    id_of_did = get_id_of_did(author_did)

    return_payload = {"metadata": {}, "image_paths": [], "post": {}}
    base_path = PurePosixPath(post.cid).joinpath(id_of_did)
    # ポストの本文情報をS3に保存
    return_payload["metadata"] = _save_post_text_to_s3(base_path, post)
    return_payload["post"] = post.model_dump_json()

    num_of_file = len(post.value.embed.images)
    # ポストに含まれる画像を取得しS3に保存
    for image, num_of_file in zip(post.value.embed.images, range(num_of_file)):
        blob_cid = image.image.cid.encode()
        blob = authors_pds_client.com.atproto.sync.get_blob(
            models.ComAtprotoSyncGetBlob.Params(cid=blob_cid, did=author_did)
        )
        # S3に画像とそのmetadataのセットを保存
        with BytesIO(blob) as f:
            img_object_name = base_path.joinpath(str(num_of_file)).with_suffix(
                mimetypes.guess_extension(image.image.mime_type)
            )
            img_object_name = img_object_name.as_posix()
            post_bytes_object(settings.ORIGINAL_IMAGE_BUCKET_NAME, img_object_name, f)
            return_payload["image_paths"].append(img_object_name)
            logger.info(f"Original image saved to S3 {img_object_name}")

    return return_payload


if __name__ == "__main__":
    sample_event = {
        "cid": "bafyreic4cvvpkc7k2v4g356byvft6uggsv3exzgoko6ptpk2aaxmx6igfi",
        "uri": "at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lkitc6qda22p",
        "author_did": "did:plc:yzw3jty3wrlfejayynmp6oh7",
        "created_at": "2025-03-16T14:16:11.638Z",
    }
    handler(sample_event, {})
