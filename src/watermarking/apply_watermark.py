import json
from io import BytesIO
from pathlib import PurePosixPath
from typing import List

from PIL import Image

from lib.aws.s3 import get_object, post_bytes_object
from lib.common_converter import get_did_from_post_uri, get_id_of_did
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)

original_image_bucket = settings.ORIGINAL_IMAGE_BUCKET_NAME
watermarks_image_bucket = settings.WATERMARKS_BUCKET_NAME
watermarked_image_bucket = settings.WATERMARKED_IMAGE_BUCKET_NAME


OPACITY = 128
MAX_IMAGES = 4
MAX_SIZE = 950 * 1024  # max size of image in KB 976.56KB


def make_tile(target_width: int, target_height: int, tile_img: Image, wcnt: int) -> Image:
    """横にwcnt枚タイリングできるタイル画像を返す"""
    expected_width = target_width // wcnt
    expected_height = round(tile_img.height * expected_width / tile_img.width)
    # hcnt = target_height // expected_height
    hcnt = round(target_height / expected_height)
    resized_tile_img: Image = tile_img.resize((expected_width, expected_height))

    # base imageにタイル画像を敷き詰めたものを返す
    base_img = Image.new("RGBA", (target_width, target_height))
    for i in range(wcnt):
        for k in range(hcnt):
            base_img.paste(
                resized_tile_img, (i * resized_tile_img.size[0], k * resized_tile_img.size[1])
            )
    return base_img


def _resize(input_img: Image) -> Image:
    # RGBA画像をRGBに変換して保存サイズを削減
    if input_img.mode == "RGBA":
        with BytesIO() as out:
            input_img.save(out, format="PNG")
            saving_size_in_bytes = out.tell()
            logger.info(f"Original Size of image: {saving_size_in_bytes} bytes")
            if saving_size_in_bytes < MAX_SIZE:
                return input_img
            out.seek(0)
            input_img.convert("RGB").save(out, format="JPEG")
            saving_size_in_bytes = out.tell()
            if saving_size_in_bytes < MAX_SIZE:
                logger.info(f"RGB Converted Size of image: {saving_size_in_bytes} bytes")
                return input_img.convert("RGB")
            else:
                return input_img.convert("RGB").resize(
                    (input_img.width // 2, input_img.height // 2)
                )
    # すでにRGBまたはRGBAから品質低下させてもMAX_SIZEを超える場合は縮小画像を返す
    return input_img.resize((input_img.width // 2, input_img.height // 2))


def add_watermark(input_img: Image, watermark_img: Image) -> Image:
    """_summary_

    Args:
        input_img (Image): _description_
        watermark_text (_type_): _description_
        position (_type_): _description_
    TBD:
        official https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html
        https://note.com/sakamod/n/ne5a789a1733b
    """
    # 透かし適用対象画像をRGBAモードに変換
    tgt_img = input_img.convert("RGBA")
    watermark_img = make_tile(tgt_img.width, tgt_img.height, watermark_img, 6)

    # 元のウォーターマーク画像から、白を透過色として除外するマスクを適用した画像をウォーターマークとして適用する
    _, _, _, alpha = watermark_img.split()
    alpha_channel = 128
    alpha.paste(Image.new("L", watermark_img.size, alpha_channel), mask=alpha)
    watermark_mask = Image.composite(
        Image.new("RGBA", watermark_img.size, (255, 255, 255, 0)), watermark_img, alpha
    )
    clear_img = Image.new("RGBA", tgt_img.size, (255, 255, 255, 200))
    clear_img.paste(watermark_img, mask=watermark_mask)
    tgt_img = Image.blend(tgt_img, clear_img, 0.2)
    return tgt_img


def get_watermarks_img(post_uri: str) -> Image:
    did = get_did_from_post_uri(post_uri)
    id = get_id_of_did(did)
    metadata_path = PurePosixPath("metadatas").joinpath(id).with_suffix(".json")
    metadata_obj = get_object(settings.WATERMARKS_BUCKET_NAME, metadata_path.as_posix())
    with metadata_obj["Body"] as s:
        metadata = json.loads(s.data.decode("utf-8"))
    s3_obj = get_object(settings.WATERMARKS_BUCKET_NAME, metadata["path"])
    with BytesIO(s3_obj["Body"].read()) as f:
        img = Image.open(f).convert("RGBA")
        # 白色を透明化
        newData = []
        for data in img.getdata():
            if data[0] == 255 and data[1] == 255 and data[2] == 255:
                newData.append((255, 255, 255, 0))
            else:
                newData.append(data)
        img.putdata(newData)
        return img


def handler(event, context):
    logger.info(f"Received event: {event}")
    post = json.loads(event["post"])
    watermarks_img = get_watermarks_img(post["uri"])

    # post_metadata = event["metadata"]
    image_paths: List[str] = event["image_paths"]
    out_image_paths: List[str] = []
    # watermarking each image
    for path in image_paths[:MAX_IMAGES]:
        with BytesIO(get_object(settings.ORIGINAL_IMAGE_BUCKET_NAME, path)["Body"].read()) as f:
            watermarked_img = add_watermark(Image.open(f), watermarks_img)
            watermarked_img = _resize(watermarked_img)
            fmt, suffix = ("PNG", ".png") if watermarked_img.mode == "RGBA" else ("JPEG", ".jpg")
            with BytesIO() as out:
                watermarked_img.save(out, format=fmt)
                out.seek(0)
                out_path = PurePosixPath(path).with_suffix(suffix).as_posix()
                post_bytes_object(settings.WATERMARKED_IMAGE_BUCKET_NAME, out_path, out)
                out_image_paths.append(out_path)
                logger.info(f"Saved watermarked image to S3 {out_path}")
    event["out_image_paths"] = out_image_paths
    return event


if __name__ == "__main__":
    payload = {
        "metadata": "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/post.json",
        "image_paths": [
            "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/1.jpg",
            "bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy/yzw3jty3wrlfejayynmp6oh7/0.jpg",
        ],
        "post": '{"uri":"at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lkiwnvqvd22h","value":{"created_at":"2025-03-16T15:16:26.091Z","text":"","embed":{"images":[{"alt":"","image":{"mime_type":"image/jpeg","size":395930,"ref":{"link":"bafkreib72iihfumq2vdnx2wlm6atmop2yzoo4yktu67pxy3yulzky4jply"},"py_type":"blob"},"aspect_ratio":{"height":1022,"width":762,"py_type":"app.bsky.embed.defs#aspectRatio"},"py_type":"app.bsky.embed.images#image"},{"alt":"","image":{"mime_type":"image/jpeg","size":612791,"ref":{"link":"bafkreiflyaojb6gwgmhzlbyj5fh43bhaqdiimg5jthrqzu2n2h5ggtkzqe"},"py_type":"blob"},"aspect_ratio":{"height":1285,"width":1080,"py_type":"app.bsky.embed.defs#aspectRatio"},"py_type":"app.bsky.embed.images#image"}],"py_type":"app.bsky.embed.images"},"entities":null,"facets":null,"labels":null,"langs":["ja"],"reply":null,"tags":null,"py_type":"app.bsky.feed.post"},"cid":"bafyreibw75dotiuosaqkdiufhxstlh7ojar3vyqeow2ojy3l6rvqrcvtzy"}',
    }
    handler(payload, {})
