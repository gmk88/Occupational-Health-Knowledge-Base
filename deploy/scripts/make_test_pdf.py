from __future__ import annotations

from datetime import datetime
from pathlib import Path

import fitz

FONT = r"C:\Windows\Fonts\msyh.ttc"
OUTPUT = Path("var/testdata/sample.pdf")

PAGES = [
    (
        "工作场所有害因素职业接触限值\n"
        "苯（CAS 71-43-2）职业接触限值：PC-TWA 6 mg/m3，PC-STEL 10 mg/m3。\n"
        "喷漆岗位应加强局部通风，并按规定开展职业健康监护。\n"
        "姓名：张三，联系电话：13800138000，体检结论：未见明显异常。"
    ),
    (
        "噪声职业接触限值：每周工作 5 天、每天 8 小时等效声级为 85 dB(A)。\n"
        "长期接触超标噪声可能导致职业性噪声聋，应佩戴护听器。\n"
        "用人单位应定期开展职业病危害因素检测与评价。\n"
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}。"
    ),
]


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    for text in PAGES:
        page = document.new_page()
        if Path(FONT).is_file():
            page.insert_font(fontname="msyh", fontfile=FONT)
            font = "msyh"
        else:
            font = "helv"
        page.insert_textbox(fitz.Rect(60, 60, 540, 760), text, fontsize=14, fontname=font)
    document.save(OUTPUT)
    document.close()
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
