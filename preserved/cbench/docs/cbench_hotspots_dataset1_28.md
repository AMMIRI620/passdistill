# cBench dataset 1：28 个固定主热点

28 ready，4 blocked。consumer_mad 已修复并完成真实构建、正确性、三次中位数计时和采样。
原有三个正确性豁免条目仍需补齐有效 baseline；此文件不是可执行搜索 manifest。

| 程序 | 状态 | 主热点 | Self / 全部采样 |
|---|---|---|---:|
| automotive_bitcount | ready | bit_count | 37.45% |
| automotive_qsort1 | ready | qsortx | 17.48% |
| automotive_susan_c | ready | susan_corners | 96.87% |
| automotive_susan_e | ready | susan_edges | 70.99% |
| automotive_susan_s | ready | susan_smoothing | 99.89% |
| bzip2d | ready | BZ2_decompress | 55.31% |
| bzip2e | ready | mainQSort3 | 29.18% |
| consumer_jpeg_c | ready | encode_mcu_AC_refine | 28.10% |
| consumer_jpeg_d | ready | decode_mcu | 36.09% |
| consumer_lame | ready | L3psycho_anal | 18.93% |
| consumer_mad | ready | III_huffdecode | 34.77% |
| consumer_tiff2bw | ready | LZWDecode | 85.53% |
| consumer_tiff2rgba | ready | LZWDecode | 87.39% |
| consumer_tiffdither | ready | fsdither | 27.93% |
| consumer_tiffmedian | ready | create_colorcell | 57.83% |
| network_dijkstra | ready | dijkstra | 44.73% |
| network_patricia | ready | pat_search | 11.65% |
| office_ghostscript | blocked | — | — |
| office_ispell | blocked | — | — |
| office_rsynth | ready | resonator | 67.57% |
| office_stringsearch1 | ready | strsearch | 90.97% |
| security_blowfish_d | ready | BF_encrypt | 84.05% |
| security_blowfish_e | ready | BF_encrypt | 84.41% |
| security_pgp_d | blocked | — | — |
| security_pgp_e | blocked | — | — |
| security_rijndael_d | ready | decrypt | 71.01% |
| security_rijndael_e | ready | encrypt | 75.99% |
| security_sha | ready | sha_transform | 95.26% |
| telecom_CRC32 | ready | crc32file | 64.08% |
| telecom_adpcm_c | ready | adpcm_coder | 99.98% |
| telecom_adpcm_d | ready | adpcm_decoder | 99.96% |
| telecom_gsm | ready | Calculation_of_the_LTP_parameters | 41.78% |
