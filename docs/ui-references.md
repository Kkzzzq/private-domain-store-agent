# 页面视觉参考

本次美化参考了以下项目的页面组织方式，实际样式及导航图标在本项目内编写，没有引入它们的框架或组件代码。

- Tabler：https://github.com/tabler/tabler。后台导航、表格、表单和统计卡片的层次与留白。
- Medusa Storefront：https://github.com/medusajs/nextjs-starter-medusa。商城图片展示、商品网格和购买信息组织。

B 端样式位于 `web/admin.css`；C 端样式位于 `web/storefront.css`，两端分别加载，商家设置的主题色仍然有效。

保留商品行内 SKU 配置；商品列表不显示勾选框、批量操作栏和禁售按钮；展开 SKU 时隐藏图片路径。
