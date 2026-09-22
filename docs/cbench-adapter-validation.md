# cBench 适配验证结果

测试：`92 passed, 16 subtests passed`。原有 73 项 PolyBench 测试全部通过。

真实 LLVM smoke：离线 proposal，真实全程序编译、正确性检查和计时；CPU 3、NUMA 0、dataset 1 原生循环不变。

| 程序 | TU 数 | 原生循环 | Search baseline 三次时间（秒） | 中位数 | Teacher 中位数 | Recovery 中位数 |
|---|---:|---:|---|---:|---:|---:|
| network_dijkstra | 1 | 500000 | 0.334293, 0.333438, 0.342993 | 0.334293 | 0.336528 | 0.327166 |
| automotive_bitcount | 10 | 80 | 2.173630, 2.176555, 2.160127 | 2.173630 | 2.179874 | 2.207531 |
| consumer_mad | 42 | 1742 | 4.845590, 5.045744, 4.901985 | 4.901985 | 4.980962 | 5.006812 |

每个程序的四个阶段均通过输出 MD5 比对，每个阶段有 1 次预运行和 3 次完整有效计时。Recovery 的所有 TU 使用同一候选配置，原始 IR 哈希保持不变。Teacher 是语义等价替换；速度差不作为优化收益。

证据目录：

- [network_dijkstra](../artifacts/cbench-adapter-smoke-v3/network_dijkstra/)：构建命令、原始 IR、计时样本、prompt、候选配置及汇总。
- [automotive_bitcount](../artifacts/cbench-adapter-smoke-v3/automotive_bitcount/)：构建命令、原始 IR、计时样本、prompt、候选配置及汇总。
- [consumer_mad](../artifacts/cbench-adapter-smoke-v2/consumer_mad/)：构建命令、原始 IR、计时样本、prompt、候选配置及汇总。

`consumer_mad` 使用 v2 运行结果；随后 v3 仅修复选择性 resume 保留其他程序汇总的行为，构建和测量逻辑未改。Dijkstra、bitcount 已用 v3 再验证；Dijkstra 实际 resume 没有新增计时，bitcount 汇总保持原样。

- [完整机器可读验证报告](../artifacts/cbench-adapter-validation.json)
- [resume 验证](../artifacts/cbench-adapter-smoke-v3/resume_validation.json)
- [PolyBench 文件一致性](../artifacts/cbench-adapter-polybench-compatibility.json)
- [28 个程序的上下文字符数审计](../artifacts/cbench-adapter-context-audit.json)

本轮只对上述三个程序完成真实构建与搜索 smoke；其余 ready 条目已检查源码哈希、行范围、dataset 命令、原生循环与输入哈希，尚未在新适配器中逐个执行。四个历史构建失败条目仍为 blocked。没有启动正式 API 搜索，也没有重做 profiling。

运行命令与边界说明见 [cbench-adapter.md](cbench-adapter.md)。
