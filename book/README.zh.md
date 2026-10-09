# 双语书稿维护与出版

[English](README.md)

这里面向作者和维护者，不是读者正文。读者可以从[中文书稿目录](../docs/book/README.zh.md)开始，并通过网站的语言切换器进入对应英文页面。英文是主稿，中文是完整配套版本，不是摘要。每种语言的**同一份 Markdown 源文件同时用于网站与可重排 EPUB3**，不另存一套电子书正文。

全书覆盖全部 143 个知识章。**发布验收必须从齐全且同步的源稿实际构建两种语言的完整 EPUB。** 双语小样本只能验证导出流程，不能证明完整英文书已经构建或审校完成。

## 两种语言，各自共用一份正文

英文知识章使用 `docs/<topic>/<NN-module>/NN-chapter.md`，完整中文版本使用同目录的 `NN-chapter.zh.md`；各级索引和前后附页也遵循此规则。网站根路径为英文，中文位于 `/zh/`，切换语言应留在同一逻辑页面。除共用资产和外部资料外，源文件内链指向同语言页面。导出不翻译、不改写正文，也不把简体转成繁体。

[`en/manifest.json`](en/manifest.json) 与 [`zh-CN/manifest.json`](zh-CN/manifest.json) 共用 143 个稳定知识章 ID、九篇结构与阅读顺序。书名分别为 **AI Engineering Interviews: From Model Foundations to Field Delivery** 和 **AI 工程面试：从模型原理到现场交付**，篇标题、源路径和元数据按语言设置。网站仍沿模块组织，电子书依据 manifest 的显式顺序编排。

九篇依次为：LLM 23 章、多模态 10 章、工具与协议 15 章、RAG 22 章、Agent 25 章、框架与编排 23 章、生产工程 13 章、安全与治理 10 章、FDE 2 章。篇内按原文件章号递增，每篇重新从第 1 章开始。英文源 H1 使用 `# Chapter N: Title`，两种语言保留相同的编号小节层级。组装后的标题显示“第一篇 第1章”等完整位置，小节号和正文中原有的“第十四章”不做全局替换。

manifest 保存篇标题、章节稳定 ID 和路径；知识章标题从源 H1 读取。`front_matter` 与 `back_matter` 指向 `docs/book/` 中对应语言的扉页、前言、读法、致谢、作者与许可页。读者目录由脚本生成，不手工维护另一份 143 章标题清单。

## 日常编辑与组装

日常改稿从英文开始，**在同一个 PR 中更新中文配套页**。若英文只调整措辞、中文含义确实无需变化，也要明确审阅这一判断。保留原中文材料中的解释、假设、例子与技术深度，依据所引原始资料核对论断。保留 API 标识符、示例数值、公式与版本限定；翻译解释性注释和图中标签时，不改变可执行行为。

维护顺序是：更新真实的英文与中文源文件，包括把中文内链指向 `.zh.md` 配套页；重建两个读者目录；记录真正审阅过的文件对；最后运行严格检查并构建两个版本。组装只需要 Python 3.10 或更新版本的标准库。从仓库根目录运行：

```bash
# 修改两种语言的源文件后，重建并提交两个读者目录。
# 单独维护索引不要求同步记录已经更新。
python3 scripts/build_book.py --language en --write-index
python3 scripts/build_book.py --language zh-CN --write-index

# 此时按下文的 --record / --record-all 用法，记录真正审阅过的文件对。
# 然后运行只读同步检查；ROOT 指仓库根目录。
python3 scripts/check_translations.py --root .

# 不生成母稿，分别检查两个版本。
python3 scripts/build_book.py --language en --check
python3 scripts/build_book.py --language zh-CN --check

# CI 同时检查目录是否过期。
python3 scripts/build_book.py --language en --check --check-index
python3 scripts/build_book.py --language zh-CN --check --check-index

# 组装母稿及可追踪的构建记录；默认语言为英文。
python3 scripts/build_book.py
python3 scripts/build_book.py --language zh-CN

python3 -m unittest discover -s scripts/tests -p 'test_build_book.py'
```

单独执行 `build_book.py --language LANG --write-index`，不带 `--check` 或 `--output`，属于源索引维护：仍校验 manifest 和源文件，但不要求同步记录已经更新。所有 `--check`、普通母稿组装、EPUB 导出，以及与 `--output` 同用的 `--write-index`，都必须先通过 `scripts/check_translations.py --root ROOT`。配套译稿缺失、同步记录过期，或检查器本身不存在，都会使**这些严格入口直接失败**，不回退到另一语言、改标签冒充，也没有正式出版的跳过检查参数。

同步检查器默认只读。重建两个目录并真正完成编辑审阅后，才可用 `--record PATH.md ... --note "说明实际完成的审阅"` 记录指定文件对。迁移期间使用 `--record-all --note "说明实际完成的审阅"`，要求已审阅全部覆盖页面。示例说明要换成实际完成的审阅内容，不能只刷新哈希来消除错误。独立的 `Book` 解析器测试可隔离同步检查，正式出版命令不可绕过。流程不引入自动或付费翻译服务、API 密钥、浏览器翻译，也不在构建时重译全书。

两个入口都接受 `--language en|zh-CN`，默认 `en`。高级用法 `--manifest book/zh-CN/manifest.json` 接受仓库相对路径，从 manifest 元数据推断语言，**不能与 `--language` 同用**。语言、源路径后缀、H1 格式和扉页 H1 必须一致。即使只构建一种语言，两份正式 manifest 及配对源文件也必须齐备。章节发现按语言分别检查恰好收录一次，不把 286 个双语文件算作一个版本。漏章、重复路径/ID、非法 JSON 字段、错误顺序或 H1 章号、越界路径、缺少资产或片段锚点都会失败；不要跳过坏文件来让构建通过。

输出分别为 `book/en/generated/manuscript.md` 和 `book/zh-CN/generated/manuscript.md`，同目录生成 `manuscript.build.json`，必要时复制本地资产到 `assets/`。检查成功时会标明语言，并报告该版本的 `chapters=143 parts=9`。生成目录已被忽略，不提交组装正文。`--output FILE` 可指定仓库外文件，资产随它放在相邻目录；仓库内输出只能位于所选语言的生成目录，不能覆盖源文件或另一语言的产物。`--check` 不与 `--output` 同用。单独执行 `--write-index` 只更新 `docs/book/README.md` 或 `docs/book/README.zh.md`，不写母稿。

新增、移动或删除章节时，同时更新两份 manifest、配对源文件、各级网站索引和 MkDocs 导航，再重建两个书稿目录。标题审校完成后也要重建目录。正式发布前仍需运行 `python3 scripts/check_docs.py`、`npm run check:mermaid` 和 `.venv/bin/mkdocs build --strict`；组装器不能替代逐章技术审校。

## 转换边界

| 输入 | 母稿中的处理 |
|---|---|
| YAML 页元数据 | 只剥离文件开头成对的 `---` 元数据块，不把描述插入正文 |
| 书内章节、前后附页链接 | 改为同一文件内的稳定锚点；原有标题片段会先校验，再映射到书稿锚点 |
| 网站总目录、主题目录链接 | 分别映射到书稿目录与对应篇；不拼接网站索引正文 |
| 模块目录或其他未收录 Markdown 页面 | 校验目标后转成 `source_url` 下的完整线上链接，保留所指模块的含义；**需要联网**，不冒充某一章 |
| 本地图片和其他非 Markdown 附件 | 校验存在且未越出仓库，复制到输出旁的 `assets/`；保留仓库相对层级，避免重名覆盖 |
| 外部资料链接、远程图片 | 保留原 URL，不下载；远程图片还不是离线出版资产 |
| 参考式链接 | 统一重写定义目标，并给引用标签加章节命名空间，避免整书重名串链 |
| 代码围栏、行内代码、数学、缩进代码 | 保留原文，不把其中的示例链接、注释或标题当作正文改写 |
| 编辑用 HTML 注释 | 不进入读者稿；代码示例里的注释仍保留 |
| 已知格式的重复作者页尾、返回网站目录行 | 只移除这些明确模式；不删除技术限定、来源说明或第三方具体出处 |

这是为本仓库维护的 Markdown 子集组装器，不是通用 CommonMark/EPUB 引擎。支持普通行内链接（含括号 URL、尖括号目标和同一行的可选标题）、常规参考式链接、带引号的 HTML `href`/`src`。脚注、源 HTML 自定义锚点、`srcset` 等尚未实现的结构会明确报错；需要时应先增加显式转换和回归用例。新增块级语法或多行链接时也应扩展测试，不能只看命令是否退出成功。

篇锚点形如 `part-agent`，章锚点形如 `agent-24`，编号小节形如 `agent-24-s24-2`。不编号的标题使用章内顺序 ID，例如 `agent-24-extra-01`。不同语言的标题片段映射到这些锚点。更改标题不会改动章 ID 或编号小节 ID；调整小节编号、不编号标题的顺序时，需要重新核对交叉引用。

此前审校已从章节源文件移除通用署名页尾；组装器保留对旧格式的兼容处理，仓库许可继续有效。遇到未识别的本章作者声明时，脚本报错而不是猜测删除范围。第三方具体署名、论文与规范出处应留在对应论证旁，通用署名和许可集中在 `docs/book/colophon.md` 与 `docs/book/colophon.zh.md`。

## 版本记录与术语

`schema_version` 表示 manifest 格式，`edition` 是内部稿件版本标识，不代表已出版的版次或 ISBN。冻结每种语言的稿件时，记录 Git 提交、manifest 与源文件哈希、审校记录，以及 `manuscript_sha256`。同样的输入应得到同样的母稿字节；变更稿件时更新内部版本并保留上一版构建记录。

章 ID 是跨语言身份，不随译名、文件移动或展示顺序重新生成。记录本次迁移采用的中文源版本与真正一起审阅过的双语版本，不复制中文生成稿再独立维护一套英文。此前的中文审校记录不证明英文译稿已经审校。

术语表以稳定概念 ID 为键，至少记录中文写法、英文首选词、保留缩写、语义备注和首次出现的章 ID。像“记忆”“上下文”“状态”“检索”“工具执行”这些容易混用的词，要先确定语境，再统一译法。保留产品名、API 标识符和必要版本限定；不通过统一译名掩盖原本不同的概念。术语表或哈希记录本身不能证明术语和翻译审校已经完成。

## EPUB 导出与下载

网站继续走 `.github/workflows/docs.yml`；电子书走独立的 [Build EPUB](https://github.com/zongyangbigpolo/awesome-ai-roadmap/actions/workflows/epub.yml)，通过 `en` / `zh-CN` 矩阵处理 PR 预览、影响书稿的 `main` 更新和手动运行。导出流程只有仓库读取权限，不发 Release、不部署网站、不上传 KDP；网站部署不以 EPUB 导出成功为前提。

一个内容 PR 同时维护两种语言，网站与 EPUB 检查使用同一组源文件，合并后各自构建。无需另开“EPUB 内容 PR”，也不手工维护或提交 `.epub`。完整书籍工件只有在源文件齐全且通过同步检查后才能产生，不能用小样本代替整书导出。

在成功运行的 **Artifacts** 中下载 `ai-engineering-interview-en-epub` 或 `ai-engineering-interview-zh-CN-epub`。解压得到对应的 `ai-engineering-interview-en.epub` 或 `ai-engineering-interview-zh-CN.epub`、`build.json`、母稿哈希记录、静态渲染记录和 EPUBCheck 报告。下载通常需要登录 GitHub。保留期为 90 天（仓库或组织策略可能进一步缩短）；过期后，有 Actions 操作权限的维护者可选 **Run workflow** 重建。

### 本地工具与导出

完整导出支持 macOS 的 arm64、x64，以及 Linux x64；需要 Python 3.10+、Node.js **22** 和单独安装的 Java 17+。安装脚本不改全局 PATH、不替用户安装 Java，也不修改另一个主工作树。Windows 可使用 x64 Linux 环境运行。虽然固定的 Pandoc 归档另含 Linux arm64，当前 Puppeteer 配套 Chromium 不支持该平台，因此不能据此宣称完整导出支持 Linux arm64；请使用 x64 runner。

```bash
# 首次安装，或固定依赖版本发生变化时运行。
python3 scripts/install_epub_tools.py
npm ci --prefix book/epub

# 包含全书组装、静态渲染、打包、链接审计和 EPUBCheck。
python3 scripts/build_epub.py
python3 scripts/build_epub.py --language zh-CN
```

默认文件为 `book/en/generated/epub/ai-engineering-interview-en.epub` 和 `book/zh-CN/generated/epub/ai-engineering-interview-zh-CN.epub`。目录内还保留中间母稿、`rendered/` PNG 和构建记录，便于审稿。`--output DIRECTORY` 可指定独立输出目录，仍受源文件保护和语言隔离限制；只能替换本工具已有的输出。只有全部检查通过才替换上次成功产物；缺工具、资源丢失、未知公式、渲染错误或写入失败都会报错，不降级成缺图版本。

Pandoc **3.6.4**、EPUBCheck **5.2.1** 下载到 `book/epub/.tools/`，按 [`epub/tools.json`](epub/tools.json) 固定的完整归档 SHA-256 校验后解包。校验值来自官方 GitHub Release 的 HTTPS 下载，不冒充上游签名。Node 依赖单独锁在 `book/epub/package-lock.json`：Mermaid **11.12.0**、MathJax **3.2.2**、Puppeteer **24.15.0**、Noto Sans SC **5.2.5**；Chromium 放在 `book/epub/.cache/puppeteer/`，普通网站的 `npm ci` 不会安装它们。首次安装需要联网获取工具和字体，书稿转换不发送到任何远程渲染服务。

Linux 若缺 Chromium 系统库，按 [Puppeteer 的运行环境说明](https://pptr.dev/troubleshooting) 安装对应发行版依赖；不要用关闭沙箱掩盖缺库。本地默认启用浏览器沙箱，只有独立、可丢弃的 CI runner 才应显式设置 `EPUB_NO_SANDBOX=1`。

### 导出如何保留阅读内容

导出复用 `scripts/build_book.py` 的 manifest 校验、次序、稳定 ID、链接与署名处理，然后由 Pandoc 解析 Markdown AST。代码围栏、行内代码和缩进代码不是公式；示例代码中的 Mermaid 不会被当成真正插图。独立的源分段计数与 AST 图/公式计数必须一致，遇到超出当前支持子集的结构要补充转换与回归测试，不能直接放宽计数。

每个知识章、篇页和前后附页分别生成 XHTML，线性 spine 顺序来自 manifest。保留原扉页，不使用 Pandoc 自动扉页；母稿的正文目录换成单一的 EPUB 原生导航目录。篇内原章号不变，稳定章/节 ID 移交给标题；打包后按真实 XHTML ID 与资源哈希修正跨文件链接，并逐条检查目标是否存在。参考资料仍可点击联网访问，**正文、图和公式本身不依赖网络或脚本**。

每种语言的源文件继续保留 Mermaid 与 LaTeX，仅在导出时把该语言的标签在本地转成带替代文本的 PNG。单个浏览器加载隔离安装的渲染器与字体，禁止访问外部地址，批量绘制并按语言、内容、渲染器与 lockfile 缓存。图片使用两倍像素密度和白色背景，避免深色阅读模式下透明黑字消失；行内公式按 `em` 设首选宽度，受到单元格或段落宽度约束时等比缩放，不撑宽页面。点公式图片可进入独立的完整公式页并返回原位置，原始像素不减少。中文字体用于生成图片，不锁定电子书正文字体。

源文件中的普通图片目前支持本地 PNG/JPEG/GIF。远程图片、带依赖的 SVG、Mermaid 内嵌图片/图标和交互链接需要先做显式的离线静态转换；当前导出会拒绝这些输入，不替作者联网抓取或静默删除。

每幅图在正常标签字号下的渲染尺寸必须不超过 **480 × 650 CSS 像素**，否则导出失败，必须修改源稿：保留简短完整的图，把分支、条件和细节放在邻近正文中，或将不同概念拆成数幅小图。这些修改同时用于网站和电子书，而不是仅在电子书中替换。渲染器只生成完整图片，不再生成或接受局部切片。图片按测得的 CSS 宽度显示，不按两倍像素密度的 PNG 尺寸放大。子图标题与节点框重叠也会使导出失败；整体尺寸较小，并不代表图内排版可读。

正文中的每幅图都可以在独立的非线性图页打开同一张完整图片，并精确返回原位置；复用的 PNG 仍只打包一份。图页不混入章目录或连续阅读顺序。避免分页的样式有助于让图片保持完整，但尺寸上限和 CSS 不代表 Kindle 分页已经验收。代码只通过 CSS 视觉换行，不向代码内容插入换行符。四列及以上的表格在视口宽度不超过 600px 时，将每行显示为带字段名的纵向内容；大屏保留表格形式。字段名取自对应语言的列标题，单元格内容、代码和链接保持完整。这类宽表中的合并单元格、多行表头、图片表头或空表头需要另行支持。表格、图和公式仍需在实际设备查看，也要检查不应用这些媒体查询的阅读器。

生成的导航、详情页文字和返回链接全部使用所选语言，EPUB/XHTML 语言元数据也必须一致。EPUB 专用 CSS 位于 `book/epub/epub.css`，不会覆盖站点样式。导出不生成封面、不编造 ISBN 或出版社；书目作者沿用 Polo Li，许可仍集中在书末。不能只修改 metadata 就把中文源文件算作英文版。

第一列用作行名称时，允许左上角表头为空：保留行名称，不凭空添加字段名。其他列的空表头会使导出失败。

### 回归与验收边界

回归应明确区分源索引维护与出版：单独的 `--write-index` 可在记录同步状态前重建目录，但记录过期或缺失、检查器不存在时，`--check`、母稿组装、EPUB 导出和 `--write-index --output` 仍必须失败。索引维护仍拒绝非法 manifest、源路径与 H1，不能借此发布不完整的译稿。

```bash
# 这些单元测试不需要导出工具或浏览器。
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py'

# 实际渲染和英/中文小样本集成；不能跳过缺失的工具。
npm test --prefix book/epub
python3 -B scripts/tests/epub_integration.py

# 全部译稿通过同步检查后，最终集成必须实际导出两个完整的 143 章版本。
python3 scripts/build_epub.py --language en
EPUB_LANGUAGE=en npm run test:layout --prefix book/epub
python3 scripts/build_epub.py --language zh-CN
EPUB_LANGUAGE=zh-CN npm run test:layout --prefix book/epub
```

双语小样本必须真正运行 Pandoc、浏览器和 EPUBCheck；缺工具应失败，不是跳过后算成功。它们不能代替上面的两次完整导出，后者要求每份译稿都已齐备。`EPUB_LANGUAGE` 默认为 `en`，排版测试必须检查指定版本，不回退到另一种语言。

`build.json` 区分图/公式的**出现次数**、去重渲染数和实际打包资产数，并记录图的尺寸上限、局部切片数为零、字节数、SHA-256、章数、篇数、spine、内部链接检查及工具版本。`manuscript.build.json` 记录每个源文件与资产哈希；`render.json` 可定位 PNG 及尺寸；`epubcheck.json` / `.txt` 保留官方校验结果。完整导出还检查 mimetype、OPF、语言、导航、所有内部片段、资源完整性、脚本与远程依赖。图/公式无错误、EPUBCheck 无错误和警告后才发布工件。

浏览器排版回归使用所选实际 EPUB 的代表页（包括量化章节的公式表格和智能体构建模块的五列比较表），检查 375px 宽度下 16/24/32px 字号、页面无横向溢出、公式纵横比、代码未裁剪及完整公式页的返回链接；还检查宽表字段名在 375px 下显示、在 768px 下隐藏。此外，会在 375px 和 768px 宽度下检查**每一次插图出现的位置**，覆盖正文和独立图页，核对原始及显示尺寸、纵横比、避免图片内部分页的样式，以及没有局部切片。`layout.json` 记录 EPUB 哈希和这些测量值，CI 一并附上。这仍不等于人工排版验收；还要在电子书阅读器与 Kindle Previewer 查看对应语言的字体、窄屏代码/表格、不同字号、横竖屏、深色模式以及全部图和公式。导出记录会明确保留“未进行 Kindle Previewer 人工验收”和“未声称 KDP 接收”。

## 出版限制与人工决策

**格式支持、预览验收与发行资格是三件事。** KDP 接受符合 Kindle Publishing Guidelines 的 EPUB，并建议上传前用 Kindle Previewer 检查。通过 EPUBCheck 只说明文件满足其检查的 EPUB 规范，不说明视觉排版已验收，更不说明 KDP 已接受该书或其语言。

**简体中文仍受语言资格限制。** 已记录的 KDP 语言列表只列出 `Chinese (Traditional) (eBook only)`，未列简体中文；官方说明不支持语言的电子书可能被移除。因此继续维护完整简体版，但不能把本稿称为可直接上架的 KDP 书，也不能虚报成繁体或英文绕过限制。真正的英文母稿解决的是语言稿件问题，不代替预览、权利和平台审核。不要未经作者决定偷偷转为繁体。

**按真实生产方式申报 AI 内容。** KDP 要求申报 AI 实际生成的文字、图片或翻译，即使随后经过大量人工修改仍属 `AI-generated`。仅用 AI 对人写内容做编辑、润色、检查等辅助，才属于对应的 `AI-assisted` 情形。逐项记录真实过程，在后台按当时要求申报，不能因为人工审校过就自动改报为纯人工。

**普通 KDP 出版不等于 KDP Select。** 条款的 Optional Programs → KDP Select → Exclusivity 要求项目期间的数字独家分发。本项目已有 GitHub/Wiki 公开全文且已按 CC BY 4.0 授权，不应默认勾选 Select 或 Kindle Unlimited。作者需另行核对是否能够满足独家义务；删除版权声明或关闭仓库不会撤销已经授予的 CC 许可。

**保留权利边界。** 作者可以商业出版自己的原创内容，但不能撤销已授予的 CC BY 4.0 许可。第三方论文、代码、截图、商标和引用各有其权利与许可，须根据最终实际用法复核；不能因原仓库开放就把全部引用视为可任意重印。集中许可页不代替第三方要求的具体署名、通知或授权。

## 到可发行电子书还差什么

先完成技术与翻译审校，同步双语稿并冻结一版，再实际构建和验证**两个完整的 143 章 EPUB**，不能只跑样本。静态插图、公式、原生导航和可重排打包仍需人工确认图中文字、公式含义、替代文本、宽表与代码的阅读效果，并复核资产权利。

用 Kindle Previewer 检查不同屏幕、字号和横竖屏；公式与图表还要人工逐页看，不能仅凭结构校验成功。具备平台支持的真实语言稿、完成封面、书目资料、真实致谢和权利复核后，再根据实际出版语言及 AI 使用情况填写 KDP 后台。没有获得的 ISBN、出版社、出版年次或贡献者姓名，不应为凑齐页面而编造。

### 出版资料与核对日期

这里保留的是既有核对记录，**不是本次新查证**：EPUB 格式与语言支持核对日期为 **2026-09-18**，其他出版条款保留 **2026-09-15** 的记录。平台规则会变化，上架前须重新查阅原始页面。

- KDP [Supported eBook Formats](https://kdp.amazon.com/en_US/help/topic/G200634390)。
- KDP [Book Supported Languages](https://kdp.amazon.com/en_US/help/topic/G200673300)。
- KDP [Content Guidelines](https://kdp.amazon.com/en_US/help/topic/G200672390)。
- KDP [Terms and Conditions](https://kdp.amazon.com/en_US/terms-and-conditions)，既有记录中的页面更新日期为 **2024-09-27**。
