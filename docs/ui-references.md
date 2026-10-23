# 页面视觉参考

价格数字字体：核对 [Vercel Commerce layout](https://github.com/vercel/commerce/blob/main/app/layout.tsx) 与 Saleor品牌字体，均使用Geist无衬线方案。此项目仅价格数字采用本地Geist Regular/SemiBold（官方npm `geist@1.8.1`），取消过紧字距与过重字重，保持直立。字体位于`web/fonts`，SIL OFL授权随`Geist-LICENSE.txt`保存，无外网字体依赖。

优惠券入口UI预览参考 [Vant CouponCell](https://github.com/youzan/vant/blob/main/packages/vant/src/coupon-cell/CouponCell.tsx) 与 [Coupon](https://github.com/youzan/vant/blob/main/packages/vant/src/coupon/Coupon.tsx) 的入口、面额、门槛、说明分区，自行用原生DOM+wa-dialog实现，未引入Vue或复制源码。`web/coupons.css`与`renderCouponEntry`只提供显式示例UI，暂无优惠券后端、领取或结算抵扣，不能宣称优惠已生效。

商品标签统一：参考 [shadcn/ui Badge](https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/badge.tsx) 的内容适宽、胶囊轮廓和紧凑内边距，独立实现 `web/product-labels.css`。B/C两端共用，覆盖商品卡标签、详情折扣及后台自定义标签预览，保留商家颜色。首页、合集和浏览记录均复用productCard；折扣格式统一X折，整数去掉小数零。

2026-10-19 第二轮详情精修：进一步检查 [Saleor Paper Storefront](https://github.com/saleor/storefront)（GitHub页面约1.6k星；源码最新提交 `dcf6f9c`，2026-10-14）。具体参考 `src/styles/brand.css` 的近白/柔灰表面、低阴影和统一边框，以及 `src/ui/components/pdp/variant-selection/variant-name-selector.tsx` 的规格选中态与焦点处理。独立编写暖白画廊、细线价格区、稳定宽度的规格勾选、双列服务项及按钮阴影，没有复制源码或引入运行依赖。本地只读参考仓库位于 `D:/qiuzhao/Project/ui-reference-saleor-20261019`。

2026-10-19 商品详情购买区调整：参考 [shadcn/ui](https://github.com/shadcn-ui/ui) 的紧凑徽章、边框与选中态（查询时 125,943 星，最近推送 2026-10-19），以及 [Vercel Commerce 的商品描述组件](https://github.com/vercel/commerce/blob/main/components/product/product-description.tsx) 的标题与价格分组。自行实现局部 CSS 与 DOM，没有引入组件依赖。售价 42px，折扣及优惠 15px，节省金额随 SKU 更新；数量行横排，减少区块间距。样式在 `web/store-background.css`，逻辑在 `web/c.js`。

本次美化参考了以下项目的页面组织方式，实际样式及导航图标在本项目内编写，没有引入它们的框架或组件代码。

- Tabler：https://github.com/tabler/tabler。后台导航、表格、表单和统计卡片的层次与留白。
- Medusa Storefront：https://github.com/medusajs/nextjs-starter-medusa。商城图片展示、商品网格和购买信息组织。

B 端样式位于 `web/admin.css`；C 端样式位于 `web/storefront.css`，两端分别加载，商家设置的主题色仍然有效。

保留商品行内 SKU 配置；商品列表不显示勾选框、批量操作栏和禁售按钮；展开 SKU 时隐藏图片路径。
