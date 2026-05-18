from __future__ import annotations

import math


def paginate(page: int, page_size: int, total: int):
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }
