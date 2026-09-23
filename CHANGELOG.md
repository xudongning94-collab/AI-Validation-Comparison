# Changelog

## 0.1.0-alpha.4 — D5 integration / D6
- 将 D5 干扰识别正式接入 D3 文本查重：`exclude` 项不参与正文重复率，`downweight` 项按配置系数降权
- 文本 Finding 新增原始相似度、干扰系数、双方干扰分类与动作元数据
- 新增图片特征提取：SHA-256、pHash、平均 RGB、尺寸
- DOCX 图片定位增强：尽量映射到正文段落索引，同时保留 relationship part
- PDF 图片提取补齐 SHA-256、pHash 与颜色特征
- 新增图片重复检测 Alpha：字节完全一致 + pHash 汉明距离 + 平均色 + 宽高比辅助过滤
- 新增图片重复率、图片对摘要、`image_compare.schema.json`
- 新增 `scripts/compare_images.py`
- 新增图片相似度、Schema、干扰降权自动化测试
- 当前自动化测试 15/15 通过

## 0.1.0-alpha.3 — D4/D5
- 新增格式检查 Alpha：正文主样式统计、字体/字号离群段落识别、左右页边距异常提示
- 新增干扰项识别 Alpha：标题、低信息短文本、招标响应/法定模板规则识别
- 干扰项输出 `exclude` / `downweight` 动作，为后续文本查重接入降权策略
- 新增 `scripts/check_document.py` 本地检查入口
- 新增格式检查与干扰识别自动化测试
- 当前自动化测试 10/10 通过

## 0.1.0-alpha.2 — D3
- 新增 2-5 文档文本两两比对
- 新增字符 n-gram 倒排候选召回，避免直接全量笛卡尔积
- 新增 TF-IDF / SequenceMatcher / containment 词法融合相似度
- 新增高度重复 / 中度相似 Finding 输出
- 新增按唯一重复段落字符数计算的重复率
- 新增重复章节 Top 聚合
- 新增 `SemanticReranker` 接口，为 Embedding 精排预留稳定边界
- 新增 `text_compare.schema.json`
- Document ID / Finding ID 改为稳定哈希派生，便于缓存与审计
- 新增文本比对 CLI、Schema 校验与集成测试

## 0.1.0-alpha.1 — D0/D1/D2
- 创建工程基线与目录结构
- 建立 DocumentIR / Finding / Report 三类 Schema
- 实现 DOCX Parser Alpha
- 实现 PDF Parser Alpha
- 增加统一 Dispatcher 与本地 CLI
- 增加基础测试
- 固化 HiAgent 轻配置边界
