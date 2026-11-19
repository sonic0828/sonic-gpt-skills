# catalog.json 与 manifest.json

`catalog.json` 是 Agent 写入的完整盘点，可直接从此例开始。路径使用游戏根目录下的相对路径和正斜杠。工作台直接引用项目素材；需要自制预览时可将固定截图放在项目的开发目录，作为另一个来源。只有截图或录像时，把证据目录当作项目根目录。一个输出目录对应一个项目的一种模式。

```json
{
  "version": 1,
  "project": "示例游戏",
  "mode": "library",
  "coverage": "主场景的生命条和回复道具；过场动画尚未盘点。",
  "items": [
    {
      "id": "hud.health",
      "name": "生命条",
      "category": "战斗界面",
      "evidence": "used",
      "states": ["满血", "受伤"],
      "sources": [{"path": "src/hud.js", "locator": "drawHealth"}],
      "uses": [{"scene": "战斗页", "path": "src/battle.js", "locator": "renderHud"}]
    },
    {
      "id": "item.heal",
      "name": "回复道具",
      "category": "道具",
      "evidence": "file",
      "sources": [
        {"path": "art/items.png", "locator": "heal", "rect": [8, 16, 32, 32], "preview": "物件原图"},
        {"path": "art/items.json", "locator": "frames.heal"}
      ]
    }
  ]
}
```

- `mode` 取 `ui` 或 `library`。分类名称取自游戏。覆盖说明 `coverage` 写明盘点边界和仍不确定的部分。
- `id` 取稳定的配置键、组件角色或资产 ID，与显示名、排列顺序、文件路径解耦。每项至少一处 `sources`。用 `locator` 写图集帧名、代码符号、预制体节点、截图坐标或录像时间点。可省略不适用的字段。
- `evidence` 取 `used`（找到调用点或关卡配置，至少一条 `uses`）、`file`（仅发现素材）或 `visual`（画面可见）。后两种保留空的使用位置。`uses` 每项含场景名和可核对的文件，可再附符号或配置键。`states` 是有据可查的状态名称。
- 需要展示哪张图或哪段媒体，就给对应来源填写 `preview` 作为图注。支持常见浏览器图片、音频和视频。图集或截图的 `rect` 为原图左上角起算的像素 `[x,y,width,height]`。同一路径可用不同区域和图注多次出现。其他格式仅列路径，必要时另附现成缩略图。视频时间点可写入图注和定位。
- `manifest.json` 由构建器生成。用户可在其中编辑条目的 `manual.name`、`manual.note`，保存后重新构建。脚本按 ID 合并，保留手工字段；名称为空时展示提炼名称。
- 更新同一份 `catalog.json`，保留未涉及的条目，再构建。来源改名且身份明确时沿用 ID、更新路径。归属不明时另建 ID，保留原条目与备注供复核。退出本次盘点和文件失联分别标记。已知条目引用的旧文件消失时允许重建；首次引入就不存在的路径会报错。
- 清单用 SHA-256 检查引用文件，文件级变化会影响所有关联条目。更新状态相对上一次构建，包含新增、变更、未变、退出盘点和来源缺失。恢复原 ID 后可继续使用原备注。
