# Affordance Runtime 中文深度解读

这是一个零依赖静态 GitHub Pages 报告，入口为 `index.html`。页面内容绑定到分支
`agent/migrate-runtime-components` 的提交 `786857f8fb61aa99f2c7e6a23eb8225957e1438b`。

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
