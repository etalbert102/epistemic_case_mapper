from __future__ import annotations

import os


DEFAULT_MEMO_READY_SECTION_NUM_PREDICT = 4096
DEFAULT_MEMO_READY_WHOLE_MEMO_NUM_PREDICT = 8192
DEFAULT_MEMO_READY_REPAIR_NUM_PREDICT = 8192


def memo_ready_section_num_predict() -> int:
    return _env_int("ECM_MEMO_READY_SECTION_NUM_PREDICT", DEFAULT_MEMO_READY_SECTION_NUM_PREDICT)


def memo_ready_whole_memo_num_predict() -> int:
    return _env_int("ECM_MEMO_READY_WHOLE_MEMO_NUM_PREDICT", DEFAULT_MEMO_READY_WHOLE_MEMO_NUM_PREDICT)


def memo_ready_repair_num_predict() -> int:
    return _env_int("ECM_MEMO_READY_REPAIR_NUM_PREDICT", DEFAULT_MEMO_READY_REPAIR_NUM_PREDICT)


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default
