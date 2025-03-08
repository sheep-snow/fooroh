import re
from uuid import uuid4

pat_id_in_did = re.compile(r"^did:[a-z]+:([a-zA-Z0-9]+)$")
"""didからid部だけを取得するパターン"""


def get_id_of_did(did: str) -> str | None:
    """didからid部だけを取得する
    See:
        `did:plc:abcdefg` -> `abcdefg`
    """
    try:
        id = pat_id_in_did.match(did).groups()[0]
        if isinstance(id, str):
            return id
        else:
            return None
    except BaseException:
        return None


def generate_exec_id(did: str) -> str:
    """Statemachine の実行IDを生成する"""
    return f"{get_id_of_did(did)}-{str(uuid4())}"
