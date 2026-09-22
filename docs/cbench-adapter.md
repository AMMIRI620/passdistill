# cBench 最小接入

活动工程继续使用原有 Teacher → Distiller → Recovery 搜索。仅在
`search/teacher_search.py` 和 `search/recovery_search.py` 增加可选 `adapter` 参数；
不传时沿用原路径。PolyBench 的配置、evaluator、compiler、三份 prompt、catalog、
参数编辑器和入口脚本保持回退后的原样。

## 清单

- `configs/cbench_hotspots.json`：约 10 KB；28 个 ready 热点、4 个 blocked 程序。
  ready 条目只有程序名、文件名、仓库相对路径、函数名和起止行，不做源码哈希校验。
  一程序一热点，由已保留的真实采样清单提取，搜索过程不重新选择热点。
- `configs/cbench_builds.json`：28 个可定位程序的 TU、编译/链接参数、dataset 1 命令、
  原生循环、输入路径、输出和固定环境。`consumer_mad` 使用此前修复后的配置。
- 完整采样排名、inline chain、排除原因、原始 perf 和历史结果继续保留在
  `preserved/cbench/` 与 `artifacts/`。

重建轻量清单：

```bash
python3 scripts/extract_cbench_manifest.py
```

清单的 ready 只表示已有可定位热点，不替代本次构建、正确性与计时验证；没有继承
此前三个程序的正确性豁免。实际运行失败会记录 blocked。

## 边界与提示词

`passdistill/cbench/` 独立负责运行协议、构建、上下文、替换与适配，不导入旧 cBench
搜索实现，也不修改 PolyBench 配置类。

Teacher 使用 `prompt/cbench/Source Oracle.md`。输入为完整热点函数、明确的文件与行号、
构建参数、相关编译反馈、只读声明与本地头文件。不会展开项目调用图；常量表初始化和
可识别的其他函数体被省略。上下文筛选是语法处理，不是完整 C 依赖分析；它不会修改
实际构建源文件。模型可见文本和字符数保存在每轮 oracle 目录中。

Teacher 的 `source_patch` 是完整替换函数，保留原声明/签名；适配器按已审核的行范围
写回新副本。函数以外的源码不变，每个候选重新复制原项目并完整编译全部 TU。
不使用补丁中的路径，不把 Teacher 源码用于 Recovery。Distiller 继续调用原函数、
原 prompt，只传入原热点函数、替换函数以及相关 remarks。

Recovery 在原 prompt 前添加独立的 `prompt/cbench/Recovery Context.md`，说明这是
cBench 多文件完整程序调优。搜索主干负责一次性物化 pipeline；适配器将同一 pipeline
和 opt_options 应用于所有原始 TU IR，再链接。TU 失败直接失败；独立构建目录防止
复用其他候选对象文件。原 catalog、编辑数量和参数空间不增加限制。

## 计时与正确性

运行固定使用 `numactl --physcpubind=3 --membind=0`，绑定失败则运行失败，不静默退化。
dataset 1 命令、重定向和原生 `_finfo_dataset` 数值来自保留配置，并与原生定义比对。
外部执行三次不会改写程序内部循环次数。

每个完整程序先做一次正确性预运行，再进行三次完整计时执行。每次重新 staging，
重置输入、移除旧输出；staging、哈希、编译及报告写入不计时。使用进程完整 wall time。
search baseline 建立功能输出 MD5，Clang baseline、Teacher 和 Recovery 与之逐一比对。
任一运行失败、超时、缺少输出或输出不一致，则没有有效中位数，不重试或取部分样本。
`TimingResult.median` 因而可直接复用原有排序、promotion 和报告逻辑。

恢复运行只比较程序配置、热点位置、搜索配置和测量策略，不校验源码、IR、输入文件、
catalog、工具链或 prompt 的哈希；旧记录中的哈希不再参与校验。输出 MD5 仅用于
功能正确性测试。输出目录不覆盖历史结果；中断在 baseline 构建中间的运行需要新输出目录。

## 命令

回归测试：

```bash
/tmp/passdistill-test-env/bin/python -m pytest -q tests
```

离线完整 smoke（每程序 1 Teacher + 1 Recovery；proposal 不调用付费 API，其他阶段真实）：

```bash
python3 scripts/run_cbench.py \
  --program network_dijkstra automotive_bitcount consumer_mad \
  --smoke --output artifacts/cbench-smoke-new
```

只验证 baseline：

```bash
python3 scripts/run_cbench.py --program automotive_bitcount \
  --baseline-only --output artifacts/cbench-baseline-new
```

同配置恢复已开始的搜索：在原命令上添加 `--resume`，保持输出目录和其他选项不变。

`configs/cbench.json` 已提供三轮、每轮两 Teacher、总计六 Teacher 和五十 Recovery
候选预算；默认 `llm_backend=mock`。正式 API 搜索需要显式在独立配置中设置后端，
本次没有启动。API 客户端仍是原 PolyBench 客户端（包括原有 900 秒等待及其重试行为），
本次适配未修改它。

离线 smoke 的 Teacher 是带注释的语义等价替换，Recovery 为基线 pipeline 控制候选；
报告中的微小速度差是实测波动，不作为优化收益证据。
