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
FONT_SIZE = 64
MAX_IMAGES = 4


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
            with BytesIO() as out:
                watermarked_img.save(out, format="PNG")
                out.seek(0)
                out_path = PurePosixPath(path).with_suffix(".png").as_posix()
                post_bytes_object(settings.WATERMARKED_IMAGE_BUCKET_NAME, out_path, out)
                out_image_paths.append(out_path)
                logger.info(f"Saved watermarked image to S3 {out_path}")
    event["out_image_paths"] = out_image_paths
    return event


if __name__ == "__main__":
    payload = {
        "metadata": "bafyreibulkhj5y5quqf73xlub47u42vs25l5lppqd6k5tknxcphiiywar4/yzw3jty3wrlfejayynmp6oh7/post.json",
        "image_paths": [
            "bafyreibulkhj5y5quqf73xlub47u42vs25l5lppqd6k5tknxcphiiywar4/yzw3jty3wrlfejayynmp6oh7/0.jpg"
        ],
        "post": '{"uri":"at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lk6w5lem4c2t","value":{"created_at":"2025-03-12T15:40:40.957Z","text":"","embed":{"images":[{"alt":"","image":{"mime_type":"image/jpeg","size":237449,"ref":{"link":"bafkreih4ywq2vxv7qssmi6tj6y5rwxi7t5qewb2q3tedbkambswowq2jf4"},"py_type":"blob"},"aspect_ratio":{"height":744,"width":572,"py_type":"app.bsky.embed.defs#aspectRatio"},"py_type":"app.bsky.embed.images#image"}],"py_type":"app.bsky.embed.images"},"entities":null,"facets":null,"labels":null,"langs":["ja"],"reply":null,"tags":null,"py_type":"app.bsky.feed.post"},"cid":"bafyreibulkhj5y5quqf73xlub47u42vs25l5lppqd6k5tknxcphiiywar4"}',
    }
    handler(payload, {})
