# 归属、许可与资料边界

## 自有内容

- `work/`、`tools/` 内本项目原创程序代码：MIT，见 LICENSE。未包含 Blender、插件、第三方 Python 包的源码或安装包。
- 自有建筑几何表达、原创文字说明与渲染图：© 2026 nikochen1997，按 [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) 许可。使用时请注明项目名称、仓库链接和修改情况。
- 原始事实、专名或公共领域建筑本身不因本声明产生新的独占权。

## OpenStreetMap 数据

布局与基础轮廓含 © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)，源数据库采用 [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)。仓库中 OSM 衍生布局数据（包括 `model-data.json`）及模型内对应数据库部分保留 ODbL 义务；MIT 或 CC BY 不能覆盖这部分许可。发布衍生数据库时应继续遵守 ODbL 的署名、提供数据库与相同方式共享要求。渲染图作为 Produced Work 仍须保留 OSM 署名。基础布局数据随仓库提供，相关公开源链接亦见 OSM 版权页。

## 故宫研究资料

故宫博物院的公开建筑介绍、论文、平面图及照片用作事实核对。本项目没有取得这些原版资料的再分发许可，因此不上传原版 PDF、扫描页、照片、网页缓存或插件资料。来源链接和事实摘要不代表资料权利人对本项目背书。历史阶段使用的判断、假设与不确定性保留在各阶段模型清单中。

## 公开副本与历史核验

公开 `.blend` 清理仅限经 SDNA 定位的 `FileSelectParams.dir` 与 `Scene.r.pic` 两个本机路径字段，等长替换后其余字节保持一致；因此公开文件 SHA 与历史审计中的原文件 SHA 不同。原始私人路径不会随包发布。公开 PNG 的图像数据与色彩相关块保留原字节，仅替换文本元数据并补充 OSM 署名。

该归档只发布已清理的旧阶段工程。当前制作基线、研究原文、全部历史大体积核验缓存没有随包公开；历史脚本不保证仅凭公开包即可完整重跑。模型仍可直接打开编辑与渲染。
