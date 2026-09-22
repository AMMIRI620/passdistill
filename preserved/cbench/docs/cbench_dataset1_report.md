# cBench dataset 1: hardware-sampled static hotspots

32 programs/variants; 27 profiles with source-located Self samples; 24 ready for search; 8 blocked.
Existing baseline measurements are preserved. Profiling durations are not performance samples. No formal LLM search was started.

| Program | Native repeat | Primary source function | Self / all events | Self / mapped project | Samples / lost | Mapping coverage | Status | Evidence |
|---|---:|---|---:|---:|---|---:|---|---|
| automotive_bitcount | 80 | bitcnt_1.c:bit_count:9-20 | 37.4545% | 37.4752% | 4635 / 0 | 99.9446% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/automotive_bitcount/profile.json) |
| automotive_qsort1 | 226 | qsort.c:qsortx:39-120 | 17.4829% | 38.2378% | 6933 / 0 | 45.7215% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/automotive_qsort1/profile.json) |
| automotive_susan_c | 782 | susan.c:susan_corners:1443-1720 | 96.8702% | 99.8691% | 7174 / 0 | 96.9971% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/automotive_susan_c/profile.json) |
| automotive_susan_e | 374 | susan.c:susan_edges:1047-1278 | 70.9886% | 71.6114% | 6882 / 0 | 99.1304% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/automotive_susan_e/profile.json) |
| automotive_susan_s | 49 | susan.c:susan_smoothing:660-792 | 99.8858% | 100.0000% | 5755 / 0 | 99.8858% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/automotive_susan_s/profile.json) |
| bzip2d | 80 | decompress.c:BZ2_decompress:106-621 | 55.3088% | 55.4245% | 12648 / 0 | 99.7913% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/bzip2d/profile.json) |
| bzip2e | 40 | blocksort.c:mainQSort3:620-717 | 29.1761% | 29.3641% | 9999 / 0 | 99.3596% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/bzip2e/profile.json) |
| consumer_jpeg_c | 2114 | jcphuff.c:encode_mcu_AC_refine:613-734 | 28.1036% | 28.3668% | 10391 / 0 | 99.0722% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/consumer_jpeg_c/profile.json) |
| consumer_jpeg_d | 8750 | jdhuff.c:decode_mcu:436-550 | 36.0863% | 37.4803% | 10243 / 0 | 96.2806% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/consumer_jpeg_d/profile.json) |
| consumer_lame | 228 | psymodel.c:L3psycho_anal:50-970 | 18.9280% | 21.0906% | 6182 / 0 | 89.7462% | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/consumer_lame/profile.json) |
| consumer_mad | 1742 | — | — | — | 0 / — | — | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/consumer_mad/preparation.json) |
| consumer_tiff2bw | 6757 | tif_lzw.c:LZWDecode:310-473 | 85.5270% | 88.2038% | 12855 / 0 | 96.9652% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/consumer_tiff2bw/profile.json) |
| consumer_tiff2rgba | 6579 | tif_lzw.c:LZWDecode:310-473 | 87.3913% | 91.1939% | 13741 / 0 | 95.8301% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/consumer_tiff2rgba/profile.json) |
| consumer_tiffdither | 5000 | tiffdither.c:fsdither:51-131 | 27.9258% | 28.2320% | 14092 / 0 | 98.9157% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/consumer_tiffdither/profile.json) |
| consumer_tiffmedian | 3659 | tiffmedian.c:create_colorcell:651-737 | 57.8349% | 58.9595% | 9793 / 0 | 98.0925% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/consumer_tiffmedian/profile.json) |
| network_dijkstra | 500000 | dijkstra_large.c:dijkstra:96-134 | 44.7319% | 77.8767% | 690 / 0 | 57.4394% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/network_dijkstra/profile.json) |
| network_patricia | 50000 | patricia.c:pat_search:314-343 | 11.6539% | 41.8697% | 4261 / 0 | 27.8337% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/network_patricia/profile.json) |
| office_ghostscript | 40 | — | — | — | 0 / — | — | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/office_ghostscript/preparation.json) |
| office_ispell | 3662 | — | — | — | 0 / — | — | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/office_ispell/preparation.json) |
| office_rsynth | 1300 | nsynth.c:resonator:736-745 | 67.5673% | 70.0714% | 5831 / 0 | 96.4263% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/office_rsynth/profile.json) |
| office_stringsearch1 | 2778240 | pbmsrch_large.c:strsearch:46-71 | 90.9678% | 96.8924% | 5173 / 0 | 93.8855% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/office_stringsearch1/profile.json) |
| security_blowfish_d | 180006 | bf_enc.c:BF_encrypt:72-140 | 84.0508% | 84.0601% | 16484 / 0 | 99.9890% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/security_blowfish_d/profile.json) |
| security_blowfish_e | 180006 | bf_enc.c:BF_encrypt:72-140 | 84.4102% | 84.4170% | 16843 / 0 | 99.9919% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/security_blowfish_e/profile.json) |
| security_pgp_d | 41673 | — | — | — | 0 / — | — | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/security_pgp_d/preparation.json) |
| security_pgp_e | 6072 | — | — | — | 0 / — | — | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/security_pgp_e/preparation.json) |
| security_rijndael_d | 129007 | aes.c:decrypt:769-827 | 71.0096% | 88.3203% | 20690 / 0 | 80.4001% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/security_rijndael_d/profile.json) |
| security_rijndael_e | 129259 | aes.c:encrypt:709-767 | 75.9897% | 96.8364% | 20340 / 0 | 78.4722% | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/security_rijndael_e/profile.json) |
| security_sha | 321506 | sha.c:sha_transform:38-96 | 95.2573% | 98.2639% | 13124 / 0 | 96.9403% | blocked | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/security_sha/profile.json) |
| telecom_CRC32 | 3431 | crc_32.c:crc32file:125-157 | 64.0830% | 100.0000% | 4014 / 0 | 64.0830% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/telecom_CRC32/profile.json) |
| telecom_adpcm_c | 6644 | adpcm.c:adpcm_coder:72-173 | 99.9805% | 100.0000% | 12101 / 0 | 99.9805% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/telecom_adpcm_c/profile.json) |
| telecom_adpcm_d | 14287 | adpcm.c:adpcm_decoder:175-252 | 99.9606% | 100.0000% | 8609 / 0 | 99.9606% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/telecom_adpcm_d/profile.json) |
| telecom_gsm | 558 | long_term.c:Calculation_of_the_LTP_parameters:73-208 | 41.7841% | 41.9638% | 8004 / 0 | 99.5718% | ready | [record](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-profile-analysis-v3/telecom_gsm/profile.json) |

Self counts each sample once at its innermost eligible source function; no Children accumulation. The all-event denominator retains loader/library/unmapped samples. cpu_core/cycles/u and cpu_atom/cycles/u breakdowns are retained. Source ranges come from Clang AST; TU identity from DWARF compilation units; raw binary symbols from llvm-nm. Full inline chains, ranked eligible functions and excluded samples are in each analysis directory.

## Preserved baseline timings

| Program | Three search-baseline times (s) | Arithmetic mean (s) | Clang mean (s) |
|---|---|---:|---:|
| automotive_bitcount | [1.127007280003454, 1.124136553000426, 1.1340171629999531] | 1.1283869986679445 | 1.1116871520013472 |
| automotive_qsort1 | [1.7165030340038356, 1.7010085369984154, 1.6926896990044042] | 1.7034004233355517 | 1.7041048450021965 |
| automotive_susan_c | [1.7865411699967808, 1.7931213389965706, 1.787267173996952] | 1.7889765609967678 | 1.7932613420004297 |
| automotive_susan_e | [1.7462961549972533, 1.7572886779962573, 1.7298182390004513] | 1.744467690664654 | 1.7528585246691364 |
| automotive_susan_s | [1.4136496999999508, 1.4184241369948722, 1.4156709529997897] | 1.4159149299982043 | 1.4200760953341767 |
| bzip2d | [3.2597863100018003, 3.248920268997608, 3.269686925006681] | 3.2594645013353634 | 3.245757289664956 |
| bzip2e | [2.491508959996281, 2.501323354001215, 2.502159814001061] | 2.4983307093328526 | 2.536811788998117 |
| consumer_jpeg_c | [2.628650660997664, 2.7337786720017903, 2.682810576996417] | 2.6817466366652902 | 3.598120420666722 |
| consumer_jpeg_d | [2.686889843993413, 2.833577901998069, 2.675659767999605] | 2.7320425046636956 | 2.7816377049991083 |
| consumer_lame | [] | None | None |
| consumer_mad | [] | None | None |
| consumer_tiff2bw | [3.3168622640005196, 3.321442256004957, 3.509628621999582] | 3.382644380668353 | 3.454722185332988 |
| consumer_tiff2rgba | [3.7184823749994393, 3.9933612660024664, 4.035145483998349] | 3.9156630416667517 | 3.7799253403330417 |
| consumer_tiffdither | [3.6234980360022746, 3.6168822840045323, 3.6016485229993123] | 3.614009614335373 | 3.529675193999234 |
| consumer_tiffmedian | [2.4486657450033817, 2.445540697000979, 2.4535054189982475] | 2.4492372870008694 | 2.4486784403343336 |
| network_dijkstra | [0.1657193759965594, 0.17186622599547263, 0.17008344100031536] | 0.16922301433078246 | 0.16941800433414755 |
| network_patricia | [1.1043780809995951, 1.0932108750057523, 1.0973674159977236] | 1.0983187906676903 | 1.1000322816641226 |
| office_ghostscript | [] | None | None |
| office_ispell | [] | None | None |
| office_rsynth | [1.4266658589986037, 1.4291327519968036, 1.4251736779988278] | 1.4269907629980783 | 1.4154866190001485 |
| office_stringsearch1 | [1.2968022450004355, 1.296781427001406, 1.2943364849998034] | 1.2959733856672149 | 1.3004791696633522 |
| security_blowfish_d | [4.130429775002995, 4.133483751000313, 4.144454023997241] | 4.136122516666849 | 4.14835312866732 |
| security_blowfish_e | [4.26386002000072, 4.210657363997598, 4.2011131909966934] | 4.225210191665004 | 4.205258795668972 |
| security_pgp_d | [] | None | None |
| security_pgp_e | [] | None | None |
| security_rijndael_d | [5.486365349999687, 5.7992879540033755, 5.413616637000814] | 5.566423313667959 | 5.571262340330577 |
| security_rijndael_e | [5.646111796995683, 5.9590683940041345, 5.722609897995426] | 5.775930029665081 | None |
| security_sha | [] | None | None |
| telecom_CRC32 | [1.0163760880022892, 1.0244912600028329, 1.0197685560051468] | 1.020211968003423 | 1.0168178873330664 |
| telecom_adpcm_c | [3.177314266002213, 3.165689018998819, 3.16124700599903] | 3.168083430333354 | 3.1435824000048647 |
| telecom_adpcm_d | [2.2268107879935997, 2.1934103649982717, 2.192814093999914] | 2.2043450823305952 | 2.1998551490008444 |
| telecom_gsm | [2.010426606000692, 2.009330756998679, 2.1552436169949942] | 2.0583336599981217 | 1.890254189335489 |

## Blocked programs

- consumer_lame: baseline/correctness blocked: search baseline output is not repeatable or workload failed; see measurement records; profile functional outputs differ from fixed search reference
- consumer_mad: /home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/consumer_mad/frontend/tu_003_frontend: audio_esd.c:30:11: fatal error: 'esd.h' file not found
   30 | # include <esd.h>
      |           ^~~~~~~
1 error generated.

- office_ghostscript: /home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/office_ghostscript/frontend/tu_000_frontend: In file included from gconfig.c:21:
In file included from ./gx.h:21:
In file included from ./stdio_.h:25:
/usr/include/stdio.h:413:31: error: too many arguments provided to function-like macro invocation
  413 | extern int dprintf (int __fd, const char *__restrict __fmt, ...)
      |                               ^
./std.h:128:9: note: macro 'dprintf' defined here
  128 | #define dprintf(str)\
      |         ^
1 error generated.

- office_ispell: /home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/office_ispell/frontend/tu_000_frontend: bilities (word)
      |      ^
correct.c:812:12: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
  812 | static int insert (word)
      |            ^
correct.c:836:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
  836 | static void wrongcapital (word)
      |             ^
correct.c:855:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
  855 | static void wrongletter (word)
      |             ^
correct.c:890:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
  890 | static void extraletter (word)
      |             ^
correct.c:912:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
  912 | static void missingletter (word)
      |             ^
correct.c:949:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
  949 | static void missingspace (word)
      |             ^
correct.c:1008:5: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1008 | int compoundgood (word, pfxopts)
      |     ^
correct.c:1065:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1065 | static void transposedletter (word)
      |             ^
correct.c:1089:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1089 | static void tryveryhard (word)
      |             ^
correct.c:1096:12: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1096 | static int ins_cap (word, pattern)
      |            ^
correct.c:1114:12: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1114 | static int save_cap (word, pattern, savearea)
      |            ^
correct.c:1154:5: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1154 | int ins_root_cap (word, pattern, prestrip, preadd, sufstrip, sufadd,
      |     ^
correct.c:1182:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1182 | static void save_root_cap (word, pattern, prestrip, preadd, sufstrip, sufadd,
      |             ^
correct.c:1391:15: error: static declaration of 'getline' follows non-static declaration
 1391 | static char * getline (s)
      |               ^
/usr/include/stdio.h:707:18: note: previous declaration is here
  707 | extern __ssize_t getline (char **__restrict __lineptr,
      |                  ^
correct.c:1391:15: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1391 | static char * getline (s)
      |               ^
correct.c:1601:6: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1601 | void copyout (cc, cnt)
      |      ^
correct.c:1616:13: warning: a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]
 1616 | static void lookharder (string)
      |             ^
27 warnings and 5 errors generated.

- security_pgp_d: /home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/security_pgp_d/frontend/tu_000_frontend: cure) [-Wformat-security]
 1043 |                     LANG("WARNING: No ASCII armor `END' line.\n"));
      |                     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1043:7: note: treat the string as an argument to avoid this
 1043 |                     LANG("WARNING: No ASCII armor `END' line.\n"));
      |                     ^
      |                     "%s", 
armor.c:1074:7: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1074 |                     LANG("ERROR: Bad ASCII armor checksum"));
      |                     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1074:7: note: treat the string as an argument to avoid this
 1074 |                     LANG("ERROR: Bad ASCII armor checksum"));
      |                     ^
      |                     "%s", 
armor.c:1083:3: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1083 |                 LANG("Warning: Transport armor lacks a checksum.\n"));
      |                 ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1083:3: note: treat the string as an argument to avoid this
 1083 |                 LANG("Warning: Transport armor lacks a checksum.\n"));
      |                 ^
      |                 "%s", 
armor.c:1173:7: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1173 |                     LANG("ERROR: No ASCII armor `BEGIN' line!\n"));
      |                     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1173:7: note: treat the string as an argument to avoid this
 1173 |                     LANG("ERROR: No ASCII armor `BEGIN' line!\n"));
      |                     ^
      |                     "%s", 
armor.c:1209:1: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1209 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1209:1: note: treat the string as an argument to avoid this
 1209 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^
      | "%s", 
armor.c:1234:23: warning: incompatible pointer types passing 'char[80]' to parameter of type 'char **' [-Wincompatible-pointer-types]
 1234 |             status = getline(buf, sizeof buf, in);
      |                              ^~~
/usr/include/stdio.h:707:45: note: passing argument to parameter '__lineptr' here
  707 | extern __ssize_t getline (char **__restrict __lineptr,
      |                                             ^
armor.c:1234:28: warning: incompatible integer to pointer conversion passing '__size_t' (aka 'unsigned long') to parameter of type 'size_t *' (aka 'unsigned long *') [-Wint-conversion]
 1234 |             status = getline(buf, sizeof buf, in);
      |                                   ^~~~~~~~~~
/usr/include/stdio.h:708:46: note: passing argument to parameter '__n' here
  708 |                           size_t *__restrict __n,
      |                                              ^
armor.c:1237:1: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1237 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1237:1: note: treat the string as an argument to avoid this
 1237 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^
      | "%s", 
armor.c:1269:18: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1269 |         fprintf(pgpout, LANG("ERROR: Hit EOF in header.\n"));
      |                         ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1269:18: note: treat the string as an argument to avoid this
 1269 |         fprintf(pgpout, LANG("ERROR: Hit EOF in header.\n"));
      |                         ^
      |                         "%s", 
12 warnings and 1 error generated.

- security_pgp_e: /home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-preparation-20260921-v1/security_pgp_e/frontend/tu_000_frontend: cure) [-Wformat-security]
 1043 |                     LANG("WARNING: No ASCII armor `END' line.\n"));
      |                     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1043:7: note: treat the string as an argument to avoid this
 1043 |                     LANG("WARNING: No ASCII armor `END' line.\n"));
      |                     ^
      |                     "%s", 
armor.c:1074:7: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1074 |                     LANG("ERROR: Bad ASCII armor checksum"));
      |                     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1074:7: note: treat the string as an argument to avoid this
 1074 |                     LANG("ERROR: Bad ASCII armor checksum"));
      |                     ^
      |                     "%s", 
armor.c:1083:3: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1083 |                 LANG("Warning: Transport armor lacks a checksum.\n"));
      |                 ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1083:3: note: treat the string as an argument to avoid this
 1083 |                 LANG("Warning: Transport armor lacks a checksum.\n"));
      |                 ^
      |                 "%s", 
armor.c:1173:7: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1173 |                     LANG("ERROR: No ASCII armor `BEGIN' line!\n"));
      |                     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1173:7: note: treat the string as an argument to avoid this
 1173 |                     LANG("ERROR: No ASCII armor `BEGIN' line!\n"));
      |                     ^
      |                     "%s", 
armor.c:1209:1: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1209 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1209:1: note: treat the string as an argument to avoid this
 1209 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^
      | "%s", 
armor.c:1234:23: warning: incompatible pointer types passing 'char[80]' to parameter of type 'char **' [-Wincompatible-pointer-types]
 1234 |             status = getline(buf, sizeof buf, in);
      |                              ^~~
/usr/include/stdio.h:707:45: note: passing argument to parameter '__lineptr' here
  707 | extern __ssize_t getline (char **__restrict __lineptr,
      |                                             ^
armor.c:1234:28: warning: incompatible integer to pointer conversion passing '__size_t' (aka 'unsigned long') to parameter of type 'size_t *' (aka 'unsigned long *') [-Wint-conversion]
 1234 |             status = getline(buf, sizeof buf, in);
      |                                   ^~~~~~~~~~
/usr/include/stdio.h:708:46: note: passing argument to parameter '__n' here
  708 |                           size_t *__restrict __n,
      |                                              ^
armor.c:1237:1: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1237 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1237:1: note: treat the string as an argument to avoid this
 1237 | LANG("ERROR: ASCII armor decode input ended unexpectedly!\n"));
      | ^
      | "%s", 
armor.c:1269:18: warning: format string is not a string literal (potentially insecure) [-Wformat-security]
 1269 |         fprintf(pgpout, LANG("ERROR: Hit EOF in header.\n"));
      |                         ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
armor.c:1269:18: note: treat the string as an argument to avoid this
 1269 |         fprintf(pgpout, LANG("ERROR: Hit EOF in header.\n"));
      |                         ^
      |                         "%s", 
12 warnings and 1 error generated.

- security_rijndael_e: baseline/correctness blocked: Clang baseline failed or differs from fixed search reference
- security_sha: baseline/correctness blocked: search baseline output is not repeatable or workload failed; see measurement records; profile functional outputs differ from fixed search reference

Programs with a located profile but invalid baseline/oracle remain blocked; their sampled ranking is retained for audit, while the search-level primary_hotspot stays null. Unavailable builds have no invented samples.

## Commands

```sh
python3 scripts/profile_cbench_frozen.py --manifest configs/cbench_hotspots_dataset1.json --out artifacts/cbench-record-NEW
python3 scripts/analyze_cbench_profiles.py --recordings artifacts/cbench-record-NEW --out artifacts/cbench-analysis-NEW
/tmp/passdistill-test-env/bin/python -m pytest -q tests
```

Prior permission-failure evidence and pre-existing baseline runs remain unchanged. The previous real smoke covered network_dijkstra (1 TU) and automotive_bitcount (10 TUs), same-pipeline rebuilding, instcombine insertion plus identical -force-vector-interleave=1 for all TUs, exact MD5, mean3 and failure paths. Formal 6-Teacher/50-Recovery search remains opt-in.

## Full shared-search smoke after sampling

- network_dijkstra: frozen target `dijkstra_large.c:dijkstra`; 1 valid Teacher fixture, 3 Recovery attempts (2 measured, 1 invalid editor rejection). Teacher mean 0.188233429s. Resume preserved the same target, means and budgets. [Full result](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-frozen-search-smoke-v1/network_dijkstra/smoke.json).
- automotive_bitcount: frozen target `bitcnt_1.c:bit_count`; 1 valid Teacher fixture, 3 Recovery attempts (2 measured, 1 invalid editor rejection). Teacher mean 1.115982214s. Resume preserved the same target, means and budgets. [Full result](/home/liujf/project/passdistill-polybench-minimal/artifacts/cbench-frozen-search-smoke-v1/automotive_bitcount/smoke.json).

98 tests passed, plus 16 subtests. The raw-sample audit verifies unique sample IDs, exact exclusive weight conservation, 0 reported lost samples and selection invariant under sample reordering for all 27 sampled programs. Full rankings, excluded samples, raw perf.data, symbolizer output, Clang AST and DWARF CU lookups are retained.

The original blocked snapshot/report remains under `artifacts/cbench-delivery-20260921-v1`; this report and the current configs point to the new sampled snapshot. Formal 6-Teacher/50-Recovery search was not started.
