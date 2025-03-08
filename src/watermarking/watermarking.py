import os
import sys

from PIL import Image, ImageDraw, ImageFont

from lib.log import get_logger

logger = get_logger(__name__)

original_image_bucket = os.getenv("ORIGINAL_IMAGE_BUCKET")
watermarks_image_bucket = os.getenv("WATERMARKS_IMAGE_BUCKET")
watermarked_image_bucket = os.getenv("WATERMARKED_IMAGE_BUCKET")


# 透かしの文字
my_mark = "@ITK"
# 出力ファイル名の接尾辞
out_file_suffix = "_wm"

OPACITY = 128
FONT_SIZE = 20


def add_watermark(input_img_path, output_img_path, watermark_text, position):
    # 画像を開く
    image = Image.open(input_img_path).convert("RGBA")

    # 透かし用のテキストイメージを作成
    watermark = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(watermark)
    # フォントの設定（フォントファイルのパスが必要です）
    font = ImageFont.truetype("arial.ttf", FONT_SIZE)
    # 透かしのテキストを描画
    text_width, text_height = draw.textlength(watermark_text, font=font), FONT_SIZE
    x, y = position
    draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, OPACITY))

    # 透かしを元の画像に合成
    watermarked = Image.alpha_composite(image, watermark)

    # 保存前にRGBAからRGBに変換（JPEG保存のため）
    rgb_image = watermarked.convert("RGB")
    rgb_image.save(output_img_path)


def handler(event, context):
    logger.info(f"Received event: {event}")

    # 引数のファイルをループして、複数の入力に対応させる
    for in_file_path in sys.argv[1:]:
        out_file_name, out_file_ext = os.path.splitext(os.path.basename(in_file_path))
        os_file_path = os.path.join(
            os.path.dirname(in_file_path), out_file_name + out_file_suffix + out_file_ext
        )
        add_watermark(sys.argv[1], os_file_path, my_mark, (100, 100), 10, 200)

    return {"message": "OK", "status": 200}


if __name__ == "__main__":
    print(handler({}, {}))
