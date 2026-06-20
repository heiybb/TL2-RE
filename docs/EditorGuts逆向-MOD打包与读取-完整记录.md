# TL2 EditorGuts.dll 逆向工程总记录 —— MOD 打包/读取 数据结构

> 一句话目标:**不开编辑器**,纯离线从 `.DAT/.LAYOUT` 源直接生成一个能进游戏、能生效、跟原生 DLL 打出来**功能等价**的 `.MOD`。
>
> 这篇是 `mikuro_mod_packer/` 这个包的"设计底稿"。我把 TL2 打包用到的五种格式 —— **MOD 容器 / BINDAT / BINLAYOUT / RAW / MPP** —— 连同它们**在原生 DLL 里到底是怎么被写出来、又是怎么被读回去和校验的**,全部摊开记在这里。
>
> 怎么挖出来的:IDA(idalib MCP)硬反汇编 `E:\Torchlight 2\EditorGuts.dll`(32 位,imagebase `0x10000000`),读取侧再去啃游戏本体 `Torchlight2.exe`;然后拿 `Ogre.log` / `modlauncher.sch` 实地对照,把 shipped 数据和原生打包结果**逐字节**比。下文所有 `sub_XXXXXXXX` 都是绝对地址。配套的活文档还有代码里的注释(都带着函数地址和字节布局)。
>
> 几个贯穿全文的前提常量先放这:`ver`(容器 magic,`word_125EFF4C`)= 4;manifest 版本字段(`word_125E3854`)= 2;`flags` = 0;安装常量 `gamever`(1.25.9.5)= `0x0005000900190001`。

---

## 0. 总览:从源到 .MOD 的五条线

先给个全景,免得后面钻进细节里迷路。从源文件到最终那个 `.MOD`,一共五条线汇到一起:

```
                       CreateMod (sub_103FA610: 读 MOD.DAT 元数据)
  .DAT  ──编译──▶ BINDAT  ┐
  .LAYOUT ─编译─▶ BINLAYOUT├─▶  写进 .MOD 容器(header + PAK 数据段 + manifest 文件树)
  扫源生成    ─▶ 7×RAW    ┤        ▲ 编译产物"骑"在源名下(FOO.DAT 不是 FOO.DAT.BINDAT)
  关卡 raycast ─▶ .MPP    ┘        │   但用编译形的 type code
                                  └─ PAK 数据段逐 block: [u32 解压尺寸][u32 压缩尺寸][zlib]
```

这里有个一开始很容易看走眼的细节:**编译产物存的是源文件名,用的却是编译形的类型码**。`FOO.DAT`(type 0 = BINDAT)这条记录里装的是编译后的 BINDAT 字节;`FOO.LAYOUT`(type 1)装的是 BINLAYOUT。GUTS 确实会把 `.DAT.BINDAT` / `.LAYOUT.BINLAYOUT` 落到盘上,但它们**不会单独进 manifest**——进 manifest 的永远是那个源名条目。

游戏这边更直白:`Torchlight2.exe` 把 `.MOD` 当成一个 PAK 归档挂上去,接管 `MEDIA/` 子树(`Ogre.log` 里能看到 `Added resource location 'MEDIA/UI/' of type 'PAK'`),之后一律按路径查文件。

---

## 1. `.MOD` 容器格式

### 1.1 总体三段

整个文件就三段,拼接而成:
```
out = _w_header(h, off_data, off_man)        # mod-info 头(可变长,取决于字符串)
    + data                                   # PAK 数据段 [off_data, off_man)
    + _w_manifest(h, dirs)                    # TOC 文件树(从 off_man 起)
```
`off_data` = header 长度;`off_man` = `off_data + len(data)`。结构本身不复杂,真正麻烦的是后面几个 hash 字段。

### 1.2 Header(mod-info)

写入器 `sub_103F5DA0`,读取器 `sub_103FA610`。布局:
```
<HHQII> ver, modver, gamever, off_data, off_man
SS title; SS author; SS descr; SS website; SS download      # SS=ShortString: u16 字符数 + UTF-16LE
<QIQ>   modid, flags, reqHash
<H> reqs_count;  per: SS(name) <QH> mod_id, version
<H> dels_count;  per: SS(path)
```
MOD.DAT 里那些字段最后落到哪个槽位,是我对着 `sub_103FA610` / `sub_103F5DA0` 一个个抠出来的:`NAME`→title(+40)、`AUTHOR`→+68、`DESCRIPTION`→+152、`WEBSITE`→+96、`DOWNLOAD_URL`→+124、`MOD_ID`→modid(+240)、`VERSION`→modver(+256)、`REQUIRED_MODS`→reqs、`REMOVE_FILES`→dels。注意 `MOD_FILE_NAME` 是**输出文件名**,根本不是 header 里的槽。

几个容易写错的点:
- **modver = VERSION + 1**:publish 路径里会执行一句 `++*(this+256)`,所以盘上看到的版本号比你 MOD.DAT 写的大 1。
- **reqHash** 是 REQUIRED_MODS 的递归哈希(`sub_103F5500`);没有依赖时就是 0 —— 这也是唯一能离线干净复现的情形,有依赖的我们暂时不碰。
- **gamever** 不是写死的,是 `read_gamever()` 真的去读 `Torchlight2.exe` 的 VS_FIXEDFILEINFO(`sub_103F8CD0`,取词序 (minorMS, majorMS, privLS, buildLS))。每个安装一个常量。

### 1.3 Manifest(TOC 文件树)

写入器 `sub_102A5860`。布局:
```
<HI> 版本(=word_125E3854=2), mhash    # ← mhash 是 "hashValue" 字段
SS root("MEDIA/")
<II> file_count(fc), dir_count
per dir: SS(dirname) <I> rec_count
         per rec: <IB> crc32, type   SS(name)   <IIQ> off, size, filetime
```
- **目录树是排序出来的**:文件按父目录 key 塞进 `std::map<wstring,…>`,于是目录就按 **UTF-16 路径排序**输出;每个目录还会给它的子目录留一个 **type-7 占位**。`DIR[0]=('', [type-7 'MEDIA/'])`,根是 `MEDIA/`。
- **rec 里的 `off`** 是**相对数据段起点**的——加上 `off_data` 才是文件在 `.MOD` 里的绝对位置,算偏移时容易漏掉这一步。
- **`filetime`** 是源文件 mtime 转成的 Windows FILETIME。游戏压根不看,纯元数据。
- ⚠️ **文件名必须全大写**——这点很关键,单独拿一节讲(见 1.6)。

### 1.4 PAK 数据段

写入器 `sub_102A7100`。布局:
```
<II> maxCompressedBlockSize, rollingHash      # 8 字节头(rollingHash 见 1.5)
per file(manifest 序): <II> 解压尺寸, 压缩尺寸(0=stored) + 字节流
```
- **maxCompressedBlockSize** 是最大那块压缩后的尺寸,喂给游戏开解压读缓冲用。
- **存还是压**由 `byte_11E94CD8[type]` 决定(pak writer `sub_102A7100` 里:`if (byte_11E94CD8[type] && size < 0x1900000)` 才压)。这张表对 type 0..23 全是 1,**只有 type 24(.JPG)是 0**。换句话说:**除了 .JPG 直接 stored,其余一律 zlib-L6**;另外任何 block 只要 ≥ `0x1900000`(26MB)也一律 stored。
  > 我们离线打包这里换了个实现:改用 **isal**(`isal_zlib`,SIMD DEFLATE,输出仍是 zlib 格式,游戏照常解压,crc32 也跟标准值一致;装不上就回退到普通 zlib)。不是 byte-exact,但功能完全等价,而且快 ~3-5x。

### 1.5 三个 hash/count 字段(★ 最关键,这三个我一开始都判断错了)

| 字段 | 位置 | 游戏是否校验 | 我们的处理 |
|---|---|---|---|
| **PAK rollingHash** | 数据段头第 2 个 u32 | **是,会校验** | **必须算对**(`_pak_rolling_hash`) |
| manifest mhash("hashValue") | manifest 头 | 否(读而不校) | 0 即可 |
| manifest fc(FileCount) | manifest 头 | 否(容量提示) | 写字面记录数 |

**rollingHash —— 这就是"launcher 勾上了、进游戏却毫无动静"的根源。** 加载器(见 1.9)会**自己重算一遍再跟你写的比**;你写 0,它就静默报一句 `"Unable to load mod."`,然后把整个 mod 的文件表丢掉——结果是一点内容都没有,也没有任何报错。这个 bug 我们查了很久。

把算法挖清楚之后才发现它写(`sub_102A7100` 末尾)和校(`sub_102A2690`)两边**对称且完全确定**:
- 采样步长 `stride = N / rng(25,75)`,`N` 是数据段长度;
- **关键的关键**:`rng` 这个 LCG(`sub_10285B30`:`state = state_hi + 695696193*state_lo`)在被调之前,先被 `sub_10285A50` **拿 N 当种子**喂了一道(`sub_10285450` 负责存旧状态、算完再恢复)。所以那个看着"随机"的除数,其实是 **N 的一个确定函数**:
    ```
    divisor = 25 + (695696193 * N  mod 2^32) mod 51
    stride  = max(2, N // divisor)
    h = N;   对 offset 8、8+stride、… < N 的字节:  h = (int8)byte + 33*h  (mod 2^32)
    h = (int8)data[N-1] + 33*h        # 再叠加最后一字节(offset 0..7 的头不参与)
    rollingHash = h
    ```
  - 写完拿 30 个 shipped / 编辑器 publish 出来的 `.MOD` 一验,**逐字节全中**,至此确认就是它。
- **mhash** 是 `sub_10286420(15,25)` 派生的(debug 串泄了底:`"Rand Integer Between Seed VOLATILE"`),`sub_102A3320` 会读它,但**从头到尾不比对** → 它本来就是真随机,我们留 0 就行。
- **fc**:原生自己写的 fc(比如 862)跟它的实际记录数(~618)根本对不上,游戏却照常加载 → 说明游戏走的是 DirCount 加各目录计数挨个迭代,**根本没拿 fc 来界定边界**。

### 1.6 文件名大小写(★ 第二个 in-game bug)

**GUTS 在收集时会把 manifest 里每个文件名转成大写**(`sub_103F50D0`);游戏那边查 PAK 时,把请求路径也转大写,然后跟存储名**照原样**比(它默认你已经是大写了)。

两边一旦大小写不对齐,就静默失败。我们当时的现场是这样:磁盘上是小写的 `QLJX_F.dds`,我们原样存了小写;游戏拿 `QLJX_F.DDS` 去查 → 匹配不上 → 这个贴图静默丢失。表现出来很迷惑:`UNITS/PLAYERS/.../CLASS_QLJX_F.DAT` 里写着 `<STRING>ICON:QLJX_F_NORMAL` →(imageset)→ 指向 `QLJX_F.dds`,找不到,于是**职业头像显示成了别的图**;偏偏职业本身、名字都正常(因为那些不走大小写敏感的纹理查找),更让人摸不着头脑。

修法很简单:`_collect_media_files` 里存大写名(`str.upper()`:ASCII 转大写、CJK 原样不动,跟 GUTS 行为一致)。

### 1.7 类型码(`sub_102A1EA0` + 编译重映射 `sub_102A24F0`)

按大写扩展名(连点一起):`.DAT/.TEMPLATE`→0、`.LAYOUT`→1、`.MESH`→2、`.SKELETON`→3、`.DDS`→4、`.PNG`→5、`.WAV/.OGG`→6、目录→7、`.MATERIAL`→8、`.RAW`→9、`.UILAYOUT`→10、`.IMAGESET`→11、`.TTF/.TTC`→12、`.FONT`→13、`.ANIMATION`→16、`.HIE`→17、未知→18、`.SCHEME`→19、`.LOOKNFEEL`→20、`.MPP`→21、`.BIK`→23、`.JPG`→24。再强调一遍前面那个坑:**编译产物存源名,但 type 取编译形**(`.DAT.BINDAT` 这条,看的是 `.DAT`,所以 type 0)。

### 1.8 写入路径(CreateMod)

`CreateMod`(导出 `0x100DE830`)干三件事:读 MOD.DAT 元数据(`sub_103FA610`)+ `Pathing_RegenAll_worker`(算 MPP,见 §6)+ 把 `.MOD` 打出来(header `sub_103F5DA0` / manifest `sub_102A5860` / PAK `sub_102A7100`)。PAK 是先写到 `PAKS/TMP.tmp` 再 rename 的。

### 1.9 读取/校验路径(游戏加载器)

这条链是搞懂"无效果"真凶的关键,顺着走一遍:`sub_103FB240`(负责报 `"Unable to load mod.\nFailed because :"`)→ `sub_103F8BC0`(报 `"Unable to load mod: <name>"`,成功返回 1)→ **`sub_103F83C0`(真正干加载/校验的地方)**:
1. `if (*(this+312)) return 1;`(已经加载过);`if (!*(this+200) || !*(this+276)) return 0;`(文件表 / offMan 为空 → 静默失败)。
2. 顶部那个循环:解析 REQUIRED_MODS 依赖(`sub_103F8FF0` 查找 + 递归 `sub_103F83C0`),缺了或版本不对会记 `"Unable to activate mod : … with guid:"` / `"… is not installed"`。
3. 重开文件,`sub_103F7E60` 检查 required-mods 版本(没依赖就空过)。
4. **reqHash 比对**:`sub_103F5500(this,0)` 重算后 ?= 存的 reqHash(没依赖时 0==0)。
5. **`sub_102A3320`**:读 manifest 版本(`> word_125E3854(=2)` 就拒)、读 hashValue(不校)、然后 **`sub_102A2690` 重算并比对 rollingHash** —— **就是这一步在卡 rollingHash**,对不上直接 `goto LABEL_27`(`fclose; return 0`,一声不吭)。

> 所以你会遇到这种"灵异现象":容器结构对、文件清单对、所有内容字节都对,但只要 rollingHash 一个字段不对,整个 mod 就被静默拒掉。"launcher 能勾、进游戏没反应"的全部机理,就在这一步。

### 1.10 激活机制(MODGUID)

`<存档>/modlauncher.sch` 里:`[MODS] <INTEGER64>MODGUID:<modid> [/MODS]`。游戏会去加载 header 里 modid 跟它对得上的那个 `.MOD`。也就是说,勾选这个动作是按 **MOD_ID** 激活的,跟文件名、跟 hash 都没关系。

---

## 2. BINDAT(`.DAT` → 二进制)

序列化这条链是 `sub_10289A40`(配合字符串收集 `sub_10289950`、interner `sub_1023E9F0`、节点写 `sub_10289860`);`sub_1028ED40` 是 WriteShortString。

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
- 类型映射:`INTEGER`→1、`FLOAT`→2、`UNSIGNED INT`→4、`STRING`→5、`BOOL`→6、`INTEGER64`→7、`TRANSLATE`→8。键名走 **rg_hash**(见 §7,大写)。
- **STRING/TRANSLATE 的值存的是字符串表 id**;空串用 `0xFFFFFFFF` 这个哨兵内联(不进表)。
- 编码必须用 **surrogatepass**:编辑器是逐 wchar 原样读写、不校验 UTF-16 代理对的。`TAGS.DAT` 里有人把浮点色块直接拼进了 `<STRING>:` 值里(被重新解读成了孤代理),不开 surrogatepass 根本字节往返不回去——这种脏数据是踩出来的,不是猜出来的。

### 2.2 字符串 id 解析模型 —— ★ 逐文件(model A,已证)

这一节的推理是 BINDAT 里比较关键的一块:
- shipped 格式里,id 看起来像个**全局会话计数器**(`sub_1023E9F0` 里一路 `counter++`),很容易以为是一张全局表。
- **但游戏其实是逐文件解析的**(model A):每个 BINDAT 自带一张表,body 里的 id 用**它自己这张表**去解析。
  - **铁证在这**:shipped 的 base game 自己就带着 **565 处跨文件 id 撞号**(同一个 id 在不同文件里指不同的串,比如 id 1398 在这儿是 `'SET STAT ON LEVEL'`、在别处是另一个串),而游戏照常运行 → 要是真有一张全局合并表,早就崩了。
  - 表是**按 id 排序**的 → 游戏对每个文件的表做二分查找 → 不管 id 多稀疏都查得到。
- **由此可知**:id 具体取什么值无所谓,只要**在文件内唯一**就行。于是我们离线打包**直接弃用 corpus 字典,改成 per-file hash**(`HashStringDict`:`rg_hash(s)` 算出来,文件内线性探测保证唯一)→ 没有共享状态、天生可并行、还确定。这套已经**进游戏验过**了(职业、技能、图标全对得上)。
  - corpus 字典(扫遍所有 shipped BINDAT 重建 id↔串,存 `data/bindat_string_dict.pkl`)我们留着,但只在跑"compiler byte-exact 测试"时用。

---

## 3. BINLAYOUT(`.LAYOUT` → 二进制)

这是个 schema 驱动、逐 descriptor 编码的家伙(schema 落在 `data/binlayout_schema.json`);写入链 `sub_101169B0→sub_10116780→sub_10116650→sub_10116420→sub_10115320`,datagroup 走 `sub_101150F0`。

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
`<B>count` + 每个逻辑对象 `{<B>ID <q>OBJECTID <f>X <f>Y <I>end_offset <B>link_count}` + links `{<B>LINKINGTO str OUTPUTNAME str INPUTNAME}`(名字是内联的,不是解析过的 id)。

### 3.3 Datagroup(= `CLayoutBinaryGroup` 树,镜像每个 `Group` 对象 desc=1,合成一个根 id=-1)
节点:`<q>id <B>CHOICE@16 <I>RANDOMIZATION@20 <B>NUMBER@24 <I>@28 <I>TAG@92 <B>@25(NO TAG FOUND)/@26(LEVEL UNIQUE)/@27(GAME MODE) <I>+<q>[]ACTIVE THEMES <I>+<q>[]DEACTIVE THEMES <H>child_count`。其中 `@28` 是该 Group 对象块的流偏移;`TAG@92` 是运行时 tag 注册 id(`sub_10253630`,我们离线把它学进了 `data/binlayout_datagroup_tags.json`)。

---

## 4. RAW 索引文件(7 个)

写入分派器 `sub_1029BFA0`;下表里 `SS` = ShortString。每个 RAW **索引一类源 .DAT/.LAYOUT**;各自的扫描序见表后说明。

| RAW | 写入器 | 结构 |
|---|---|---|
| **AFFIXES** | `sub_103C4170` | `<H>count`;per: SS(FILE) SS(NAME↑) `<IIII>`MIN_SPAWN(0)/MAX_SPAWN(999999)/WEIGHT(1)/DIFF(-1) `<B>`n + SS×(UNITTYPES) `<B>`n + SS×(NOT_UNITTYPES) |
| **SKILLS** | `sub_102ECFD0` | `<I>`count(仅含非空 NAME 的);per: SS(NAME↑) SS(FILE) `<q>`UNIQUE_GUID(-1) |
| **MISSILES** | `sub_102FB490` | `<H>`count;per: SS(FILE=.LAYOUT) `<B>`n + SS×(每个 DESCRIPTOR:Missile 对象的 MISSILE NAME↑) |
| **TRIGGERABLES** | — | `<H>`count;per: SS(FILE) SS(NAME) |
| **UI** | `sub_103178E0` | `<I>`count(仅含 Menu Definition 且 MENU NAME 非空、非 DO NOT CREATE 的);per: SS(MENU NAME) SS(FILE) `<II>`TYPE/GAME STATE 枚举 idx `<BBB>`(ALWAYS VISIBLE‖CREATE ON LOAD)/MP only/SP only SS(KEY BINDING) |
| **UNITDATA** | `sub_1026CC50` / reader `sub_1026F2B0` | 4 类(ITEMS/MONSTERS/PLAYERS/PROPS)各:`<I>`count;per: `<q>`UNIT_GUID SS(NAME↑) SS(FILE) `<B>`flags(bit0=CREATEAS==EQUIPMENT,bit1=SET) `<iiiii>`LEVEL/MIN/MAX/RARITY/RARITY_HC SS(UNITTYPE↑)。**字段走完整 BASEFILE 继承链**(子→父,取首个 != 默认者);DONTCREATE 的抽象基跳过 |
| **ROOMPIECES** | — | `<I>`count;per SS(FILE);然后 per `<I>`GUIDs + `<q>`GUID× |

几个不写出来会被坑的点:
- **扫描序不统一**:AFFIXES/SKILLS/UNITDATA/MISSILES 走的是 **name-interleaved DFS**(文件和子目录按名字混在一起排、就地递归);TRIGGERABLES/UI/ROOMPIECES 则是 files-before-dirs。`_media_path`:`MEDIA/` 拼相对路径,**大写**(非 ASCII 保留)。这两种顺序很容易混,调试时要留意。
- **GUID 类型坑**:同一个值,`.DAT` 里写成 `<INTEGER64>GUID:`,`.LAYOUT` 里却是 `<STRING>GUID:`,类型不同。匹配的时候两种都得认。
- 字节验证:AFFIXES/SKILLS/MISSILES/UI/UNITDATA 这几个都逐字节复现了 shipped RAW。

---

## 5. MPP 寻路文件(`.mpp`)

### 5.1 格式
每个 `.layout` 旁边躺一个同名 `.mpp`:
```
24B header: <iiffff> gw, gh, worldW, worldD, originW, originD
然后 gw*gh 字节:每 cell 1 字节可行走性(0/1/255)
```
- cell 是 **0.4 单位**一格;区域 snap = `floor((min-0.2)/10)*10 / ceil((max+0.2)/10)*10`。
- **PATH NODE OCCUPATION 是运行时算的**,不会烘进 .mpp(.mpp 里就只有 0/1/255 三种字节)。

### 5.2 生成/写入路径(`EditorRegenPathingData`)
导出 `0x100DDDE0` → `Pathing_RegenAll_worker`(`sub_10018750`):扫 `*.layout` → **单线程** do/while 逐文件 `Pathing_RegenSingleFile_worker`(`sub_10015FA0`),每 20 个文件做一次 Ogre 资源 unload 清扫。每个文件:`CLevel_ctor`(`sub_101FD170`,1160B 的对象)→ 置标志 → `CLevel_SetMppOutputPath`(`sub_1000B980`)→ **`CLevel_LoadLevelData`(`sub_1020AB90`,解析 layout + 经 Ogre 把所有碰撞 mesh 加载进来 + 组装碰撞世界)** → 逐 cell raycast → 写 .mpp → 析构。耗时的大头是 **Ogre mesh 加载 + CLevel 那套生命周期**,raycast 本身反倒不算什么——这也是为什么离线绕开 Ogre 之后能快这么多。

### 5.3 离线 / 无头生成
- 离线 numba 后端(`mpp/native_nb.py`):用 `@njit(fastmath=False)` 把那些标量核镜像一遍,IEEE754 逐位一致;算出来 ~99.7% 的 cell 跟 native 对得上(剩下那点是 cliff/overhang 的浮点 tie-break,加上 nocollide 洞穴墙,这部分理论上不可复现)。
- **无头 byte-exact**:实在要 100% 对齐,就驱动真的 DLL(`TL2-Mikuro-Console.exe` 那个 fork)`InitEditor` + `EditorSetWorkingMod` + `CreateMod`(双 pass:pass1 写 .BINLAYOUT + stub .mpp,pass2 写真 .mpp)。InitEditor 一次大概 ~6.24s(Ogre/PAK/room-piece 数据 ~3s + FMOD+D3D9 device ~2s + shader)。

---

## 6. 编辑器生命周期

- **InitEditor**(`0x10001DD0`):薄壳一个 → `sub_10017120`(848B 的编辑器对象构造,里头含 D3D9/FMOD/Ogre)+ `sub_10019A00`。这里有个反直觉的发现:MPP 的 raycast 是**纯 CPU 几何、根本不需要 GPU**,但 `CLevel_LoadLevelData` 加载 mesh 是走 Ogre 资源管理器的(默认要 RenderSystem 去建 hardware buffer)→ 所以 **D3D9 device 是 mesh 加载的承重墙**,想简单跳过它跳不掉;FMOD 倒是能跳。这一点直接决定了"无头"能省什么、不能省什么。
- **CreateMod**(`0x100DE830`)= 元数据 + MPP + .MOD pack;而且它只认 `<install>/mods/` 底下的工程。
- **崩溃归因**:游戏/编辑器在渲染 tick 里那个 AccessViolation,是 RTX 3070 配老 D3D9 驱动的 bug(关掉 Threaded Optimization / 限 FPS / 上 DXVK 都能压),**跟打包管线没有关系**——排查时容易误判成是打包代码的问题,其实不是。

---

## 7. rg_hash(GUTS 32 位字符串哈希)

用在 BINDAT 的**节点名/键名**上(以及我们 per-file BINDAT 里的字符串 id)。实现见 `mikuro_mod_packer/rghash.py`(已经破解,拿已知的 (串→hash) 对验过)。提醒一句别搞混:BINDAT 的**字符串值**不用 hash —— 那走的是 id 表;rg_hash 只哈希 key 和 name。

---

## 8. 跨切面要点 & 几个被我亲手推翻的旧结论

- ✅ **离线打包 == native 功能等价**(拿 MIKURO_CLASS_QLJX_EN 逐字段证过):文件清单、BINDAT 语义、mesh/贴图/骨骼/材质、RAW 集合、header 全一致;剩下的差异只有——已证无害的随机 mhash/rollingHash 值、benign 的 SKILLS.RAW 顺序、benign 的 BINDAT id 编号,以及一个**源文件本身就写错了**的 LAYOUT(`CHILDREN]` 少打了个 `[`)。
- ❌ **已纠正**:早期判断"rollingHash 是随机、游戏不看"——**完全错误**。它会校验(stride RNG 拿 N 作种子 → 完全确定),必须算对。这是整个项目判断错得最严重的一次。
- ❌ **已纠正**:早期没意识到 **manifest 文件名要大写**,结果小写的 `.dds` 之类资源全查不到。
- **manifest 记录顺序**跟 native 不一样(native 那个顺序是编辑器打包时 NTFS FindFirstFile 的原始返回序),但**无害**——游戏按路径查,不靠顺序。

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
- **工具**:`tools/mod_disasm.py`(.MOD 反汇编)、`cmp_mod.py`/`cmp_bindat.py`(native-vs-ours 对比)、`verify_container_writer.py`(容器写入 byte-exact)、`bench_all_mods.py`/`bench_native.py`(基准)、`tools/tl2_console_fork/`(无头驱动 fork)。
- **性能**:见 [`性能优化记录.md`](性能优化记录.md)(全量打包 185.5→82s 的逐项优化)。
