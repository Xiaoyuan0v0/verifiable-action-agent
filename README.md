# 四次实验共用的 Python 起始工程

按课程分组完成，共同提交一份代码、报告和运行记录。每组选择一条路线，由一名成员负责运行 API；不要求成员重复开户、充值。

完整说明见上一级 [tutorial.md](../tutorial.md)。Python ≥ 3.10，仅标准库；无需安装任何第三方包。默认离线，不会自动调用付费 API。

在本目录执行：

```bash
python -m app doctor
python -m unittest discover -s tests_infra -v
```

选择 `travel` 或 `retail`，完成 `agent/loop.py`、`tools/dispatcher.py` 及所选 `domain_rules` 文件的三个函数。函数完成前，对应测试会提示 TODO；基础设施测试应通过。不要把另一条路线也当作必做任务。

```bash
python -m unittest discover -s tests_student/common -v
python -m unittest discover -s tests_student/travel -v
# 零售路线将 travel 改成 retail
```

完成实现后才运行：

```bash
python -m app run --route travel --mode mock --case standard --episode first_travel
python -m app show --episode first_travel
python scripts/check_episode.py --episode first_travel
python -m app export --episode first_travel
```

零售的 `standard` 和 `failure` 首先等待确认，需按教程 `confirm`、`resume`。真实调用必须显式指定 `--mode live` 并按教程第 4 节配置 DeepSeek Key 与费用估算。`mock` 固定脚本不会替你完成主循环，也不能作为真实模型证据。

本工程仅首次发放。后续在 `memory/`、`knowledge/`、`agent/verifier.py` 接口上扩展。保留 `lab1-loop` 版本与旧测试，长期记忆等接口目前尚未实现。
