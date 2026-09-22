# cBench 重构保留资料

当前活动代码已恢复到 cBench 接入前的 PolyBench 副本。这里的数据用于后续重构，不表示旧 PolyBench 入口能够运行 cBench。

- 最新热点清单：[28 个 ready 热点](configs/cbench_hotspots_dataset1_28.json)，[解读](docs/cbench_hotspots_dataset1_28.md)。另外 4 个程序仍构建失败。3 个正确性豁免条目的热点 ready 不代表搜索 baseline 已完整有效。
- 原始 32 个程序的 dataset 1、原生循环、环境、TU、编译和链接配置：[构建运行清单](configs/cbench_build_run_dataset1.json)。原生循环不得用外部 3 次测量覆盖。
- consumer_mad 已修复配置：[program.json](consumer_mad/program.json)、[验证与测量](consumer_mad/verification.json)、[报告](consumer_mad/REPORT.md)、[构建补丁](patches/cbench/consumer_mad-linux-build.patch)。以此补充旧构建清单中的 mad 失败记录。
- mean3 / median3 历史配置均保留供审计；用户最后指定的是三次中位数。它们不是当前 PolyBench 的运行配置。

原始证据保持项目根目录下原路径：

- `artifacts/cbench-profile-unlocked-v2/`：原始 perf 数据。
- `artifacts/cbench-profile-analysis-v3/`：样本归属和排名。
- `artifacts/cbench-mad-repair-v3/`：mad 的真实构建、正确性、三次计时及采样。
- `work/cbench-native/`、`work/cbench-mad-repaired-v1/`：源码及已修复独立副本。
- `third_party/cBench_V1.1.tar.gz`：原始压缩包。

所有历史实验保留在 `artifacts/`。JSON 内已有证据路径保持原样；若引用已移出的 configs/docs，可在本目录对应路径或回退前归档中查找。完整回退前代码、参考副本、差异和文件哈希见 [rollback.json](rollback.json) 指定的归档目录。API 环境文件未修改；本次未启动实验。
