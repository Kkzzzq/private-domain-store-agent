"""真实站点只读检查；只允许登录/注销的认证写入，不写店铺业务数据。"""
import argparse
import json
from pathlib import Path

import httpx


def check(origin, credential_file):
    lines=Path(credential_file).read_text(encoding="utf-8").splitlines()
    checks=[]
    def expect(name, ok, expected=True, actual=None):
        checks.append({"name":name,"passed":bool(ok),"expected":expected,"actual":bool(ok) if actual is None else actual})
        if not ok:raise AssertionError(name)
    with httpx.Client(base_url=origin,timeout=30) as client:
        response=client.post('/api/v1/auth/login',json={"username":lines[1][4:].strip(),"password":lines[2][4:].strip()})
        response.raise_for_status();client.headers['Authorization']='Bearer '+response.json()['access_token']
        def read(path):
            response=client.get('/api/v1'+path);response.raise_for_status();return response.json()
        try:
            shops=read('/op/records/shops?size=100')['items']
            shop=next(row for row in shops if row['share_code']=='nanzhi');sid=shop['id']
            b=read(f'/op/shops/{sid}/b/shop');c=read('/c/shops/nanzhi')
            for field in ('id','name','notice','status','theme_color'):
                expect('OP维护视角与C店铺字段一致：'+field,b[field]==c[field],b[field],c[field])
            managed=read(f'/op/shops/{sid}/b/products');visible=read('/c/shops/nanzhi/products')
            by_id={row['id']:row for row in managed}
            expect('C端商品全部属于当前真实店铺',all(row['id'] in by_id and row['shop_id']==sid for row in visible))
            for product in visible:
                source=by_id[product['id']]
                for field in ('name','category','description','image_url','status','sales_count','limit_per_user'):
                    expect(f"商品{product['id']}字段一致：{field}",product[field]==source[field],source[field],product[field])
                skus={row['id']:row for row in source['skus']}
                for sku in product['skus']:
                    fields=('id','spec','image_url','price_yuan','market_price_yuan','stock','status','sort_order','parameters')
                    expected={field:skus[sku['id']][field] for field in fields};actual={field:sku[field] for field in fields}
                    expect(f"商品{product['id']}规格{sku['id']}价格库存及参数一致",actual==expected,expected,actual)
                    expect(f"规格{sku['id']}买家可购买状态符合库存",sku['purchasable']==(sku['stock']>0))
                expect(f"商品{product['id']}未暴露下架规格",all(row['status']=='on' for row in product['skus']))
            unfiltered=read('/op/records/orders')
            expect('OP订单未选店铺时不全量展示',unfiltered.get('needs_filter') is True and unfiltered['items']==[])
            result={"origin":origin,"shop_id":sid,"shop_name":shop['name'],"managed_products":len(managed),"visible_products":len(visible),"business_writes":False,"checks":checks}
        finally:
            client.post('/api/v1/auth/logout').raise_for_status()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--operator-file',required=True)
    parser.add_argument('--report',required=True)
    args=parser.parse_args()
    result=check(args.origin,args.operator_file)
    Path(args.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key!='checks'},ensure_ascii=False))
    print('PASS',len(result['checks']),'real shop readonly assertions')


if __name__=='__main__':main()
