# Case 05：夏日星星人可编辑海报

该示例展示完整商业视觉稿如何转换为可编辑 PPTX：

- 五组文案为 PowerPoint 原生文本；
- 文案面板、产品横幅、夏日徽章和装饰星为原生 shape；
- 角色与粽子冰淇淋作为一个独立图片组合层，可移动和缩放；
- 水彩背景为 clean plate；
- 白底和黑底预览用于检查透明素材边缘。

该主视觉含毛绒、白色冰淇淋和水彩云等复杂边缘，A1/A2 直接抠图效果不稳定，因此按规则升级到 B：根据原图生成单色键背景的组合素材，再本地去背景。

使用生产工作流重新构建：

```bash
PYTHONPATH=. python3 -c "from scripts.editable_pptx.workflow import build_editable_output; build_editable_output('examples/editable-pptx/case05-summer-poster', [1], 'examples/editable-pptx/case05-summer-poster', '夏日星星人')"
```
