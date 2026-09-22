# cBench DMXAPI 实验

在项目根目录运行。默认读取 `.passdistill_dmxapi.env`，模型 `gpt-5.6-sol`。
配置为 `configs/cbench_dmxapi.json`：三轮、每轮两 Teacher，总计六 Teacher，
五十 Recovery 候选预算；CPU 3、NUMA 0、dataset 1 原生循环、三次取中位数。

```bash
# 启动 bitcount，后台持续运行；自动建立独立目录，不覆盖历史结果
python3 scripts/manage_cbench_run.py start --program automotive_bitcount

# 请求暂停；当前 API 请求、构建或整组三次计时会先完成
python3 scripts/manage_cbench_run.py pause

# 查看状态；activity.status=paused 才表示已经暂停
python3 scripts/manage_cbench_run.py status

# 继续同一进程；如果进程已退出，则从已有检查点恢复
python3 scripts/manage_cbench_run.py resume

# 切换接口配置，安全暂停后从原检查点自动继续
python3 scripts/manage_cbench_run.py switch-api --env-file .passdistill.env

# 实时查看进度、API 用量、计时与相对 search/clang baseline 的加速比
tail -f "$(python3 -c 'import json; print(json.load(open("artifacts/cbench-dmxapi-current.json"))["output"] + "/runner.log")')"
```

当前实验完成后，可选择多个程序或全部 28 个 ready 热点程序：

```bash
python3 scripts/manage_cbench_run.py start --program automotive_bitcount network_dijkstra
python3 scripts/manage_cbench_run.py start --all-ready
# 已完成 bitcount 后，只跑剩余 27 个 ready 程序
python3 scripts/manage_cbench_run.py start --all-ready --exclude automotive_bitcount
```

这些是不同的启动方式，选一条执行。同一时间只启动一个受管理实验，避免争用 CPU 3。
未指定 `--output` 的 pause/resume/status 操作指向最后启动的实验；也可以显式指定：

```bash
python3 scripts/manage_cbench_run.py pause --output artifacts/runs/你的运行目录
python3 scripts/manage_cbench_run.py resume --output artifacts/runs/你的运行目录
```

`start` 可用 `--config 配置.json`、`--env-file 环境文件` 和 `--output 新目录`。
启动时冻结配置，继续时使用该目录的配置与已记录的环境文件路径。密钥不会写入
控制记录或命令行。默认 API 主机来自环境文件，控制记录仅记录主机名。

暂停采用协作式检查点，不对进程发送 SIGSTOP，不会把暂停时间算入计时样本。
正在执行的 API 请求单次等待 900 秒，暂停请求不会取消或重发它。继续一个仍存活的
暂停进程不会重复该请求；进程失败后显式 resume 可能需要重新提交未完成的阶段。
编译 baseline 中途异常退出的目录仍应换新目录重新启动。

cBench 使用独立 DMXAPI 客户端：非流式请求、不发送 temperature，重试策略对齐
PolyBench：单次 900 秒超时，首次失败后最多再试 5 次（总计 6 次），间隔 1、2、4、8、16 秒。
断连、超时和 HTTP 失败重发原请求；收到非 JSON 文本才进入 JSON 修复。
所有尝试耗尽后才向搜索层报告失败，重试不额外消耗候选预算。重试详情仅写文件，
不输出 API 调用日志。每次请求的 prompt、响应、usage 和状态保存在对应 oracle/distill/
planner 目录。PolyBench 客户端与 prompt 不受影响。

`switch-api` 会先验证新环境文件，等待当前操作完成后在安全暂停处重启 worker。
模型与搜索配置保持不变；已完成的结果不覆盖。若暂停点恰好在 API 响应保存后，
恢复时仅对完全相同的 system/user 内容复用该响应一次，不重复提交付费请求。
切换记录只保存环境文件路径、主机名、模型和时间，不保存密钥。

完整日志为运行目录的 `runner.log`，结果为 `summary.json`。暂停进程仍占有该实验；
若需新实验，请先让当前实验继续并完成。退出状态可由 `status` 的 alive 与 activity 查看。

日志按程序序号、Teacher/Recovery 候选进度输出 `current_vs_search`、`current_vs_clang`、
`best_teacher_vs_search`、`best_teacher_vs_clang`、`best_recovery_vs_search`、
`best_recovery_vs_clang` 和最佳 Recovery ID。最优值覆盖同程序所有方向，并在 resume
时恢复；无效候选不参与排名，Recovery 最优值包含 search baseline。
主日志不输出 API 请求开始/结束、token 用量等调用信息；原始响应、usage、错误状态
仍保存在对应阶段文件中。运行进度快照为每个程序 `search/progress.json`。
