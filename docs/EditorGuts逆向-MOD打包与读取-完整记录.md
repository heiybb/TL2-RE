# TL2 EditorGuts.dll 逆向工程总记录 —— MOD 打包/读取 数据结构

> 目标:**离线、无编辑器**地从 `.DAT/.LAYOUT` 源生成与原生 DLL 打包**功能等价、可进游戏生效**的 `.MOD`。
> 本文是 `mikuro_mod_packer/` 包的设计依据,覆盖 **MOD 容器 / BINDAT / BINLAYOUT / RAW / MPP** 五种格式,
> 以及它们**在原生 DLL 里如何被写入、如何被读取/校验**。
>
> **方法**:IDA(idalib MCP)反汇编 `E:\Torchlight 2\EditorGuts.dll`(32 位,imagebase `0x10000000`)+
> 游戏 `Torchlight2.exe`(读取侧)+ `Ogre.log`/`modlauncher.sch` 实地验证 + 对 shipped 数据/native 打包逐字节比对。
> 所有 `sub_XXXXXXXX` 是绝对地址。配套活文档:memory 文件(见文末)、`AGENTS.md`、以及代码内注释(带函数地址/字节布局)。
>
> **重要前提**:`ver`(容器 magic, `word_125EFF4C`)=4;manifest 版本字段(`word_125E3854`)=2;`flags`=0。
> 安装常量 `gamever`(1.25.9.5)= `0x0005000900190001`。

---

## 0. 总览:从源到 .MOD 的五条线

```
                       CreateMod (sub_103FA610: 读 MOD.DAT 元数据)
  .DAT  ──编译──▶ BINDAT  ┐
  .LAYOUT ─编译─▶ BINLAYOUT├─▶  写进 .MOD 容器(header + PAK 数据段 + manifest 文件树)
  扫源生成    ─▶ 7×RAW    ┤        ▲ 编译产物"骑"在源名下(FOO.DAT 不是 FOO.DAT.BINDAT)
  关卡 raycast ─▶ .MPP    ┘        │   但用编译形的 type code
                                  └─ PAK 数据段逐 block: [u32 解压尺寸][u32 压缩尺寸][zlib]
```

- **编译产物存源名、编译类型**:`FOO.DAT`(type 0=BINDAT)条目里装的是编译后的 BINDAT 字节;`FOO.LAYOUT`(type 1)装 BINLAYOUT。GUTS 把 `.DAT.BINDAT`/`.LAYOUT.BINLAYOUT` 落盘但**不单独进 manifest**。
- 游戏加载侧:`Torchlight2.exe` 把 `.MOD` 当 PAK 归档挂载 `MEDIA/` 子树(`Ogre.log` 可见 `Added resource location 'MEDIA/UI/' of type 'PAK'`),按路径查文件。

---

## 1. `.MOD` 容器格式

### 1.1 总体三段
```
out = _w_header(h, off_data, off_man)        # mod-info 头(可变长,取决于字符串)
    + data                                   # PAK 数据段 [off_data, off_man)
    + _w_manifest(h, dirs)                    # TOC 文件树(从 off_man 起)
```
`off_data` = header 长度;`off_man` = `off_data + len(data)`。

### 1.2 Header(mod-info)
写入器 `sub_103F5DA0`,读取器 `sub_103FA610`。布局:
```
<HHQII> ver, modver, gamever, off_data, off_man
SS title; SS author; SS descr; SS website; SS download      # SS=ShortString: u16 字符数 + UTF-16LE
<QIQ>   modid, flags, reqHash
<H> reqs_count;  per: SS(name) <QH> mod_id, version
<H> dels_count;  per: SS(path)
```
- **字段→槽位**(RE 自 `sub_103FA610`/`sub_103F5DA0`):`NAME`→title(+40)、`AUTHOR`→+68、`DESCRIPTION`→+152、`WEBSITE`→+96、`DOWNLOAD_URL`→+124、`MOD_ID`→modid(+240)、`VERSION`→modver(+256)、`REQUIRED_MODS`→reqs、`REMOVE_FILES`→dels。`MOD_FILE_NAME` 是**输出文件名**,不是 header 槽。
- **modver = VERSION + 1**:publish 路径执行 `++*(this+256)`。
- **reqHash** = REQUIRED_MODS 的递归哈希(`sub_103F5500`);无依赖时 = 0(常见且可离线复现的唯一情形)。
- **gamever** = `read_gamever()` 实读 `Torchlight2.exe` 的 VS_FIXEDFILEINFO(`sub_103F8CD0`,取词序 (minorMS,majorMS,privLS,buildLS))。每安装常量。

### 1.3 Manifest(TOC 文件树)
写入器 `sub_102A5860`。布局:
```
<HI> 版本(=word_125E3854=2), mhash    # ← mhash 是 "hashValue" 字段
SS root("MEDIA/")
<II> file_count(fc), dir_count
per dir: SS(dirname) <I> rec_count
         per rec: <IB> crc32, type   SS(name)   <IIQ> off, size, filetime
```
- **目录树**:文件按父目录 key 进 `std::map<wstring,…>` → 目录按 **UTF-16 路径排序**输出;每个目录给子目录一个 **type-7 占位**。`DIR[0]=('', [type-7 'MEDIA/'])`,根 = `MEDIA/`。
- **rec 的 `off`** 是**相对数据段起点**(`off_data + off` 才是文件内绝对位置)。
- **`filetime`** = 源文件 mtime 转 Windows FILETIME。游戏不校验,纯元数据。
- ⚠️ **文件名必须全大写**(见 1.6)。

### 1.4 PAK 数据段
写入器 `sub_102A7100`。布局:
```
<II> maxCompressedBlockSize, rollingHash      # 8 字节头(rollingHash 见 1.5)
per file(manifest 序): <II> 解压尺寸, 压缩尺寸(0=stored) + 字节流
```
- **maxCompressedBlockSize** = 最大压缩 block 尺寸,喂游戏解压读缓冲。
- **存储 vs 压缩** = `byte_11E94CD8[type]`(pak writer `sub_102A7100`:`if (byte_11E94CD8[type] && size < 0x1900000)` 才压)。表对 type 0..23 都是 1,**只有 type 24(.JPG)是 0**。即:**除 .JPG(stored)外全 zlib-L6**;另外任何 block ≥ `0x1900000`(26MB)也 stored。
  > 注:我们离线打包改用 **isal**(`isal_zlib`,SIMD DEFLATE,仍 zlib 格式,游戏照常解压,crc32 同标准值;缺失回退 zlib),非 byte-exact 但功能等价 + 快 ~3-5x。

### 1.5 三个 hash/count 字段(★ 最关键,曾全部判断错过)

| 字段 | 位置 | 游戏是否校验 | 我们的处理 |
|---|---|---|---|
| **PAK rollingHash** | 数据段头第 2 个 u32 | **是,会校验** | **必须算对**(`_pak_rolling_hash`) |
| manifest mhash("hashValue") | manifest 头 | 否(读而不校) | 0 即可 |
| manifest fc(FileCount) | manifest 头 | 否(容量提示) | 写字面记录数 |

**rollingHash —— 这是"勾选了进游戏无效果"的真凶。** 加载器(见 1.9)会**重算并比对**;写 0 → 静默 `"Unable to load mod."` → 整个 mod 文件表被丢弃 → 无内容。
- 写入(`sub_102A7100` 末尾)/ 校验(`sub_102A2690`)算法**对称且确定**:
  - 采样步长 `stride = N / rng(25,75)`,其中 `N` = 数据段长度;
  - **关键**:`rng` 这个 LCG(`sub_10285B30`:`state = state_hi + 695696193*state_lo`)在调用前被 `sub_10285A50` **用 N 作种子**(`sub_10285450` 存旧状态、算完恢复)→ 所以"随机"除数其实是 **N 的确定函数**:
    ```
    divisor = 25 + (695696193 * N  mod 2^32) mod 51
    stride  = max(2, N // divisor)
    h = N;   对 offset 8、8+stride、… < N 的字节:  h = (int8)byte + 33*h  (mod 2^32)
    h = (int8)data[N-1] + 33*h        # 再叠加最后一字节(offset 0..7 的头不参与)
    rollingHash = h
    ```
  - 已对 30 个 shipped/editor-published `.MOD` **逐字节吻合**。
- **mhash** 由 `sub_10286420(15,25)` 派生(debug 串 `"Rand Integer Between Seed VOLATILE"`),`sub_102A3320` 读入但**从不比对** → 真随机、可留 0。
- **fc**:native 自己的 fc(如 862)≠ 它的实际记录数(~618)却照常加载 → 游戏走 DirCount + 各目录计数迭代,**不用 fc 界定**。

### 1.6 文件名大小写(★ 第二个 in-game bug)
**GUTS 把 manifest 里每个文件名转大写**(`sub_103F50D0` 收集时);游戏的 PAK 查找把请求路径转大写,然后跟存储名**按原样**比对(假定已大写)。
- 后果:磁盘上小写的 `QLJX_F.dds` 若存原始小写,游戏用 `QLJX_F.DDS` 查 → 匹配不到 → 该资源静默失败。具体表现:`UNITS/PLAYERS/.../CLASS_QLJX_F.DAT` 里 `<STRING>ICON:QLJX_F_NORMAL` →(imageset)→ `QLJX_F.dds` 找不到 → **职业头像显示别的图**(职业本身/名字正常,因为它们不走大小写敏感的纹理查找)。
- 修复:`_collect_media_files` 存大写名(`str.upper()`:ASCII 转大写,CJK 不变,与 GUTS 一致)。

### 1.7 类型码(`sub_102A1EA0` + 编译重映射 `sub_102A24F0`)
按 UPPER 扩展名(含点):`.DAT/.TEMPLATE`→0、`.LAYOUT`→1、`.MESH`→2、`.SKELETON`→3、`.DDS`→4、`.PNG`→5、`.WAV/.OGG`→6、目录→7、`.MATERIAL`→8、`.RAW`→9、`.UILAYOUT`→10、`.IMAGESET`→11、`.TTF/.TTC`→12、`.FONT`→13、`.ANIMATION`→16、`.HIE`→17、未知→18、`.SCHEME`→19、`.LOOKNFEEL`→20、`.MPP`→21、`.BIK`→23、`.JPG`→24。**编译产物存源名但取编译形的 type**(`.DAT.BINDAT`→看 `.DAT`→0)。

### 1.8 写入路径(CreateMod)
`CreateMod`(导出 `0x100DE830`)= 读 MOD.DAT 元数据(`sub_103FA610`)+ `Pathing_RegenAll_worker`(MPP,见 §6)+ `.MOD` pack(header `sub_103F5DA0` / manifest `sub_102A5860` / PAK `sub_102A7100`)。PAK 先写到 `PAKS/TMP.tmp` 再 rename。

### 1.9 读取/校验路径(游戏加载器)
链路:`sub_103FB240`(报 `"Unable to load mod.\nFailed because :"`)→ `sub_103F8BC0`(报 `"Unable to load mod: <name>"`,成功返回 1)→ **`sub_103F83C0`(真正的加载/校验)**:
1. `if (*(this+312)) return 1;`(已加载);`if (!*(this+200) || !*(this+276)) return 0;`(文件表/offMan 为空 → 静默失败)。
2. 顶部循环:解析 REQUIRED_MODS 依赖(`sub_103F8FF0` 查找 + 递归 `sub_103F83C0`),缺失/版本不对会记 `"Unable to activate mod : … with guid:"` / `"… is not installed"`。
3. 重开文件,`sub_103F7E60` 检查 required-mods 版本(无依赖时空过)。
4. **reqHash 比对**:`sub_103F5500(this,0)` 重算 ?= 存储 reqHash(无依赖时 0==0)。
5. **`sub_102A3320`**:读 manifest 版本(`> word_125E3854(=2)` 则拒)、读 hashValue(不校)、然后 **`sub_102A2690` 重算并比对 rollingHash** —— **这一步是 rollingHash 的校验点**,不等就 `goto LABEL_27`(`fclose; return 0`,静默)。

> 即:容器结构、文件清单、所有内容字节都对,但只要 rollingHash 不对就整体静默拒绝。这就是"launcher 能勾、进游戏无效果"的机理。

### 1.10 激活机制(MODGUID)
`<存档>/modlauncher.sch`:`[MODS] <INTEGER64>MODGUID:<modid> [/MODS]`。游戏加载 header modid 匹配的 `.MOD`。即勾选按 **MOD_ID** 激活,与文件名/hash 无关。

---

## 2. BINDAT(`.DAT` → 二进制)

序列化链 `sub_10289A40`(+ 字符串收集 `sub_10289950`、interner `sub_1023E9F0`、节点写 `sub_10289860`);`sub_1028ED40` = WriteShortString。

### 2.1 格式
```
Header 12B: <III> version(=2), string_count, first_id
String table(按 id 升序,GUTS 迭代 std::map):
   entry0 = <H>len + wchar[]           # 第 0 个无 id 前缀(id 在 header 的 first_id)
   entryN = <I>id <H>len + wchar[]
Body = 一个递归节点:
   <II> name_hash(节点名 rg_hash), prop_count
   per prop: <II> key_hash(rg_hash), type   + value(type∈{3,7} 为 8B,否则 4B)
   <I> child_count   + 子节点...           # 源顺序
```
- 类型:`INTEGER`→1、`FLOAT`→2、`UNSIGNED INT`→4、`STRING`→5、`BOOL`→6、`INTEGER64`→7、`TRANSLATE`→8。键名用 **rg_hash**(§7,大写)。
- **STRING/TRANSLATE 的值存字符串表 id**;空串用 `0xFFFFFFFF` 哨兵内联(不进表)。
- 编码用 **surrogatepass**:编辑器逐 wchar 原样读写、不校验 UTF-16 代理对;`TAGS.DAT` 里有把浮点色块拼进 `<STRING>:` 值的脏数据(重解释成孤代理),必须 surrogatepass 才能字节往返。

### 2.2 字符串 id 解析模型 —— ★ 逐文件(model A,已证)
- **shipped 格式**里 id 是**全局会话计数器**(`sub_1023E9F0`,`counter++`)。
- **但游戏是逐文件解析的**(model A):每个 BINDAT 自带表,body 的 id 用**本文件的表**解析。
  - **铁证**:shipped base game 自带 **565 处跨文件 id 撞号**(同一 id 在不同文件指不同串,如 id 1398 = `'SET STAT ON LEVEL'` vs 别的串)而游戏照常加载运行 → 若全局合并表早崩了。
  - 表**按 id 排序** → 游戏对每个文件的表做二分查找 → 任意(含稀疏)id 都能解析。
- **推论**:id 的具体值无所谓,只要**文件内唯一**。所以我们离线打包**弃用 corpus 字典,改 per-file hash**(`HashStringDict`:`rg_hash(s)` + 文件内线性探测保唯一)→ 无共享状态、天然并行、确定性;已**进游戏验证**(职业/技能/图标全对)。
  - 离线另保留 corpus 字典(扫全部 shipped BINDAT 重建 id↔串,`data/bindat_string_dict.pkl`)仅供"compiler byte-exact 测试"。

---

## 3. BINLAYOUT(`.LAYOUT` → 二进制)

schema 驱动的逐 descriptor 编码器(`data/binlayout_schema.json`);写入链 `sub_101169B0→sub_10116780→sub_10116650→sub_10116420→sub_10115320`,datagroup `sub_101150F0`。

### 3.1 格式
```
Header: <B>0x0B <B>flag(=4) <I>dg_off <H>obj_count(顶层)
Object(递归):
   <I> block_size  <B> descriptor  <q> id
   str NAME(仅当 != descriptor 默认名时写)
   <B> prop_count   per prop: <H>mem <B>code + value
   <I> adprop_region   <H> child_count   + 子对象...
   per prop = <H> mem; <B> code; value
```
### 3.2 Logic Group 逻辑图(在 ADPROP 区)
`<B>count` + 每个逻辑对象 `{<B>ID <q>OBJECTID <f>X <f>Y <I>end_offset <B>link_count}` + links `{<B>LINKINGTO str OUTPUTNAME str INPUTNAME}`(名字内联,非解析 id)。

### 3.3 Datagroup(= `CLayoutBinaryGroup` 树,镜像每个 `Group` 对象 desc=1,合成根 id=-1)
节点:`<q>id <B>CHOICE@16 <I>RANDOMIZATION@20 <B>NUMBER@24 <I>@28 <I>TAG@92 <B>@25(NO TAG FOUND)/@26(LEVEL UNIQUE)/@27(GAME MODE) <I>+<q>[]ACTIVE THEMES <I>+<q>[]DEACTIVE THEMES <H>child_count`。`@28` = 该 Group 对象块的流偏移;`TAG@92` = 运行时 tag 注册 id(`sub_10253630`,离线学进 `data/binlayout_datagroup_tags.json`)。

---

## 4. RAW 索引文件(7 个)

写入分派器 `sub_1029BFA0`;`SS`=ShortString。各文件**索引一类源 .DAT/.LAYOUT**;扫描序见各项。

| RAW | 写入器 | 结构 |
|---|---|---|
| **AFFIXES** | `sub_103C4170` | `<H>count`;per: SS(FILE) SS(NAME↑) `<IIII>`MIN_SPAWN(0)/MAX_SPAWN(999999)/WEIGHT(1)/DIFF(-1) `<B>`n + SS×(UNITTYPES) `<B>`n + SS×(NOT_UNITTYPES) |
| **SKILLS** | `sub_102ECFD0` | `<I>`count(仅含非空 NAME 的);per: SS(NAME↑) SS(FILE) `<q>`UNIQUE_GUID(-1) |
| **MISSILES** | `sub_102FB490` | `<H>`count;per: SS(FILE=.LAYOUT) `<B>`n + SS×(每个 DESCRIPTOR:Missile 对象的 MISSILE NAME↑) |
| **TRIGGERABLES** | — | `<H>`count;per: SS(FILE) SS(NAME) |
| **UI** | `sub_103178E0` | `<I>`count(仅含 Menu Definition 且 MENU NAME 非空、非 DO NOT CREATE 的);per: SS(MENU NAME) SS(FILE) `<II>`TYPE/GAME STATE 枚举 idx `<BBB>`(ALWAYS VISIBLE‖CREATE ON LOAD)/MP only/SP only SS(KEY BINDING) |
| **UNITDATA** | `sub_1026CC50` / reader `sub_1026F2B0` | 4 类(ITEMS/MONSTERS/PLAYERS/PROPS)各:`<I>`count;per: `<q>`UNIT_GUID SS(NAME↑) SS(FILE) `<B>`flags(bit0=CREATEAS==EQUIPMENT,bit1=SET) `<iiiii>`LEVEL/MIN/MAX/RARITY/RARITY_HC SS(UNITTYPE↑)。**字段走完整 BASEFILE 继承链**(子→父,取首个 != 默认者);DONTCREATE 的抽象基跳过 |
| **ROOMPIECES** | — | `<I>`count;per SS(FILE);然后 per `<I>`GUIDs + `<q>`GUID× |

- **扫描序**:AFFIXES/SKILLS/UNITDATA/MISSILES = **name-interleaved DFS**(文件与子目录按名混排,就地递归);TRIGGERABLES/UI/ROOMPIECES = files-before-dirs。`_media_path`:`MEDIA/` + 相对路径,**大写**(非 ASCII 保留)。
- **GUID 类型坑**:`.DAT` 里是 `<INTEGER64>GUID:`,`.LAYOUT` 里是 `<STRING>GUID:`,同值不同类型。
- 字节验证:AFFIXES/SKILLS/MISSILES/UI/UNITDATA 均逐字节复现 shipped RAW。

---

## 5. MPP 寻路文件(`.mpp`)

### 5.1 格式
每个 `.layout` 旁一个同名 `.mpp`:
```
24B header: <iiffff> gw, gh, worldW, worldD, originW, originD
然后 gw*gh 字节:每 cell 1 字节可行走性(0/1/255)
```
- cell = **0.4 单位**;区域 snap = `floor((min-0.2)/10)*10 / ceil((max+0.2)/10)*10`。
- **PATH NODE OCCUPATION 是运行时的**,不烘进 .mpp(只 3 个字节值 0/1/255)。

### 5.2 生成/写入路径(`EditorRegenPathingData`)
导出 `0x100DDDE0` → `Pathing_RegenAll_worker`(`sub_10018750`):扫 `*.layout` → **单线程** do/while 逐文件 `Pathing_RegenSingleFile_worker`(`sub_10015FA0`),每 20 文件做一次 Ogre 资源 unload 清扫。每文件:`CLevel_ctor`(`sub_101FD170`,1160B 对象)→ 置标志 → `CLevel_SetMppOutputPath`(`sub_1000B980`)→ **`CLevel_LoadLevelData`(`sub_1020AB90`,解析 layout + 经 Ogre 加载全部碰撞 mesh + 组装碰撞世界)** → raycast 每 cell → 写 .mpp → 析构。耗时大头是 **Ogre mesh 加载 + CLevel 生命周期**,非 raycast。

### 5.3 离线 / 无头生成
- 离线 numba 后端(`mpp/native_nb.py`):`@njit(fastmath=False)` 镜像标量核,IEEE754 逐位一致;~99.7% cell 与 native 一致(剩余是 cliff/overhang 浮点 tie-break + nocollide 洞穴墙,不可复现)。
- **无头 byte-exact**:驱动真实 DLL(`TL2-Mikuro-Console.exe` fork)`InitEditor` + `EditorSetWorkingMod` + `CreateMod`(双 pass:pass1 写 .BINLAYOUT + stub .mpp,pass2 写真 .mpp)。InitEditor 一次 ~6.24s(Ogre/PAK/room-piece 数据 ~3s + FMOD+D3D9 device ~2s + shader)。

---

## 6. 编辑器生命周期

- **InitEditor**(`0x10001DD0`):薄壳 → `sub_10017120`(848B 编辑器对象构造,内含 D3D9/FMOD/Ogre)+ `sub_10019A00`。MPP 的 raycast 是**纯 CPU 几何不需 GPU**,但 `CLevel_LoadLevelData` 经 Ogre 资源管理器加载 mesh(默认走 RenderSystem 建 hardware buffer)→ **D3D9 device 是 mesh 加载的承重墙**,不能简单跳过;FMOD 可跳。
- **CreateMod**(`0x100DE830`)= 元数据 + MPP + .MOD pack;只接受 `<install>/mods/` 下的工程。
- **崩溃归因**:游戏/编辑器在渲染 tick 的 AccessViolation = RTX 3070 + 旧 D3D9 驱动 bug(关 Threaded Optimization / 限 FPS / DXVK),**不是打包管线**。

---

## 7. rg_hash(GUTS 32 位字符串哈希)

用于 BINDAT 的 **节点名/键名**(以及我们 per-file BINDAT 的字符串 id)。实现见 `mikuro_mod_packer/rghash.py`(已破解、对已知 (串→hash) 对验证)。注意 BINDAT 的**字符串值**不用 hash —— 用 id 表;rg_hash 只哈希 key/name。

---

## 8. 跨切面要点 & 已被纠正的旧结论

- ✅ **离线打包 == native 功能等价**(MIKURO_CLASS_QLJX_EN 逐字段证):文件清单、BINDAT 语义、mesh/贴图/骨骼/材质、RAW 集合、header 全一致;差异只有(已证无害的)随机 mhash/rollingHash 值、benign 的 SKILLS.RAW 顺序、benign 的 BINDAT id 编号、以及一个**源文件本身写错**的 LAYOUT(`CHILDREN]` 少了 `[`)。
- ❌ **已纠正**:早期判断"rollingHash 是随机、游戏忽略"是**错的** —— 它会校验(stride RNG 用 N 作种子→确定),必须算对。
- ❌ **已纠正**:早期没注意 **manifest 文件名要大写**,导致小写 `.dds` 等资源查不到。
- **manifest 记录顺序**与 native 不同(native = 编辑器打包时的 NTFS FindFirstFile 原始序),但**无害**(游戏走路径查找,不依赖顺序)。

---

## 附录 A:关键函数地址表(EditorGuts.dll, imagebase 0x10000000)

| 功能 | 地址 |
|---|---|
| InitEditor / CreateMod / EditorSetWorkingMod / EditorRegenPathingData | `0x10001DD0` / `0x100DE830` / `0x100E3B50` / `0x100DDDE0` |
| MOD header 写 / 读 | `sub_103F5DA0` / `sub_103FA610` |
| Manifest 写 | `sub_102A5860` |
| PAK 数据段写(+rollingHash 计算) | `sub_102A7100` |
| 类型码分类 / 编译重映射 / 存储表 | `sub_102A1EA0` / `sub_102A24F0` / `byte_11E94CD8` |
| 加载报错 / "Unable to load mod" / **加载校验** | `sub_103FB240` / `sub_103F8BC0` / `sub_103F83C0` |
| required-mods 检查 / reqHash / gamever 读取 | `sub_103F7E60` / `sub_103F5500` / `sub_103F8CD0` |
| manifest+PAK 校验 / **rollingHash 校验** | `sub_102A3320` / `sub_102A2690` |
| rollingHash 的种子 RNG:"rand between" / LCG / 设种子 / 存状态 | `sub_10286420` / `sub_10285B30` / `sub_10285A50` / `sub_10285450` |
| BINDAT:序列化 / 串收集 / interner / 节点写 / WriteShortString | `sub_10289A40` / `sub_10289950` / `sub_1023E9F0` / `sub_10289860` / `sub_1028ED40` |
| BINLAYOUT:写入链 / datagroup / tag 注册 | `sub_101169B0…sub_10115320` / `sub_101150F0` / `sub_10253630` |
| RAW:分派 / AFFIXES / SKILLS / MISSILES / UI / UNITDATA(写/读) | `sub_1029BFA0` / `sub_103C4170` / `sub_102ECFD0` / `sub_102FB490` / `sub_103178E0` / `sub_1026CC50`·`sub_1026F2B0` |
| MPP:RegenAll / RegenSingleFile / CLevel ctor·LoadLevelData·SetMppOutputPath | `sub_10018750` / `sub_10015FA0` / `sub_101FD170`·`sub_1020AB90`·`sub_1000B980` |

## 附录 B:配套资源索引

- **代码**:`mikuro_mod_packer/`(`packer.py` 容器+编排、`bindat.py`、`binlayout.py`、`raw.py`、`rghash.py`、`mpp/`);CLI `python -m mikuro_mod_packer`。
- **Memory**:`mod-container-hash-count-fields-and-activation`(rollingHash/mhash/fc/激活)、`mod-manifest-uppercase-filenames`(大小写)、`bindat-binlayout-template-echo`(BIN*/RAW/容器 + per-file hash)、`mpp-*`(.mpp 格式 / 无头重生 / 语料精度等)。
- **工具**:`tools/mod_disasm.py`(.MOD 反汇编)、`cmp_mod.py`/`cmp_bindat.py`(native-vs-ours 对比)、`verify_container_writer.py`(容器写入 byte-exact)、`bench_all_mods.py`/`bench_native.py`(基准)、`tools/tl2_console_fork/`(无头驱动 fork)。
- **性能**:见 `开发日志/性能优化记录.md` #6(全量打包 185.5→83s)。
