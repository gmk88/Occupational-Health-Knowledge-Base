from occupational_health.services.documents.auto_tagging import classify


def test_physical_scenario_by_keywords() -> None:
    result = classify("GBZ 2.2-2007 物理因素接触限值", "本标准规定了工作场所噪声与高温。")
    assert result["code"] == "physical"
    assert "类型:法规标准" in result["tags"]
    assert "因素:噪声" in result["tags"]


def test_assessment_scenario_by_keywords() -> None:
    result = classify("某某公司职业病危害因素检测报告", "检测结果如下：苯 6 mg/m3。")
    assert result["code"] == "assessment"
    assert "类型:检测评价" in result["tags"]
    assert "环节:检测" in result["tags"]


def test_health_surveillance_scenario_by_keywords() -> None:
    result = classify("职业健康监护年度总结", "上岗前体检结果与在岗期间复查。")
    assert result["code"] == "health_surveillance"
    assert "类型:健康监护" in result["tags"]


def test_chemical_scenario_by_keywords() -> None:
    result = classify("苯 化学品安全数据表", "本安全技术说明书说明危害与急救措施。")
    assert result["code"] == "chemical"
    assert "类型:化学品安全" in result["tags"]


def test_unrelated_text_falls_back_to_general() -> None:
    result = classify("会议纪要", "今天讨论了排班与食堂菜单。")
    assert result["code"] == "general"
    assert result["confidence"] == 0.0
    assert "类型:其他资料" in result["tags"]
