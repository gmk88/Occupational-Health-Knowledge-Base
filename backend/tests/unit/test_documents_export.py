from types import SimpleNamespace

from occupational_health.api.routes.documents import export_documents


class _Service:
    def export_documents(self) -> list[dict]:
        return [
            {
                "文档ID": "doc-1",
                "文档名称": "GBZ 2.1-2019 工作场所有害因素职业接触限值",
                "原始文件名": "GBZ2.1规范.pdf",
                "标准号": "GBZ 2.1-2019",
                "标准主编号": "GBZ 2.1",
                "版本年份": 2019,
                "生命周期状态": "现行",
                "文档角色": "主标准",
                "场景": "化学毒物",
                "标签": "类型:法规标准、因素:化学毒物",
                "处理状态": "可检索",
                "版本号": 1,
                "页数": 80,
                "实施日期": "2020-04-01",
                "上传时间": "2026-11-01T10:00:00+08:00",
                "更新时间": "2026-11-18T10:00:00+08:00",
            }
        ]


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(document_service=_Service()))
    )


def test_export_documents_returns_excel_friendly_csv() -> None:
    response = export_documents(_request(), None)  # type: ignore[arg-type]
    assert response.status_code == 200
    assert response.media_type == "text/csv; charset=utf-8"
    assert response.body.startswith("\ufeff".encode("utf-8"))
    text = response.body.decode("utf-8")
    assert "文档名称,原始文件名,标准号" in text
    assert "GBZ 2.1-2019" in text
    assert "化学毒物" in text
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "filename*=UTF-8''" in disposition
