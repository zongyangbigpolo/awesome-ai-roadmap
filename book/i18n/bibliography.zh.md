# 维护统一参考资料

网站和 EPUB 共用书末的 `docs/book/references.md` 与 `references.zh.md`。正文引用使用放在 `<sup>` 中的普通 Markdown 链接，例如：

```markdown
论文中的结论<sup>[【15】](../../book/references.zh.md#ref-15)</sup>
```

中文章节使用 `references.zh.md`，编号与英文相同。条目通过显式的 `<a id="ref-15"></a>` 锚点定位，不使用标题，以免目录增加数百个条目。`scripts/build_book.py` 仅在清单中 ID 为 `references` 的文档中接受这些锚点，检查其唯一性，并在组装书稿时解析链接。

## 权威源文件

`book/bibliography.json` 保存稳定的连续编号、原始来源 URL、原有链接标题，以及两种语言中完整迁移的来源说明。编号条目标识一个 URL；各章阅读说明保留原有作者和标题写法、版本、日期、访问限制、许可声明，以及来源的适用范围。不同 URL 保持独立，包括带版本的规范地址、固定提交地址和片段标识；不要仅因标题相似就合并。

两种语言的参考资料 Markdown 页面由登记表生成。修改来源说明或书目信息时，应编辑登记表再重新生成，不要在生成页面中另行维护手写副本。如果没有本地化的专有资料标题，可以保留其原文；这不意味着可以用英文替换中文解释性正文。

## 迁移与日常维护

```bash
# 只读检查，并记录精确的源文件哈希。
python3 scripts/migrate_bibliography.py --report .artifacts/bibliography-review.json

# 先解析完整的两种语言，再写入登记表、参考资料章节和正文引用修改。
python3 scripts/migrate_bibliography.py --apply --report .artifacts/bibliography-review.json
```

始终针对当前源文件运行，不要用旧章节快照覆盖较新的修改。工具在写入前检查源文件是否仍与读取时一致。它只识别明确列出的章末来源标题，保留章节标题和页尾导航、许可说明，并通过共用 Markdown 链接解析器保护示例、代码、公式、注释、图片和 YAML 元数据。默认只报告，不写入。

增加新来源时，先在两种语言的相关论述旁放置明确链接，再运行工具。新 URL 追加到登记表，已有编号不变。如果只是补充一般延伸阅读，应编辑登记表中对应章节的两种语言 `notes`。不要根据旧的章末书目推断某段话引用了哪个来源。记录翻译同步之前，应检查生成的改动。报告中的英文路径和哈希只标识经过机械处理的文件，不证明完成了语义或事实审查。

保留的章末标题通过 `#reading-<stable-chapter-id>` 指向对应的来源说明，原先指向该标题的链接仍然有效。来源说明中指向其他本地章节的链接会按参考资料章节所在目录重新计算相对路径，目标不变。

## 验证

运行 `python3 scripts/migrate_bibliography.py --check`，检查生成页面是否过期、正文是否仍有待迁移的来源链接；运行 `python3 -m unittest discover -s scripts/tests -p test_bibliography.py` 执行回归测试。发布前还应运行既有文档检查、翻译同步检查、中文链接检查、严格网站构建、两种语言书稿检查和 EPUB 回归检查。在网站和 EPUB 中检查上标和参考资料跳转；源文件语法正确本身不代表视觉验收通过。

`.github/workflows/docs.yml` 和 `.github/workflows/epub.yml` 都在发布构建之前运行只读的参考资料一致性检查。路径过滤器覆盖登记表、源页面、迁移脚本和共用链接解析器。CI 中的这项检查不会重新生成文件，也不会记录翻译同步状态。
