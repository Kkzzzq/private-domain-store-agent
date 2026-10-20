# 新增演示商品图片登记

下载日期：2026-10-19。作者、照片 ID、原始页面 slug 的完整清单在 `backend/app/demo_catalog.py` 的 `PHOTO_SOURCES`；具体页面形式为 `https://www.pexels.com/photo/{slug}-{id}/`。

- 素白杯：KATRIN BOLOVTSOVA / 6312237。
- 浅灰杯：Andrea Piacquadio / 1809127。
- 带盖编织篮：Charlotte May / 5824584。
- 悬挂编织篮：abdellah photographie / 16725450。
- 素白靠垫：Marek Hrnčiarik / 15758184。
- 暖色靠垫组合：Ron Lach / 8762876。
- 横线记录本：Engin Akyurt / 4554344。
- 空白线圈本：Tara Winstead / 6682959。

许可：[Pexels License](https://www.pexels.com/license/)。不得暗示照片作者为商品背书。仅为商城演示素材，不代表真实供货、尺寸、材质认证或商家实拍；商品详情已明确这一点，不用图片推断精确规格。

文件在 `web/covers/catalog/pexels-{id}.jpg`。下载地址为 `https://images.pexels.com/photos/{id}/pexels-photo-{id}.jpeg?auto=compress&cs=tinysrgb&w=960`，使用平台缩放版本，未进行本地调色或伪造 SKU 颜色。每个新增 SKU 对应不同原始照片。

四件商品、八个 SKU，通过 `cd backend; .venv\Scripts\python.exe scripts\add_demo_catalog.py --shop nanzhi` 写入当前配置的数据库，先确认 `.env` 指向演示库。脚本只新增，不覆盖同名商品，不修改旧订单、用户、库存或商家设置；重复执行不重复新增。新增「日常新物」首页手动栏目，不伪造销量。

商品查询/推荐读取业务库，可使用新商品。未自动将这些演示描述写入政策 RAG 知识库，不将数据库更新冒称向量知识库已重建。

## 多 SKU SPU

`--expand-cup` 将“日常简约饮水杯”扩充为六规格 SPU：素白陶瓷/浅灰搪瓷各有单只、2只装、4只装。新增四个组合装 SKU，分别保存价格、划线价、库存与对应款式图片，重复执行不重复添加。组合装使用同款单只外观图片，不伪造多只实拍，描述明确装数以规格为准；不修改已有订单和单只 SKU。执行示例：`.venv\Scripts\python.exe scripts\add_demo_catalog.py --shop nanzhi --expand-cup`。
