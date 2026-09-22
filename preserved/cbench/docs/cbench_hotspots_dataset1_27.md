# cBench dataset 1：27 个固定主热点

此清单是静态热点清单，不是可直接启动搜索的运行 manifest。27 个热点 ready，5 个因构建失败 blocked。
用户授权仅对 consumer_lame、security_sha、security_rijndael_e 忽略输出正确性；历史 baseline 证据不改写。实验没有启动。

| 程序 | 状态 | 主热点 | 源文件及行范围 | Self / 全部采样 | 正确性策略 | 搜索准备状态 |
|---|---|---|---|---:|---|---|
| automotive_bitcount | ready | bit_count | bitcnt_1.c:9-20 | 37.45% | required | ready |
| automotive_qsort1 | ready | qsortx | qsort.c:39-120 | 17.48% | required | ready |
| automotive_susan_c | ready | susan_corners | susan.c:1443-1720 | 96.87% | required | ready |
| automotive_susan_e | ready | susan_edges | susan.c:1047-1278 | 70.99% | required | ready |
| automotive_susan_s | ready | susan_smoothing | susan.c:660-792 | 99.89% | required | ready |
| bzip2d | ready | BZ2_decompress | decompress.c:106-621 | 55.31% | required | ready |
| bzip2e | ready | mainQSort3 | blocksort.c:620-717 | 29.18% | required | ready |
| consumer_jpeg_c | ready | encode_mcu_AC_refine | jcphuff.c:613-734 | 28.10% | required | ready |
| consumer_jpeg_d | ready | decode_mcu | jdhuff.c:436-550 | 36.09% | required | ready |
| consumer_lame | ready | L3psycho_anal | psymodel.c:50-970 | 18.93% | waived_by_user | requires_valid_baseline_measurement |
| consumer_mad | blocked | — | — | — | required | blocked_build |
| consumer_tiff2bw | ready | LZWDecode | tif_lzw.c:310-473 | 85.53% | required | ready |
| consumer_tiff2rgba | ready | LZWDecode | tif_lzw.c:310-473 | 87.39% | required | ready |
| consumer_tiffdither | ready | fsdither | tiffdither.c:51-131 | 27.93% | required | ready |
| consumer_tiffmedian | ready | create_colorcell | tiffmedian.c:651-737 | 57.83% | required | ready |
| network_dijkstra | ready | dijkstra | dijkstra_large.c:96-134 | 44.73% | required | ready |
| network_patricia | ready | pat_search | patricia.c:314-343 | 11.65% | required | ready |
| office_ghostscript | blocked | — | — | — | required | blocked_build |
| office_ispell | blocked | — | — | — | required | blocked_build |
| office_rsynth | ready | resonator | nsynth.c:736-745 | 67.57% | required | ready |
| office_stringsearch1 | ready | strsearch | pbmsrch_large.c:46-71 | 90.97% | required | ready |
| security_blowfish_d | ready | BF_encrypt | bf_enc.c:72-140 | 84.05% | required | ready |
| security_blowfish_e | ready | BF_encrypt | bf_enc.c:72-140 | 84.41% | required | ready |
| security_pgp_d | blocked | — | — | — | required | blocked_build |
| security_pgp_e | blocked | — | — | — | required | blocked_build |
| security_rijndael_d | ready | decrypt | aes.c:769-827 | 71.01% | required | ready |
| security_rijndael_e | ready | encrypt | aes.c:709-767 | 75.99% | waived_by_user | requires_valid_baseline_measurement |
| security_sha | ready | sha_transform | sha.c:38-96 | 95.26% | waived_by_user | requires_valid_baseline_measurement |
| telecom_CRC32 | ready | crc32file | crc_32.c:125-157 | 64.08% | required | ready |
| telecom_adpcm_c | ready | adpcm_coder | adpcm.c:72-173 | 99.98% | required | ready |
| telecom_adpcm_d | ready | adpcm_decoder | adpcm.c:175-252 | 99.96% | required | ready |
| telecom_gsm | ready | Calculation_of_the_LTP_parameters | long_term.c:73-208 | 41.78% | required | ready |

三个新增条目：

- consumer_lame：L3psycho_anal，psymodel.c:50–970；已有 1,170 个归属样本，Self 18.93%。旧 search/Clang baseline 均无有效三次计时。
- security_sha：sha_transform，sha.c:38–96；已有 12,494 个归属样本，Self 95.26%。旧 search/Clang baseline 均无有效三次计时。
- security_rijndael_e：encrypt，aes.c:709–767；已有 15,447 个归属样本，Self 75.99%。旧 search baseline 的三次计时有效；Clang baseline 无有效计时且曾崩溃。

Self 比例是采样 period 比例，不是加速比。完整排名、样本归属和 perf.data 路径保存在 JSON 的 evidence 中。
