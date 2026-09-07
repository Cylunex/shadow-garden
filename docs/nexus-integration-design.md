# Garden 接入 Nexus 的详细设计

设计版本：2026-09-07 / UA-1。状态：目标设计，尚未实现。公共身份、鉴权、Agent、模型、命令与回执以 [Platform 统一规范](https://github.com/Cylunex/shadow-platform/blob/main/docs/nexus-unified-access-design.md) 为准；本文仅定义本领域差异。旧接口安全限制在对应能力通过迁移验收前继续生效。

## 1. 当前实现与关键冲突

基线 `082eeb9`。`server/app/routers/machine.py` 的 Nexus Review commit 直接执行 `publish_transition()`；签名绑定主要为 review_id。文章已有草稿/预览/修订/发布/撤回、事件和导出恢复。普通“保存文章”不能继续统一映射到该 commit。

Garden 保留内容、编辑权限、文章版本、预览校验、公开状态、引用和证明；Platform 管理用户/Session、Agent/委托、确认签发与模型连接。不迁移内容表到 Platform，不新增自己的 Agent 配置/审批中心。

## 2. 统一身份与写权限

`server/app/auth.py`、`routers/auth.py`、`app/agent.py` 替换为 SDK。中央 user_id 与 Garden owner 映射，编辑者/发布者角色及每篇文章所有权仍由领域检查；有效中央 session 不等于 publisher。

中央模式禁止 legacy service Token 扩展 scope，不根据缺 registry 自动用旧 token。清除代理自报 actor；执行审计保存 user、Agent、workload 和 decision_ref，不再仅靠 `agent:{id}` 代表授权来源。

发布请求通过中央确认组件，Garden 本地不持有确认签发密钥；已有 verifier 在兼容模式保留。目标模式由 SDK 校验中央票据/claim 并验证文章版本，不需要新增 GardenApprovalGrant 表。

## 3. 命令拆分

| 操作 | 必要参数/对象 | 交互与结果 |
| --- | --- | --- |
| `post.save_draft` | title、Markdown、标签、source refs | direct；committed draft ref/version；不公开 |
| `post.update_draft` | draft_ref、expected_revision、变更 | direct；更新私人草稿/修订版 |
| `post.preview` | exact revision | 确定性内容/链接验证，无公开副作用 |
| `post.publish` | post_ref、待发布 revision/hash、visibility、关键变更摘要 | inline_confirm，发布成功才返回公开状态 |
| `post.update_published` | 已发布版本 + 待发布修订 | 编辑先存私人 revision；替换公开版是单独确认动作 |
| `post.withdraw` | post_ref、published revision | 外部可见状态变化，按中央策略内联处理 |
| `post.tags/search/read` | 范围、版本/查询 | 私人标签修改 direct；读取限制 owner/可见性 |
| `post.export` | 私人导出范围与 revision | 可直接导出本人副本；发往外部/长期共享分开 |

名称为拟议操作。Manifest/Surface 要分别映射 `save_draft` 和 `publish`，不得根据标题关键词判断风险。用户只表达写作意图不自动建立待发布确认卡；确实要求发布时才准备精确快照。

## 4. 发布事务与授权绑定

Nexus 准备文章版本 → Garden preview 返回规范内容 hash/revision 和验证结果 → 中央向用户展示同一快照 → 授权绑定 post/revision/hash/visibility/command → Garden claim 并重查版本/发布角色 → 发布事件、结果与幂等记录同事务提交。

中央不信任模型提供的 preview hash；从声明的领域预览结果取值。预览失败只报告链接/字段问题，参数变化使旧确认失效。并发编辑不允许复用原 review_id 发布新内容。

中央 claim 与内容事务分开；失败后同 command 查询或重领，不能造成二次发布事件。回执包含 draft/published 版本、公开状态、event_ref 和 result URL/ref；URL 是结果字段，不是证明已发布的唯一依据。

## 5. 引用、模型与 UI

上传/嵌入文件使用 Platform Asset 固定版本和用途许可；私有 Travel/Archive 引用默认只保留稳定 URI。发布前领域必须核验引用是否适合公开，不把长期内部签名 URL 写进文章，不因用户确认发布文章就自动公开上游私密原件。

写作助手统一进入 Nexus/Platform Runtime，Garden 只维护写作模板/Skill、内容验证及领域 eval。草稿保存后显示继续编辑/修订入口；发布内联确认不跳独立 Garden 审核页，预览验证可在后台进行。

## 6. 迁移与验收

先拆草稿与发布路径并补 command/status，然后统一 Session/Agent/确认。旧 Review v1 保留真实 publish 含义和旧安全门禁，不能为迁移将其 risk 下调。新中央模式发布能力上线后注销旧 token/签发配置和独立认证实现，历史事件不重写。

验收：存草稿不发布；模型无法确认自己；确认后修改文章/可见范围拒绝；发布角色撤回；无权限读取/公开上游私有图失败；并发双击只有一个发布事件；丢响应能读回已发布版本；撤回不声称收回外部缓存。增加源代码合同 fixture 与浏览器场景，保留现有版本/导出恢复回归。
