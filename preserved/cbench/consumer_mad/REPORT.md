# consumer_mad 修复与真实验证

状态：ready。没有启动 LLM 搜索。原始 cBench 目录未修改。

修复独立副本中的 Makefile/config1.h：排除已禁用的 ESD 后端，使用 util.c 自带 zlib 声明并链接现有 libz.so.1，保留 zlib 功能。

42 个 TU 均完成 LLVM 22.1.3 frontend → O3 opt → llc → 完整链接，同时完成 Clang O3 baseline。
dataset 1，CPU 0，原生内部循环 1742 次，输入参数、WAV 输出和 stderr MD5 检查保持不变。

| Baseline | 三次完整计时（秒） | 中位数（秒） |
|---|---|---:|
| Search | [2.544177664007293, 2.5709814070141874, 2.558924786018906] | 2.558924786 |
| Clang | [2.546809221006697, 2.531552148022456, 2.5620115409838036] | 2.546809221 |

静态主热点：`III_huffdecode`，`layer3.c:932-1271`。
非累计 Self 占全部采样 34.77%，项目源码采样 35.14%；归属样本 3641，总样本 10477，lost samples=0。
内联归属：III_huffdecode → III_decode → mad_layer_III；同一采样只计入主热点一次。
正确性预运行、三次正式计时、profiling 输出均与 search reference 一致。

新清单：configs/cbench_hotspots_dataset1_28.json（28 ready 热点，4 blocked；原有三个正确性豁免条目仍需补齐有效 baseline）。

复现命令（使用新的目录）：
```bash
python3 scripts/repair_consumer_mad.py \
  --work-root work/cbench-mad-reproduce \
  --out artifacts/cbench-mad-reproduce --cpu 0
```
