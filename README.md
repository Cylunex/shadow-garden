# Shadow Garden

Cylunex 的数字花园 —— 个人网站前端，聚合博客、项目展示、美食分享与旅行记录，持续生长。

## 结构

```
site/                        # 部署内容（即服务器上的 webroot）
  index.html                 # 首页（单页框架：项目/博客/美食/旅行/关于）
  assets/main.css            # 全站样式（浅色/深色自适应）
  blog/                      # 博客文章（独立 HTML，待添加）
scripts/deploy.sh            # 一键部署（rsync 到服务器）
scripts/deploy.env.example   # 部署目标配置模板（真实值放 deploy.env，不入库）
```

## 部署

部署目标（SSH 主机、webroot、验证地址）写在 `scripts/deploy.env`（已 gitignore），首次使用复制模板填写：

```bash
cp scripts/deploy.env.example scripts/deploy.env  # 填入真实值
./scripts/deploy.sh
```

## 约定

- 无构建步骤：纯静态 HTML/CSS，改完即部署；内容多了再考虑静态站点生成器。
- 新板块：在 `index.html` 加一个 `<section>` + 导航项，样式复用 `main.css` 里的卡片/列表模式。
- 服务器地址、域名等站点信息一律不入库，只存在于 `deploy.env` 与服务器本身。
