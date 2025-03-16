import json
from io import BytesIO
from typing import Generator, List, Optional

from PIL import Image
from pydantic import Json

from lib.aws.s3 import get_object
from lib.common_converter import get_id_of_did
from lib.fernet import decrypt
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


class InvalidAuthorDidError(Exception):
    pass


def get_author_app_passwd(author_did: str) -> str:
    """userinfo の中から author_did に対応する app_password を取得する"""
    userinfo = get_object(settings.USERINFO_BUCKET_NAME, get_id_of_did(author_did))["Body"]
    userinfo = json.loads(userinfo.read().decode("utf-8"))
    if userinfo["did"] == author_did:
        return decrypt(userinfo["app_password"])
    else:
        raise InvalidAuthorDidError("Author DID is not matched.")


def get_images(paths: Optional[List[str]] = None) -> Generator[Image, None, None]:
    """画像を取得して返すジェネレータ"""
    for path in paths:
        with BytesIO(get_object(settings.WATERMARKED_IMAGE_BUCKET_NAME, path)["Body"].read()) as f:
            yield Image.open(f)
    return None


def get_metadata(bucket, key) -> Json:
    """metadata の内容を返す"""
    metadata = get_object(bucket, key)["Body"].read().decode("utf-8")
    return json.loads(metadata)
