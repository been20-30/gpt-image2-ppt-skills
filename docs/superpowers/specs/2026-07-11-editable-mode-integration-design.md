# 可编辑模式正式集成设计

## 目标

在保留现有“gpt-image-2 整页视觉稿”默认流程的前提下，增加一个仅在用户明确要求时启用的可编辑模式。该模式把已验证成功的图片转 PPTX 能力正式纳入本 skill，并以 Case 05 夏日商业海报作为仓库示例。

## 用户触发规则

- 默认关闭。未出现 `--editable`，或用户没有明确说“可编辑、可拆分、文字能改、对象能移动”，现有生成行为和 PPTX 结构保持不变。
- 用户明确要求可编辑时，agent 必须在计划、冒烟和交付说明中标记“可编辑模式”，并使用 `--editable`。
- 可编辑模式不能静默退化为整页图片。若缺少 scene、clean plate、素材或遮罩，命令应指出缺少的文件和页码。

## CLI 与输出

主入口增加：

```bash
python3 scripts/generate_ppt.py \
  --plan slides_plan.json \
  --style styles/dark-aurora.md \
  --editable \
  --editable-scenes editable_scenes/
```

- `--editable`：显式启用可编辑模式，默认 `false`。
- `--editable-scenes DIR`：scene 清单目录。每个生成页对应 `slide-XX.scene.json`。
- `--editable` 缺少 `--editable-scenes` 时，允许自动查找 session 下的 `editable_scenes/`；仍不存在则失败并给出操作提示。
- 默认模式继续生成 `<title>.pptx`。
- 可编辑模式生成 `<title>-editable.pptx`，并保留普通整页图片 PPTX、视觉原图和全部证据。

每个 session 的新增结构：

```text
outputs/<session>/
├── images/slide-XX.png
├── editable_scenes/slide-XX.scene.json
├── editable/slide-XX/
│   ├── visual-master.png
│   ├── clean-plate.png
│   ├── repair-mask.png
│   ├── layers/*.png
│   ├── edge-check-*.png
│   └── quality-report.json
└── <title>-editable.pptx
```

## Scene 模型

scene 是 agent 在完整视觉稿生成后创建的人机可审阅描述。必须记录画布、视觉原稿、clean plate 和按 z-index 排序的对象。

支持对象类型：

1. `native_text`
   - 文本、bbox、字体、字号、字重、颜色、对齐、垂直对齐。
   - 标题、正文、日期、数字、标签、徽章文字均使用此类型。
2. `image_layer`
   - 透明 PNG/JPEG 素材、bbox、z-index、对象名称。
   - 主视觉、照片、插画、复杂纹理和无法合理转为 shape 的对象使用此类型。
3. `native_shape`
   - 矩形、圆角矩形、圆、星形、线条等基础 PowerPoint 图形。
   - 支持填充、透明度、描边、旋转和对象名称。
4. `connector`
   - 直线连接线、起止点、颜色、线宽和箭头。
   - 架构图、流程图和关系图使用此类型。

scene loader 必须拒绝重复 ID、越界 bbox、丢失素材、未知类型、无效颜色和不支持的 shape 名称。

## 图片与重叠素材路由

完整视觉稿仍由 gpt-image-2 生成，不能为了可编辑性禁止模型在初始稿中生成标题、正文、数字、表格、Logo 或关键图表。

生成后按以下顺序分层：

1. **A1 原像素直接提取（默认）**
   - 适合轮廓完整、边缘可控、遮挡较少的对象。
   - 重叠的多个对象默认作为一个连接组合层直接提取，除非用户要求分别编辑。
2. **A2 原像素提取 + 遮挡区域补全**
   - 保留可见像素，对被遮挡区域或对象移走后的背景做局部补全。
3. **B AI 分离或重新生成**
   - 仅在 A1/A2 边缘差、遮挡补全失败、毛发/毛绒/透明材质难以可靠抠图，或用户明确使用设计模式时启用。
   - Case 05 属于此路线：毛绒角色、白色冰淇淋和水彩云混合，使用原图参考生成单色键背景的组合主视觉，再本地去背景。

每个独立图片层至少保留黑底、白底边缘检查。对象移动测试必须确认 clean plate 中没有重复对象。

## Clean plate 与文字重建

- 原始完整页保存为 `visual-master.png`。
- 文字和被拆出的对象从底板中移除，得到 `clean-plate.png`。
- API 编辑结果只能在显式 repair mask 内合成；mask 外像素必须保持不变。
- 平滑渐变、霓虹光带和简单卡片背景允许采用确定性插值；AI 修复产生色块、暗圆或幽灵字时必须拒绝。
- 已知文字转为 PowerPoint 原生文本框；数据页的标签和数字必须分别可编辑。
- 架构图、流程图和规则信息图优先重建为原生 shapes/connectors，而不是 clean plate 上覆盖文字。

## 渲染与质量报告

可编辑模式交付前必须执行：

1. scene schema 验证；
2. PPTX 对象清单检查；
3. mask 外像素变化检查；
4. 黑/白底素材边缘检查；
5. Office/Keynote/LibreOffice 回渲染；
6. 文本修改验证；
7. 独立图片移动验证；
8. 人工目测，自动 `pass` 不能代替视觉判断。

`quality-report.json` 记录：模式、路由决策、原生文本数、原生 shape 数、连接线数、图片层数、mask 外变化、缺失对象、边缘检查文件、回渲染文件和最终状态。

## Case 05 示例

新增 `examples/editable-pptx/case05-summer-poster/`，包含：

- 用户原图；
- 无字 clean plate；
- 透明组合主视觉；
- 黑/白底边缘检查；
- scene JSON；
- `editable.pptx`；
- Office 回渲染 PNG；
- 质量报告；
- 示例说明。

README 使用原图与回渲染 PNG 并排展示，并提供 `editable.pptx` 下载链接。README 和 SKILL.md 都明确可编辑模式默认关闭。

## 兼容性与非目标

- 不改变普通模式的生成、编辑、回滚和外部真实图片逻辑。
- 第一版不承诺全自动 OCR、自动字体识别、自动 SAM/BiRefNet 分割或任意截图一键像素级还原。
- agent 负责看图、选择路由并创建 scene；CLI 负责严格验证、渲染、报告和失败提示。
- 不把 API Key、`.env` 或生成过程中的私密凭据提交到仓库。

## 测试门槛

- 新增测试必须先失败后实现。
- 默认模式回归测试证明未传 `--editable` 时仍调用原有 PPTX 打包路径。
- 可编辑模式测试覆盖参数解析、scene 发现、缺失 scene 错误、多页 scene 顺序、四种对象类型、对象命名、报告字段和 `-editable.pptx` 命名。
- Case 05 示例 PPTX 必须可打开，包含原生文本、原生 shapes、clean plate 和独立图片层。
- 全部 tracked regression tests 通过后才能合并。
