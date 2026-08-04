# Affordance Runtime 中文深度解读

这是一个零依赖静态 GitHub Pages 报告，入口为 `index.html`。页面内容绑定到分支
`agent/migrate-runtime-components` 的提交 `786857f8fb61aa99f2c7e6a23eb8225957e1438b`。

总览页的核心 E2E 章节分别链接到九个转换审计单页：`entrypoints.html`、
`intake.html`、`planning.html`、`agent-loop.html`、`perception-action.html`、
`verification.html`、`recovery.html`、`context.html` 和 `evidence.html`。

`architecture-modification-audit.md` 是所收架构修改意见的规范追踪报告。它逐项区分
固定基线的当前事实、明确保留的安全边界、当前缺口、建议目标和后置事项，并将每个
条目映射到公开页面的稳定锚点和固定提交源码。总览 `SECTION 02` 同时展示 CURRENT
当前实现链与 PROPOSED 建议目标链；建议链不表示 Runtime 已经完成对应改造。

每个单页必须维持相同审计协议：输入对象、转换者、字段映射、输出对象、保留语义、
可能的语义损失、风险、防护、失败出口和本页损失账本。修改章节名称或文件名时，必须
同步更新总览入口以及详情页的上一章/下一章导航。

## 本地预览

在仓库根目录执行：

```bash
python -m http.server 8000 --directory docs
```

然后访问 `http://localhost:8000/affordance-runtime-deep-dive/`。不要直接双击 HTML；HTTP
预览更接近 GitHub Pages 的相对路径和脚本行为。

## 发布到 GitHub Pages

在仓库 Settings → Pages 中选择 **Deploy from a branch**，选择目标分支并将目录设为
`/docs`。发布后路径通常为：

`https://<owner>.github.io/<repo>/affordance-runtime-deep-dive/`

本目录没有执行远程部署，也不会修改 GitHub 仓库设置。

## 维护规则

- 架构事实以当前代码、测试和 `docs/README.md` 指定的权威文档优先级为准。
- 代码分支或提交变化后，更新页面顶部版本戳，并复核所有“已实现/未实现”判断。
- 新增术语时必须在正文首次出现处解释，并同步术语表。
- JavaScript 只做导航增强；关闭脚本后，正文、锚点与折叠内容仍应可读。
- 修改意见审计必须保留 `CURRENT`、`KEEP`、`GAP`、`PROPOSED`、`DEFERRED`
  五种口径，不能把目标建议合并进当前事实。
- 九个详情页的 conversion block ID 是公开深链接接口；如确需改名，必须保留兼容锚点
  或同步修复 Markdown、总览、测试和已发布链接。
- 当前审计中的实现判断和源码链接固定绑定
  `786857f8fb61aa99f2c7e6a23eb8225957e1438b`。未来 Runtime 发生变化时应新增事实基线
  审计，不能静默把这份历史意见改写成另一个提交的状态。
